import { formatBytes } from "../api";
import type { FileItem } from "../types";

interface Props {
  file: FileItem;
  onPreview: (file: FileItem) => void;
  onClassify?: (file: FileItem) => void;
  onDelete?: (file: FileItem) => void;
  compact?: boolean;
}

export function statusLabel(status: string): string {
  switch (status) {
    case "inbox":
      return "In Inbox";
    case "classified":
      return "Ready to review";
    case "needs_review":
      return "Needs review";
    case "organized":
      return "Organized";
    case "unsupported":
      return "Unsupported";
    case "failed":
      return "Failed";
    case "trashed":
      return "In Trash";
    default:
      return status;
  }
}

export function fileIcon(file: FileItem): string {
  if (file.mime_type.startsWith("image/")) return "▧";
  if (file.mime_type === "application/pdf") return "▤";
  if (file.mime_type.includes("wordprocessingml")) return "▥";
  if (file.mime_type.startsWith("text/")) return "▦";
  return "▩";
}

export function FileCard({ file, onPreview, onClassify, onDelete, compact }: Props) {
  const classification = file.classification;
  const confidence = classification ? Math.round(classification.confidence * 100) : null;
  const canAnalyze = file.status === "inbox" || file.status === "failed" || file.status === "needs_review";

  return (
    <article className={compact ? "file-card compact" : "file-card"}>
      <div className="file-icon" aria-hidden="true">
        {fileIcon(file)}
      </div>
      <div className="file-body">
        <div className="file-title-row">
          <h3 title={file.current_name}>{file.current_name}</h3>
          <span className={`badge status-${file.status}`}>{statusLabel(file.status)}</span>
        </div>
        <p className="muted small">
          {formatBytes(file.size)} · {file.mime_type}
          {file.folder_path.length > 0 && <> · {file.folder_path.join(" / ")}</>}
        </p>
        {file.duplicate_of_id && (
          <p className="warning small">
            <span aria-hidden="true">⚠</span> Exact duplicate of another file. Nothing was deleted.
          </p>
        )}
        {classification && (
          <div className="proposal-summary">
            <span>
              {classification.document_type.replace(/_/g, " ")} →{" "}
              <strong>{classification.suggested_path.length ? classification.suggested_path.join(" / ") : "Inbox"}</strong>
            </span>
            {confidence !== null && (
              <span className="confidence small" title="Model confidence">
                {confidence}% confidence
              </span>
            )}
          </div>
        )}
        {classification?.error && <p className="form-error small">{classification.error}</p>}
      </div>
      <div className="file-actions">
        <button type="button" className="btn ghost small" onClick={() => onPreview(file)}>
          Preview
        </button>
        {onClassify && canAnalyze && (
          <button type="button" className="btn ghost small" onClick={() => onClassify(file)}>
            {file.status === "needs_review" ? "Retry analysis" : "Analyze"}
          </button>
        )}
        {onDelete && (
          <button type="button" className="btn danger-ghost small" onClick={() => onDelete(file)}>
            Delete
          </button>
        )}
      </div>
    </article>
  );
}
