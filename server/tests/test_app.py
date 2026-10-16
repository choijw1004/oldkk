import asyncio
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app.main import create_app
from server.app.models import Candidate, Draft, Evidence, RunRequest
from server.app.providers import DemoProvider, ProviderError
from server.app.retrieval import ExpressionStore
from server.app.workflow import build_workflow, validate_draft

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store():
    return ExpressionStore(ROOT / 'docs' / 'old-keke-expressions.json')


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(api_key='', demo_only=True, db_path=tmp_path / 'feedback.sqlite3')) as client:
        yield client


def test_seed_and_search(store):
    assert len(store.items) == len(store.by_id) == 200
    assert store.stats()['styles']['retro_chat'] == 20
    assert all(store.by_id[f'old-keke-{i:03}'].style == 'daily' for i in range(151, 201))
    assert store.search('점심 메뉴 식사', 'daily')
    for style in ('daily', 'wordplay', 'retro_chat', 'theatrical'):
        assert all(ref.style == style for ref in store.search('점심 당근 방가방가 반갑습니다', style))
    assert store.search('zzqxv987654321') == []


def test_health_and_browse(client):
    health = client.get('/api/v1/health').json()
    assert health['dataset_count'] == 200
    assert health['ai_available'] is False
    assert health['default_provider'] == 'demo'
    meta = client.get('/api/v1/meta').json()
    assert sum(meta['styles'].values()) == meta['total'] == 200
    first = client.get('/api/v1/expressions').json()
    second = client.get('/api/v1/expressions?page=2').json()
    assert len(first['items']) == len(second['items']) == 12
    assert not ({i['id'] for i in first['items']} & {i['id'] for i in second['items']})
    filtered = client.get('/api/v1/expressions?style=wordplay').json()
    assert filtered['total'] == 4
    assert all(i['style'] == 'wordplay' for i in filtered['items'])
    assert client.get('/api/v1/expressions?q=zzqxv987654321').json()['items'] == []
    query = first['items'][0]['expression']
    assert any(i['expression'] == query for i in client.get('/api/v1/expressions', params={'q': query}).json()['items'])


@pytest.mark.parametrize('payload', [
    {'text': '   '}, {'text': 'x'}, {'text': '가' * 301},
    {'text': '테스트', 'mode': 'unknown'}, {'text': '테스트', 'intensity': True},
    {'text': '테스트', 'intensity': 4}, {'text': '테스트', 'style': 'theatrical'},
    {'text': '테스트', 'unexpected': 'value'},
])
def test_invalid_input(client, payload):
    response = client.post('/api/v1/runs', json=payload)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'


@pytest.mark.parametrize('mode', ['generate', 'detect'])
def test_demo_workflow(client, mode):
    response = client.post('/api/v1/runs', json={'text': '  오늘 점심 뭐 먹을까?  ', 'mode': mode})
    assert response.status_code == 200
    body = response.json()
    assert body['original_text'] == '오늘 점심 뭐 먹을까?'
    assert body['provider'] == body['quality_status'] == 'demo'
    assert body['score'] is None
    assert body['retry_count'] == 0
    assert [step['node'] for step in body['trace']] == ['analyze', 'retrieve', mode, 'review']
    allowed = {ref['id'] for ref in body['references']}
    assert all(set(c['reference_ids']) <= allowed for c in body['candidates'])
    if mode == 'generate':
        assert len(body['candidates']) == 3
        assert body['verdict'] is None
    else:
        assert body['verdict'] == 'uncertain'
        assert body['candidates'] == []


def test_feedback_saved_once_without_raw_text(client):
    result = client.post('/api/v1/runs', json={'text': '오늘 점심 뭐 먹을까?'}).json()
    payload = {'run_id': result['id'], 'rating': 'up', 'comment': '재밌어요'}
    saved = client.post('/api/v1/feedback', json=payload)
    assert saved.status_code == 201 and saved.json()['status'] == 'saved'
    assert client.post('/api/v1/feedback', json=payload).status_code == 409
    assert client.post('/api/v1/feedback', json={**payload, 'run_id': 'unknown'}).status_code == 404
    assert client.post('/api/v1/feedback', json={**payload, 'comment': '가' * 501}).status_code == 422


