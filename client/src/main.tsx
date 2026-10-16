import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowRight, LoaderCircle, Search } from 'lucide-react';
import { api } from './api';
import type { RunResult } from './types';
import './styles.css';

function App() {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<RunResult | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => request.current?.abort(), []);

  async function submit(event?: React.FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (request.current) return;

    const sentence = text.trim();
    setError('');
    setResult(null);
    if (sentence.length < 2 || sentence.length > 300) {
      setError('문장을 2~300자로 입력해 주세요.');
      return;
    }

    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    try {
      const output = await api<RunResult>('/runs', {
        method: 'POST',
        body: JSON.stringify({ text: sentence, mode: 'generate', style: 'daily', intensity: 2, engine: 'auto' }),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(95_000)]),
      });
      if (!controller.signal.aborted) setResult(output);
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : '처리하지 못했어요. 다시 시도해 주세요.');
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
      if (request.current === controller) request.current = null;
    }
  }

  return (
    <main className={`search-page${result ? ' has-results' : ''}`}>
      <div className="search-content">
        <h1>늙크크<span>연구소</span></h1>
        <p className="intro">문장을 늙크크 말투로 바꿔보세요.</p>

        <form className="search-form" onSubmit={submit} role="search" aria-label="문장 변환" aria-busy={busy} noValidate>
          <div className="search-box">
            <Search className="search-icon" size={20} strokeWidth={1.7} aria-hidden="true" />
            <label className="sr-only" htmlFor="sentence">변환할 문장</label>
            <input
              id="sentence"
              type="text"
              value={text}
              onChange={event => { setText(event.target.value); setResult(null); setError(''); }}
              onKeyDown={event => {
                if (event.key === 'Enter' && (event.nativeEvent.isComposing || event.keyCode === 229)) event.preventDefault();
              }}
              placeholder="오늘 점심 뭐 먹을까?"
              minLength={2}
              maxLength={300}
              readOnly={busy}
              autoComplete="off"
              enterKeyHint="go"
              aria-invalid={Boolean(error)}
              aria-describedby={error ? 'search-error' : undefined}
            />
            <button className="submit-button" type="submit" disabled={busy || !text.trim()} aria-label={busy ? '변환 중' : '문장 변환'}>
              {busy ? <LoaderCircle className="spin" size={21} aria-hidden="true" /> : <ArrowRight size={21} strokeWidth={1.8} aria-hidden="true" />}
            </button>
          </div>
        </form>

        <div className="search-status" role="status" aria-live="polite">
          {busy && '문장을 바꾸고 있어요…'}
        </div>

        {error && (
          <div className="search-error" id="search-error" role="alert">
            <p>{error}</p>
            <button type="button" onClick={() => void submit()}>다시 시도</button>
          </div>
        )}

        {result && (
          <section className="results" aria-label="변환 결과" aria-live="polite">
            {result.provider === 'demo' && (
              <p className="result-note">샘플 예문이에요. 입력 문장을 변환한 결과는 아니에요.</p>
            )}
            {result.quality_status === 'needs_review' && (
              <p className="result-note">자동 검수를 통과하지 못한 결과예요. 표현과 뜻을 확인해 주세요.</p>
            )}
            <ul className="result-list">
              {result.candidates.map((candidate, index) => <li key={index}>{candidate.text}</li>)}
            </ul>
          </section>
        )}
      </div>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
