/**
 * SatQuery AI Contract Types
 * Directly conforms to docs/CONTRACT.md and docs/API_CONTRACT.md
 */

export type Modality = 'optical' | 'sar';

export type TaskType = 
  | 'vqa' 
  | 'captioning' 
  | 'detection' 
  | 'change_detection' 
  | 'fusion';

export type ToolUsed = 
  | 'rsunivlm_vqa' 
  | 'rsunivlm_cap' 
  | 'rsunivlm_vg' 
  | 'rsunivlm_seg' 
  | 'rsunivlm_ccd' 
  | 'qwen_vl_vqa'
  | 'qwen_vl_cap'
  | 'qwen_vl_vg'
  | 'qwen_vl_seg'
  | 'qwen_vl_ccd'
  | 'fusion_classifier'
  | string;

export type VisualEvidenceType = 'none' | 'bbox' | 'mask';

export interface GeospatialMetadata {
  crs: string;
  image_bounds: [number, number, number, number]; // [min_lon, min_lat, max_lon, max_lat] in WGS84
  secondary_image_bounds?: [number, number, number, number] | null;
  geo_boxes?: [number, number][][] | null; // [[[lon, lat], ...]]
  all_images_geo?: Array<{ crs: string; bounds: [number, number, number, number] }> | null;
}

export interface VisualEvidence {
  type: VisualEvidenceType;
  boxes?: [number, number, number, number][] | null;
  mask_base64?: string | null;
  overlay_base64?: string | null;
  geospatial?: GeospatialMetadata | null;
}

export interface ExecutionSummary {
  selected_task: TaskType | string;
  tool_used: ToolUsed;
  parameters: Record<string, any>;
  inputs_validated: boolean;
  latency_ms: number;
}

export interface QueryImage {
  id: string;
  modality: Modality;
  date?: string; // ISO-8601 YYYY-MM-DD
  url_or_base64: string;
  asset_id?: string; // v2: uploaded asset (sent instead of url_or_base64)
  previewUrl?: string; // Client-side helper for thumbnails
  name?: string;
}

export interface QueryRequest {
  query: string;
  images: Array<{
    id: string;
    modality: Modality;
    date?: string;
    url_or_base64?: string;
    asset_id?: string;
  }>;
  session_id?: string;
}

export interface QueryResponse {
  answer: string;
  confidence: number;
  task: TaskType;
  visual_evidence: VisualEvidence;
  execution_summary: ExecutionSummary;
}

export type ErrorCode = 
  | 'INVALID_IMAGE_COUNT' 
  | 'INVALID_MODALITY_COMBINATION' 
  | 'UNSUPPORTED_FORMAT' 
  | 'MODEL_INFERENCE_FAILED' 
  | 'INTERNAL_ERROR'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'VALIDATION_ERROR'
  | 'PAYLOAD_TOO_LARGE'
  | string;

export interface ApiError {
  error: {
    code: ErrorCode;
    message: string;
    detail?: string;
  };
}

export interface HealthResponse {
  status: string;
  rsunivlm_loaded: boolean;
  fusion_loaded: boolean;
}

export interface AnalysisSession {
  id: string;
  title: string;
  timestamp: string;
  queryCount: number;
  imageCount: number;
  previewTask?: TaskType;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  query?: string;
  images?: QueryImage[];
  response?: QueryResponse;
  error?: {
    code: ErrorCode;
    message: string;
    detail?: string;
  };
  loading?: boolean;
  loadingStep?: string;
}

// ── API_CONTRACT.md v2 §5: auth, sessions, history ─────────────────────────
export interface User {
  id: string;
  email: string;
  role: 'user' | 'admin' | string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: User;
}

export interface SessionDto {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  query_count: number;
}

export interface HistoryEntry {
  id: string;
  query_text: string;
  created_at: string;
  status: 'success' | 'error';
  error_code?: string | null;
  image_asset_ids: string[];
  images: Array<{ asset_id: string; modality?: Modality | null; date?: string | null }>;
  response?: QueryResponse | null;
}
