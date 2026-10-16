# 늙크크 연구소 — API 명세 v1

기본 주소: `http://127.0.0.1:8000`. JSON은 UTF-8이다. 실제 OpenAPI 스키마는 서버의 `/openapi.json`, Swagger UI는 `/api/docs`에서 제공한다. 아래 예시의 판정과 문장은 형식 설명용이다.

## 엔드포인트

| Method | Path | 용도 |
| --- | --- | --- |
| GET | `/api/v1/health` | 서버·모델 구성 상태 |
| GET | `/api/v1/meta` | 데이터 수와 스타일별 개수 |
| GET | `/api/v1/expressions` | 표현 검색·스타일 필터·페이지 조회 |
| POST | `/api/v1/runs` | 생성 또는 판독 실행 |
| POST | `/api/v1/feedback` | 결과 공감도 저장 |

## 실행 요청

```json
{
  "text": "오늘 점심 뭐 먹을까?",
  "mode": "generate",
  "style": "daily",
  "intensity": 2,
  "engine": "auto"
}
```

- `text`: 공백 제거 후 2~300자.
- `mode`: `generate` 또는 `detect`.
- `style`: `daily`, `wordplay`, `retro_chat`. 기본 `daily`. 판독은 이 값과 무관하게 전체 스타일을 검색한다.
- `intensity`: 정수 1~3. 기본 2. 생성에만 적용한다.
- `engine`: `auto` 또는 `demo`. 기본 `auto`. auto는 서버 API 키가 있으면 OpenAI, 없으면 명시적 데모로 실행한다. OpenAI 실패 시 데모로 전환하지 않는다.

성공 응답(200):

```json
{
  "id": "UUID",
  "mode": "generate",
  "original_text": "오늘 점심 뭐 먹을까?",
  "headline": "점심 메뉴에도 말맛 한 스푼",
  "summary": "메뉴를 고르는 뜻은 유지하면서 능청스러운 표현을 더했어요.",
  "verdict": null,
  "score": null,
  "candidates": [
    {
      "text": "오늘은 뭘 먹어야 잘 먹었다고 소문이 날까?",
      "explanation": "익숙한 관용적 질문으로 바꿨어요.",
      "reference_ids": ["old-keke-021"]
    }
  ],
  "evidence": [],
  "references": [],
  "quality_status": "passed",
  "review_note": "의미 보존과 참고 자료 연결을 검수했어요.",
  "retry_count": 0,
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "elapsed_ms": 4200,
  "trace": [
    {"node": "analyze", "elapsed_ms": 800}
  ]
}
```

예시는 길이를 줄여 후보와 trace를 일부만 표시했다. 실제 생성 결과는 후보 3개다. `references`에는 검색된 표현 객체(아래 필드 + `retrieval_score`)가 들어간다. `reference_ids`는 이 목록에 있는 ID만 사용한다.

판독은 `candidates: []`이고 `verdict`가 `old_keke`, `neutral`, `uncertain` 중 하나다. `score`는 AI 경로에서 0~100의 재미용 지수다. 데모는 `uncertain`, `score: null`을 반환한다. `evidence` 항목은 `phrase`(원문에 있는 부분 문자열), `explanation`, `reference_ids`다.

`quality_status`는 `passed`, `needs_review`, `demo`. 검수 실패 후 1회 수정해도 미통과면 `needs_review`다. `provider`는 `openai` 또는 `demo`다. trace는 실행한 노드 이름과 소요 시간이며 모델 내부 추론을 담지 않는다.

## 표현 조회

`GET /api/v1/expressions?q=점심&style=daily&page=1&page_size=12`

`q`는 선택 검색어(최대 100자), `style`은 선택 필터(위 3종 및 `theatrical`), `page`는 1 이상, `page_size`는 1~50이다. 검색은 예문·일반 표현·상황·분류의 부분 문자열을 비교한다. AI 검색과 달리 도감에서는 정확한 문자열 필터를 사용한다.

```json
{
  "items": [
    {
      "id": "old-keke-021",
      "expression": "뭘 먹어야 잘 먹었다고 소문이 날까.",
      "neutral_expression": "오늘 뭐 먹을까?",
      "situation": "메뉴를 고르며 능청스럽게 농담할 때",
      "category": "음식·식사",
      "style": "daily",
      "review_status": "unreviewed",
      "origin": "synthetic_seed",
      "source_url": null
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 12
}
```

## 상태와 메타 정보

health: `status`, `ai_available`, `default_provider`, `model`, `dataset_count`.

meta: `total`, `styles`(style별 개수), `dataset_status: "unreviewed_seed"`.

## 피드백

`POST /api/v1/feedback`

```json
{
  "run_id": "실행 응답의 UUID",
  "rating": "up",
  "comment": "자연스럽고 웃겼어요."
}
```

`rating`: `up` 또는 `down`. `comment`: 선택, 최대 500자. 실행 ID당 1회 저장한다. 성공은 201과 `id`, `status: "saved"`를 반환한다. 같은 실행에 대한 중복은 409. 서버 재시작 또는 최근 1,000건 범위 밖의 실행 ID는 404다.

## 오류

```json
{"error": {"code": "VALIDATION_ERROR", "message": "입력값을 확인해 주세요."}}
```

| HTTP | code | 의미 |
| --- | --- | --- |
| 422 | VALIDATION_ERROR | 길이·옵션·타입 오류 |
| 404 | RUN_NOT_FOUND | 피드백 대상 실행 없음 |
| 409 | FEEDBACK_EXISTS | 피드백 중복 |
| 429 | BUSY | 동시 실행 제한 |
| 502 | AI_PROVIDER_ERROR | 인증·할당량·연결·출력 파싱 등 AI 제공자 오류 |
| 504 | AI_TIMEOUT | 요청 처리 90초 초과 |
| 500 | INTERNAL_ERROR | 예상하지 못한 서버 오류 |

오류 응답에 API 키, 원본 공급자 오류 본문, 스택 트레이스를 노출하지 않는다. 서버 접근 로그는 요청 본문을 기록하지 않는다.
