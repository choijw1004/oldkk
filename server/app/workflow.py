import time
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from .models import Analysis, Draft, Reference, Review, RunRequest, RunResponse, TraceStep
from .providers import Provider
from .retrieval import ExpressionStore


class State(TypedDict, total=False):
    request: RunRequest
    analysis: Analysis
    references: list[Reference]
    draft: Draft
    review: Review
    retry_count: int
    trace: list[TraceStep]
    response: RunResponse
    started_at: float


def validate_draft(request: RunRequest, draft: Draft, references: list[Reference], demo=False) -> list[str]:
    issues = []
    allowed_ids = {ref.id for ref in references}
    for entry in [*draft.candidates, *draft.evidence]:
        if not entry.explanation.strip():
            issues.append("설명은 공백이 아닌 내용이 필요해요.")
        if set(entry.reference_ids) - allowed_ids:
            issues.append("참고 ID는 검색된 자료의 ID만 사용해야 해요.")
    for evidence in draft.evidence:
        if evidence.phrase not in request.text:
            issues.append("판독 근거는 원문에 존재하는 연속된 표현이어야 해요.")
    if request.mode == "generate":
        if any(not candidate.text.strip() for candidate in draft.candidates):
            issues.append("빈 문장을 후보로 사용할 수 없어요.")
        if len(draft.candidates) != 3:
            issues.append("생성 후보를 정확히 3개 작성해 주세요.")
        if not demo and len({c.text.strip() for c in draft.candidates}) != 3:
            issues.append("후보 3개는 서로 달라야 해요.")
        if draft.verdict is not None or draft.score is not None or draft.evidence:
            issues.append("생성 결과의 판독 필드는 비워 주세요.")
    else:
        if draft.candidates or draft.verdict is None:
            issues.append("판독 결과에는 판정이 필요하며 생성 후보는 없어야 해요.")
        if not demo and draft.score is None:
            issues.append("AI 판독의 재미용 점수를 작성해 주세요.")
        if draft.verdict == "old_keke" and not draft.evidence:
            issues.append("늙크크 판정에는 원문 속 근거가 필요해요.")
    return list(dict.fromkeys(issues))


def build_workflow(store: ExpressionStore, provider: Provider):
    def traced(state, name, started):
        return state.get("trace", []) + [TraceStep(node=name, elapsed_ms=round((time.monotonic() - started) * 1000))]

    async def analyze(state):
        started = time.monotonic()
        result = await provider.analyze(state["request"])
        return {"analysis": result, "trace": traced(state, "analyze", started)}

    def retrieve(state):
        started = time.monotonic()
        request = state["request"]
        query = request.text + " " + state["analysis"].search_query
        refs = store.search(query, request.style if request.mode == "generate" else None)
        return {"references": refs, "trace": traced(state, "retrieve", started)}

    async def process(state):
        started = time.monotonic()
        result = await provider.draft(state["request"], state["analysis"], state["references"])
        return {"draft": result, "trace": traced(state, state["request"].mode, started)}

    async def review(state):
        started = time.monotonic()
        result = await provider.review(state["request"], state["draft"], state["references"])
        code_issues = validate_draft(state["request"], state["draft"], state["references"], provider.name == "demo")
        combined = Review(passed=result.passed and not code_issues,
                          issues=list(dict.fromkeys(result.issues + code_issues)), note=result.note)
        return {"review": combined, "trace": traced(state, "review", started)}

    async def revise(state):
        started = time.monotonic()
        result = await provider.draft(state["request"], state["analysis"], state["references"],
                                      state["draft"], state["review"].issues)
        return {"draft": result, "retry_count": state.get("retry_count", 0) + 1,
                "trace": traced(state, "revise", started)}

    def route_review(state):
        if not state["review"].passed and state.get("retry_count", 0) < 1:
            return "revise"
        return "finalize"

    def finalize(state):
        status = "demo" if provider.name == "demo" else ("passed" if state["review"].passed else "needs_review")
        note = state["review"].note
        if status == "needs_review":
            note = "자동 검수를 통과하지 못한 결과예요. " + " ".join(state["review"].issues)
        # Broken references/evidence must not be presented as factual citations, even on final failure.
        allowed = {ref.id for ref in state["references"]}
        draft = state["draft"].model_copy(deep=True)
        for entry in [*draft.candidates, *draft.evidence]:
            entry.reference_ids = [ref_id for ref_id in entry.reference_ids if ref_id in allowed]
        draft.evidence = [item for item in draft.evidence if item.phrase in state["request"].text]
        response = RunResponse(
            **draft.model_dump(), id=str(uuid4()), mode=state["request"].mode,
            original_text=state["request"].text, references=state["references"], quality_status=status,
            review_note=note, retry_count=state.get("retry_count", 0), provider=provider.name,
            model=provider.model, elapsed_ms=round((time.monotonic() - state["started_at"]) * 1000),
            trace=state["trace"],
        )
        return {"response": response}

    graph = StateGraph(State)
    graph.add_node("analyze", analyze)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", process)
    graph.add_node("detect", process)
    graph.add_node("review", review)
    graph.add_node("revise", revise)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "retrieve")
    graph.add_conditional_edges("retrieve", lambda state: state["request"].mode,
                                {"generate": "generate", "detect": "detect"})
    graph.add_edge("generate", "review")
    graph.add_edge("detect", "review")
    graph.add_conditional_edges("review", route_review, {"revise": "revise", "finalize": "finalize"})
    graph.add_edge("revise", "review")
    graph.add_edge("finalize", END)
    return graph.compile()
