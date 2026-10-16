#!/bin/sh
set -eu
cd "$(dirname "$0")"

command -v uv >/dev/null 2>&1 || { echo 'uv가 필요합니다. README.md의 실행 안내를 확인해 주세요.' >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo 'Node.js와 npm이 필요합니다.' >&2; exit 1; }
uv sync --group dev
(
  cd client
  if [ ! -d node_modules ]; then npm ci; fi
  npm run build
)
echo "늙크크 연구소: http://127.0.0.1:${PORT:-8000} (종료: Ctrl+C)"
exec uv run uvicorn server.app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
