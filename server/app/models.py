from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Style = Literal["daily", "wordplay", "retro_chat", "theatrical"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRequest(StrictModel):
    text: str = Field(min_length=2, max_length=300)
    mode: Literal["generate", "detect"] = "generate"
    style: Literal["daily", "wordplay", "retro_chat"] = "daily"
    intensity: int = Field(default=2, ge=1, le=3, strict=True)
    engine: Literal["auto", "demo"] = "auto"

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class Expression(StrictModel):
    id: str
    expression: str
    neutral_expression: str
    situation: str
    category: str
    style: Style
    review_status: str
    origin: str
    source_url: str | None


class Reference(Expression):
    retrieval_score: float


class ExpressionPage(StrictModel):
    items: list[Expression]
    total: int
    page: int
    page_size: int


class Analysis(StrictModel):
    situation: str
    intent: str
    search_query: str
    is_quotation: bool


class Candidate(StrictModel):
    text: str = Field(min_length=1, max_length=600)
    explanation: str = Field(min_length=1, max_length=500)
    reference_ids: list[str] = Field(max_length=6)


class Evidence(StrictModel):
    phrase: str = Field(min_length=1, max_length=300)
    explanation: str = Field(min_length=1, max_length=500)
    reference_ids: list[str] = Field(max_length=6)


class Draft(StrictModel):
    headline: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=1000)
    verdict: Literal["old_keke", "neutral", "uncertain"] | None
    score: int | None = Field(ge=0, le=100)
    candidates: list[Candidate] = Field(max_length=3)
    evidence: list[Evidence] = Field(max_length=6)


class Review(StrictModel):
    passed: bool
    issues: list[str] = Field(max_length=10)
    note: str = Field(max_length=1000)


class TraceStep(StrictModel):
    node: str
    elapsed_ms: int


class RunResponse(Draft):
    id: str
    mode: Literal["generate", "detect"]
    original_text: str
    references: list[Reference]
    quality_status: Literal["passed", "needs_review", "demo"]
    review_note: str
    retry_count: int
    provider: Literal["openai", "demo"]
    model: str | None
    elapsed_ms: int
    trace: list[TraceStep]


class FeedbackRequest(StrictModel):
    run_id: str = Field(min_length=1, max_length=64)
    rating: Literal["up", "down"]
    comment: str = Field(default="", max_length=500)


class FeedbackResponse(StrictModel):
    id: int
    status: Literal["saved"] = "saved"