def test_feedback_database_shape(tmp_path):
    db = tmp_path / 'feedback.sqlite3'
    with TestClient(create_app(api_key='', demo_only=True, db_path=db)) as client:
        result = client.post('/api/v1/runs', json={'text': '저장하지 않을 입력 문장'}).json()
        client.post('/api/v1/feedback', json={'run_id': result['id'], 'rating': 'down'})
    with sqlite3.connect(db) as connection:
        columns = {row[1] for row in connection.execute('PRAGMA table_info(feedback)')}
        assert columns == {'id', 'run_id', 'rating', 'comment', 'created_at'}
        assert connection.execute('SELECT count(*) FROM feedback').fetchone()[0] == 1
    with TestClient(create_app(api_key='', demo_only=True, db_path=db)) as restarted:
        assert restarted.post('/api/v1/feedback', json={'run_id': result['id'], 'rating': 'up'}).status_code == 404


class RepairProvider(DemoProvider):
    name = 'openai'
    model = 'fake-test-provider'

    def __init__(self, repair=True):
        self.repair = repair
        self.draft_calls = 0

    async def draft(self, request, analysis, references, previous=None, issues=None):
        self.draft_calls += 1
        invalid = not (previous and self.repair)
        return Draft(headline='테스트', summary='테스트 결과', verdict=None, score=None, evidence=[], candidates=[
            Candidate(text=f'후보 {i}', explanation='설명', reference_ids=['invalid-id'] if invalid else []) for i in range(3)
        ])


@pytest.mark.parametrize('repair', [True, False])
def test_review_repair_is_bounded_and_citations_sanitized(store, repair):
    provider = RepairProvider(repair)
    state = asyncio.run(build_workflow(store, provider).ainvoke({
        'request': RunRequest(text='오늘 점심 뭐 먹을까?'),
        'trace': [], 'retry_count': 0, 'started_at': time.monotonic(),
    }))
    result = state['response']
    assert provider.draft_calls == 2
    assert result.retry_count == 1
    assert result.quality_status == ('passed' if repair else 'needs_review')
    assert sum(step.node == 'review' for step in result.trace) == 2
    assert all(c.reference_ids == [] for c in result.candidates)


def test_invalid_evidence_is_detected():
    request = RunRequest(text='보통의 문장입니다', mode='detect')
    draft = Draft(headline='판독', summary='근거 검사', verdict='old_keke', score=60, candidates=[],
                  evidence=[Evidence(phrase='없는 표현', explanation='설명', reference_ids=[])])
    assert any('원문' in issue for issue in validate_draft(request, draft, []))


def test_blank_candidates_are_rejected():
    request = RunRequest(text='평범한 문장입니다')
    draft = Draft(headline='후보', summary='공백 검사', verdict=None, score=None, evidence=[], candidates=[
        Candidate(text=text, explanation='설명', reference_ids=[]) for text in ['   ', '다른 문장', '세 번째 문장']
    ])
    assert any('빈 문장' in issue for issue in validate_draft(request, draft, []))


def test_provider_failure_is_not_disguised_as_demo(client):
    class BrokenGraph:
        async def ainvoke(self, state):
            raise ProviderError('secret upstream detail')

    client.app.state.live_graph = BrokenGraph()
    response = client.post('/api/v1/runs', json={'text': '오늘 점심 뭐 먹을까?'})
    assert response.status_code == 502
    assert response.json()['error']['code'] == 'AI_PROVIDER_ERROR'
    assert 'secret' not in response.text
    assert client.post('/api/v1/runs', json={'text': '오늘 점심 뭐 먹을까?', 'engine': 'demo'}).json()['provider'] == 'demo'


def test_timeout_and_busy_are_explicit(client, monkeypatch):
    async def timed_out(awaitable, timeout):
        awaitable.close()
        raise TimeoutError()

    monkeypatch.setattr('server.app.main.asyncio.wait_for', timed_out)
    response = client.post('/api/v1/runs', json={'text': '실험 문장'})
    assert response.status_code == 504
    assert response.json()['error']['code'] == 'AI_TIMEOUT'
    client.app.state.gate = asyncio.Semaphore(0)
    assert client.post('/api/v1/runs', json={'text': '실험 문장'}).status_code == 429


def test_static_site_and_api_404(client):
    if (ROOT / 'client' / 'dist').is_dir():
        response = client.get('/')
        assert response.status_code == 200
        assert '늙크크 연구소' in response.text
    missing = client.get('/api/v1/missing')
    assert missing.status_code == 404
    assert missing.json()['error']['code'] == 'NOT_FOUND'
