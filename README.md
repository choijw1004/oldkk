# 늙크크 연구소

문장을 입력하면 늙크크 말투로 바꿔주는 로컬 MVP입니다. React + TypeScript 화면과 FastAPI + LangGraph 백엔드를 사용합니다.

현재 화면은 이름과 입력창 하나로 구성됩니다. 문장을 쓰고 Enter 또는 입력창의 화살표를 누르면 아래에 후보 3개가 나옵니다. 생성은 생활형·강도 2로 실행합니다. 도감, 판독, 옵션 선택, 피드백 등 부가 기능은 추후 화면에 붙일 범위로 미뤘습니다.

## 빠르게 시작

필요한 도구: Python 3.12 이상, [uv](https://docs.astral.sh/uv/), Node.js 22.12 이상, npm.

프로젝트 루트에서 실행하세요.

```sh
./run.sh
```

프런트를 빌드하고 API와 화면을 하나의 서버에서 제공합니다. 브라우저에서 **http://127.0.0.1:8000** 을 여세요. 종료는 실행 터미널에서 `Ctrl+C`입니다. 포트가 사용 중이면 `PORT=8001 ./run.sh`로 바꿀 수 있습니다.

API 키가 없으면 샘플 모드입니다. 입력과 관련된 참고 예문을 보여주며, 결과 위에 샘플임을 표시합니다. 키가 설정된 환경에서도 `DEMO_ONLY=1 ./run.sh`로 샘플 모드를 강제할 수 있습니다.

## AI 모드

```sh
cp .env.example .env
```

`.env`의 `OPENAI_API_KEY`에 본인의 키를 넣고 서버를 다시 실행하세요. 기본 모델은 기존 설계의 `gpt-4.1-mini`이며 `OPENAI_MODEL`로 변경할 수 있습니다. `.env`는 Git에서 제외됩니다. 브라우저에 키를 넣지 마세요.

AI 모드는 실제 API 사용 비용이 발생합니다. 요청당 분석·생성/판독·검수 3회, 수정이 필요하면 최대 5회 호출합니다. 공급자 실패는 오류로 표시하며 샘플 결과로 바꾸지 않습니다. Responses API의 Pydantic Structured Outputs와 `store=False`를 사용합니다. [공식 OpenAI 문서](https://developers.openai.com/api/docs/guides/structured-outputs)

## 개발 실행

터미널 1 (API):

```sh
uv sync --group dev
uv run uvicorn server.app.main:app --reload --host 127.0.0.1 --port 8000
```

터미널 2 (프런트):

```sh
cd client
npm ci
npm run dev
```

Vite가 출력한 로컬 주소를 여세요. `/api` 요청은 8000번 API로 전달됩니다. API 명세 UI는 http://127.0.0.1:8000/api/docs 입니다.

## 검증

```sh
uv run pytest -q
cd client
npm run build
```

자동 테스트는 외부 모델을 호출하지 않습니다. 실제 모델의 품질·응답 시간·사용 한도는 유효한 키로 별도 확인이 필요합니다.

## 구성과 현재 범위

- `client/src/`: 단일 문장 입력과 변환 결과. 모바일 대응, Enter 제출, 한글 조합 중 제출 방지, 중복 요청 방지, 오류 재시도.
- `server/app/`: 입력 검증, 어휘 기반 검색, LangGraph 분석 → 검색 → 생성/판독 → 검수 → 최대 1회 수정.
- `server/tests/`: API, 데이터·검색, 검수 재시도, 공급자 실패, 피드백 저장 검증.
- `docs/old-keke-expressions.json`: 200개 검토 전 창작 시드. 원본 ID와 예문을 유지합니다.
- `.local/feedback.sqlite3`: 피드백만 저장합니다. 원문·결과는 DB에 저장하지 않으며 실행 ID는 최근 1,000건만 메모리에 유지합니다.

실제 나이 추정이나 정확도 보장은 하지 않습니다. 공개 배포는 이번 범위에 포함하지 않으며 서버는 기본적으로 로컬에 바인딩합니다.

자세한 문서: [요구사항](docs/requirements.md), [AI 아키텍처](docs/ai-architecture.md), [API](docs/api.md).
