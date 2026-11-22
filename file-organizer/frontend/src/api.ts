import type {
  ApprovePayload,
  ApproveResponse,
  BatchResult,
  FileItem,
  Folder,
  ImportSources,
  LocalImportResponse,
  Operation,
  Preferences,
  SearchResponse,
  Stats,
  UndoResponse,
  UploadResponse,
  User,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
      else if (Array.isArray(body?.detail)) message = body.detail[0]?.msg ?? message;
    } catch {
      // keep the status-based message
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  me: () => request<User>("/api/auth/me"),
  login: (email: string, password: string) =>
    request<User>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string) =>
    request<User>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<{ message: string }>("/api/auth/logout", { method: "POST" }),

  files: (params: { folderId?: string; status?: string; limit?: number } = {}) => {
    const search = new URLSearchParams();
    if (params.folderId) search.set("folder_id", params.folderId);
    if (params.status) search.set("status", params.status);
    search.set("limit", String(params.limit ?? 200));
    return request<FileItem[]>(`/api/files?${search.toString()}`);
  },
  file: (id: string) => request<FileItem>(`/api/files/${id}`),
  fileText: (id: string) => request<{ text: string }>(`/api/files/${id}/text`),
  classify: (id: string) => request<{ message: string }>(`/api/files/${id}/classify`, { method: "POST" }),

  folders: () => request<Folder[]>("/api/folders"),
  createFolder: (name: string, parentId?: string | null) =>
    request<Folder>("/api/folders", {
      method: "POST",
      body: JSON.stringify({ name, parent_id: parentId ?? null }),
    }),

  review: () => request<FileItem[]>("/api/review"),
  approve: (payload: ApprovePayload) =>
    request<ApproveResponse>(`/api/review/${payload.file_id}/approve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reject: (id: string) => request<FileItem>(`/api/review/${id}/reject`, { method: "POST" }),
  approveBatch: (items: ApprovePayload[]) =>
    request<{ results: BatchResult[] }>("/api/review/approve-batch", {
      method: "POST",
      body: JSON.stringify({ items }),
    }),

  search: (params: {
    q: string;
    documentType?: string;
    category?: string;
    year?: string;
  }) => {
    const search = new URLSearchParams();
    search.set("q", params.q);
    if (params.documentType) search.set("document_type", params.documentType);
    if (params.category) search.set("category", params.category);
    if (params.year) search.set("year", params.year);
    return request<SearchResponse>(`/api/search?${search.toString()}`);
  },

  operations: () => request<Operation[]>("/api/operations"),
  undo: (id: string) => request<UndoResponse>(`/api/operations/${id}/undo`, { method: "POST" }),
  stats: () => request<Stats>("/api/files/stats/summary"),

  preferences: () => request<Preferences>("/api/preferences"),
  updatePreferences: (body: { auto_organize_enabled?: boolean; auto_organize_threshold?: number }) =>
    request<Preferences>("/api/preferences", { method: "PATCH", body: JSON.stringify(body) }),
  importSources: () => request<ImportSources>("/api/import/sources"),
  importLocal: (body: { path: string; recursive: boolean; classify: boolean }) =>
    request<LocalImportResponse>("/api/import/local", { method: "POST", body: JSON.stringify(body) }),
  runAutomation: () =>
    request<{ organized: number; skipped: number; failed: number }>("/api/automation/run", {
      method: "POST",
    }),
  cleanupEmptyFolders: () =>
    request<{ removed: number }>("/api/folders/cleanup-empty", { method: "POST" }),
  trashFile: (id: string) => request<FileItem>(`/api/files/${id}`, { method: "DELETE" }),
  trashList: () => request<FileItem[]>("/api/trash"),
  restoreTrash: (id: string) =>
    request<FileItem>(`/api/trash/${id}/restore`, { method: "POST" }),
  purgeTrash: (id: string) =>
    request<{ message: string }>(`/api/trash/${id}`, { method: "DELETE" }),
};

export function uploadFiles(files: File[], onProgress?: (percent: number) => void): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/files");
    xhr.withCredentials = true;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onerror = () => reject(new ApiError("Upload failed. Check your connection.", 0));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as UploadResponse);
      } else {
        const detail =
          body && typeof body === "object" && "detail" in body
            ? String((body as { detail: unknown }).detail)
            : `Upload failed (${xhr.status})`;
        reject(new ApiError(detail, xhr.status));
      }
    };
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    xhr.send(form);
  });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function fileExtension(name: string): string {
  const index = name.lastIndexOf(".");
  return index > 0 ? name.slice(index + 1).toLowerCase() : "";
}
