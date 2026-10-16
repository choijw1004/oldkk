export type Style = 'daily' | 'wordplay' | 'retro_chat' | 'theatrical';
export type Mode = 'generate' | 'detect';
export interface Expression {
  id: string; expression: string; neutral_expression: string; situation: string;
  category: string; style: Style; review_status: string; origin: string; source_url: string | null;
}
export interface Health {
  status: string; ai_available: boolean; default_provider: 'openai' | 'demo';
  model: string | null; dataset_count: number;
}
export interface ExpressionPage { items: Expression[]; total: number; page: number; page_size: number }
export interface RunResult {
  id: string; mode: Mode; original_text: string; headline: string; summary: string;
  verdict: 'old_keke' | 'neutral' | 'uncertain' | null; score: number | null;
  candidates: { text: string; explanation: string; reference_ids: string[] }[];
  evidence: { phrase: string; explanation: string; reference_ids: string[] }[];
  references: (Expression & { retrieval_score: number })[];
  quality_status: 'passed' | 'needs_review' | 'demo'; review_note: string;
  retry_count: number; provider: 'openai' | 'demo'; model: string | null;
  elapsed_ms: number; trace: { node: string; elapsed_ms: number }[];
}
