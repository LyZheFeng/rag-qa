// 与后端 app/schemas.py 逐字段对齐（pydantic ↔ TS 契约）
export interface Hit {
  index: number;
  chunk_id: string;
  doc_name: string;
  section_path: string;
  text: string;
  score: number; // 相似度 = 1 - cos 距离
}

export interface Latency {
  retrieve_ms: number;
  generate_ms: number;
  total_ms: number;
}

export type ParseMode = "json" | "retry" | "fallback";

export interface AskResponse {
  question: string;
  answer: string;
  refused: boolean;
  parse_mode: ParseMode;
  cited: Hit[];
  retrieved: Hit[];
  latency: Latency;
}

// GET /health 响应（侧栏状态）
export interface HealthInfo {
  status: string;
  version: string;
  retriever: string;
  chunks: number;
  embed_dim: number;
  llm_model: string;
}

// SSE 事件载荷：sources → delta* → [retry → delta*]* → done | error
export interface SourcesPayload {
  hits: Hit[];
}
export interface DeltaPayload {
  text: string;
}
export interface RetryPayload {
  message: string;
}
export interface ErrorPayload {
  message: string;
  trace_id?: string;
}
