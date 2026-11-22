export type FileStatus =
  | "inbox"
  | "classified"
  | "needs_review"
  | "organized"
  | "unsupported"
  | "failed"
  | "trashed";

export interface Classification {
  id: string;
  document_type: string;
  category: string;
  subcategory: string | null;
  tags: string[];
  suggested_name: string;
  suggested_path: string[];
  date_candidates: string[];
  entities: string[];
  confidence: number;
  rationale: string;
  requires_review: boolean;
  provider: string;
  model: string;
  error: string | null;
  applied: boolean;
  rejected: boolean;
  created_at: string;
}

export interface FileItem {
  id: string;
  original_name: string;
  current_name: string;
  mime_type: string;
  size: number;
  sha256: string;
  status: FileStatus;
  extraction_status: string;
  folder_id: string;
  folder_path: string[];
  duplicate_of_id: string | null;
  created_at: string;
  updated_at: string;
  classification: Classification | null;
}

export interface Folder {
  id: string;
  name: string;
  parent_id: string | null;
  is_system: boolean;
  path: string[];
  file_count: number;
}

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface OperationItem {
  id: string;
  file_id: string;
  from_path: string;
  to_path: string;
  from_name: string;
  to_name: string;
  status: string;
}

export interface Operation {
  id: string;
  kind: string;
  status: string;
  created_at: string;
  undone_at: string | null;
  items: OperationItem[];
}

export interface Stats {
  inbox: number;
  needs_review: number;
  organized: number;
  unsupported: number;
  trashed: number;
  total: number;
}

export interface UploadResponse {
  uploaded: FileItem[];
  errors: { filename: string; error: string }[];
}

export interface SearchHit {
  file: FileItem;
  snippet: string;
}

export interface SearchResponse {
  query: string;
  total: number;
  hits: SearchHit[];
}

export interface ApprovePayload {
  file_id: string;
  name?: string;
  path?: string[];
  tags?: string[];
  document_type?: string;
  category?: string;
  subcategory?: string | null;
}

export interface ApproveResponse {
  file: FileItem;
  operation_id: string;
}

export interface BatchResult {
  file_id: string;
  ok: boolean;
  operation_id: string | null;
  error: string | null;
}

export interface UndoResponse {
  operation: Operation;
  errors: string[];
}

export interface Preferences {
  auto_organize_enabled: boolean;
  auto_organize_threshold: number;
  scan_roots: string[];
  google_drive: string;
  google_photos: string;
}

export interface ImportSources {
  local_roots: string[];
  google_drive: string;
  google_photos: string;
}

export interface LocalImportResponse {
  path: string;
  uploaded: FileItem[];
  errors: { filename: string; error: string }[];
  skipped: number;
}
