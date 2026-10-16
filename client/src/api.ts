export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  try {
    const response = await fetch(`/api/v1${path}`, {
      ...options,
      signal: options.signal ?? AbortSignal.timeout(95_000),
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(body?.error?.message || `서버 오류가 발생했어요. (${response.status})`);
    if (body === null) throw new Error('서버 응답을 읽지 못했어요. 다시 시도해 주세요.');
    return body as T;
  } catch (error) {
    if (error instanceof TypeError) throw new Error('서버에 연결할 수 없어요. 연결 상태를 확인하고 다시 시도해 주세요.');
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error('응답 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.');
    throw error;
  }
}
