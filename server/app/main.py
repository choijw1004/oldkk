import asyncio
import logging
import os
import sqlite3
import time
from collections import OrderedDict
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from .models import ExpressionPage, FeedbackRequest, FeedbackResponse, RunRequest, RunResponse, Style
from .providers import DemoProvider, OpenAIProvider, ProviderError
from .retrieval import ExpressionStore
from .workflow import build_workflow


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
logger = logging.getLogger("old_keke")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    ai_available: bool
    default_provider: Literal["openai", "demo"]
    model: str | None
    dataset_count: int


class MetaResponse(BaseModel):
    total: int
    styles: dict[str, int]
    dataset_status: Literal["unreviewed_seed"]


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def create_app(*, api_key: str | None = None, model: str | None = None,
               db_path: Path | None = None, demo_only: bool | None = None) -> FastAPI:
    key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
    model_name = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    force_demo = demo_only if demo_only is not None else os.getenv("DEMO_ONLY", "0") == "1"
    feedback_path = db_path or ROOT / ".local" / "feedback.sqlite3"

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = ExpressionStore(ROOT / "docs" / "old-keke-expressions.json")
        app.state.live = OpenAIProvider(key, model_name) if key and not force_demo else None
        app.state.demo_graph = build_workflow(app.state.store, DemoProvider())
        app.state.live_graph = build_workflow(app.state.store, app.state.live) if app.state.live else None
        app.state.gate = asyncio.Semaphore(3)
        app.state.recent_runs = OrderedDict()
        feedback_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(feedback_path)) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY, run_id TEXT NOT NULL UNIQUE,
                rating TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            connection.commit()
        yield
        if app.state.live:
            await app.state.live.close()

    app = FastAPI(title="늙크크 연구소 API", version="0.1.0", docs_url="/api/docs",
                  redoc_url=None, lifespan=lifespan)

    @app.exception_handler(APIError)
    async def api_error_handler(request, exc):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request, exc):
        return JSONResponse(status_code=422, content={"error": {
            "code": "VALIDATION_ERROR", "message": "입력값을 확인해 주세요. 문장은 2~300자, 강도는 1~3이에요.",
        }})

    @app.exception_handler(HTTPException)
    async def http_error_handler(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"error": {
            "code": "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "message": "요청한 경로를 찾을 수 없어요." if exc.status_code == 404 else "요청을 처리할 수 없어요.",
        }})

    @app.exception_handler(Exception)
    async def internal_error_handler(request, exc):
        logger.error("Unhandled server error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"error": {
            "code": "INTERNAL_ERROR", "message": "처리 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.",
        }})

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health():
        live = app.state.live is not None
        return HealthResponse(ai_available=live, default_provider="openai" if live else "demo",
                              model=model_name if live else None, dataset_count=len(app.state.store.items))

    @app.get("/api/v1/meta", response_model=MetaResponse)
    async def meta():
        return app.state.store.stats()

    @app.get("/api/v1/expressions", response_model=ExpressionPage)
    async def expressions(q: str = Query(default="", max_length=100), style: Style | None = None,
                          page: int = Query(default=1, ge=1), page_size: int = Query(default=12, ge=1, le=50)):
        found = app.state.store.browse(q, style)
        start = (page - 1) * page_size
        return ExpressionPage(items=found[start:start + page_size], total=len(found), page=page, page_size=page_size)

    @app.post("/api/v1/runs", response_model=RunResponse)
    async def run(payload: RunRequest):
        gate = app.state.gate
        if gate.locked():
            raise APIError(429, "BUSY", "실험실이 잠시 붐비고 있어요. 조금 뒤에 다시 시도해 주세요.")
        graph = app.state.demo_graph if payload.engine == "demo" or not app.state.live_graph else app.state.live_graph
        async with gate:
            try:
                result = await asyncio.wait_for(graph.ainvoke({
                    "request": payload, "retry_count": 0, "trace": [], "started_at": time.monotonic(),
                }), timeout=90)
            except TimeoutError:
                raise APIError(504, "AI_TIMEOUT", "처리가 오래 걸려 중단했어요. 다시 시도해 주세요.") from None
            except ProviderError:
                raise APIError(502, "AI_PROVIDER_ERROR", "AI 연결에 실패했어요. 서버의 키·사용 한도·연결 상태를 확인해 주세요.") from None
        response = result["response"]
        app.state.recent_runs[response.id] = True
        if len(app.state.recent_runs) > 1000:
            app.state.recent_runs.popitem(last=False)
        return response

    @app.post("/api/v1/feedback", response_model=FeedbackResponse, status_code=201)
    async def feedback(payload: FeedbackRequest):
        if payload.run_id not in app.state.recent_runs:
            raise APIError(404, "RUN_NOT_FOUND", "결과가 만료됐어요. 다시 실행한 뒤 의견을 남겨 주세요.")
        try:
            with closing(sqlite3.connect(feedback_path)) as connection:
                cursor = connection.execute("INSERT INTO feedback (run_id, rating, comment) VALUES (?, ?, ?)",
                                            (payload.run_id, payload.rating, payload.comment.strip()))
                connection.commit()
                feedback_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            raise APIError(409, "FEEDBACK_EXISTS", "이미 의견을 남긴 결과예요.") from None
        return FeedbackResponse(id=feedback_id)

    # Production build and API can be served from one origin; dev uses Vite's /api proxy.
    build_dir = ROOT / "client" / "dist"
    if build_dir.is_dir():
        app.mount("/", StaticFiles(directory=build_dir, html=True), name="web")
    return app


app = create_app()
