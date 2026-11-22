import { useMemo } from "react";
import type { ApprovePayload, FileItem, Folder } from "../types";

export interface ReviewDraft {
  name: string;
  pathText: string;
  tags: string;
}

interface Props {
  item: FileItem;
  draft: ReviewDraft;
  folders: Folder[];
  selected: boolean;
  busy: boolean;
  onDraftChange: (id: string, patch: Partial<ReviewDraft>) => void;
  onSelect: (id: string, selected: boolean) => void;
  onApprove: (payload: ApprovePayload) => void;
  onReject: (id: string) => void;
  onDelete: (file: FileItem) => void;
  onPreview: (file: FileItem) => void;
}

export function draftFromFile(item: FileItem): ReviewDraft {
  return {
    name: item.classification?.suggested_name ?? item.current_name,
    pathText: (item.classification?.suggested_path ?? []).join(" / "),
    tags: (item.classification?.tags ?? []).join(", "),
  };
}

export function payloadFromDraft(item: FileItem, draft: ReviewDraft): ApprovePayload {
  const path = draft.pathText
    .split("/")
    .map((segment) => segment.trim())
    .filter(Boolean);
  const payload: ApprovePayload = {
    file_id: item.id,
    name: draft.name.trim() || item.current_name,
    path,
  };
  const originalTags = (item.classification?.tags ?? []).join(", ");
  if (draft.tags.trim() !== originalTags.trim()) {
    payload.tags = draft.tags
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
  }
  return payload;
}

export function ReviewCard({
  item,
  draft,
  folders,
  selected,
  busy,
  onDraftChange,
  onSelect,
  onApprove,
  onReject,
  onDelete,
  onPreview,
}: Props) {
  const classification = item.classification;
  const confidence = Math.round((classification?.confidence ?? 0) * 100);

  const proposedPath = useMemo(
    () =>
      draft.pathText
        .split("/")
        .map((segment) => segment.trim())
        .filter(Boolean),
    [draft.pathText],
  );

  const newFolders = useMemo(() => {
    const existing = new Set(folders.map((folder) => folder.path.join("/").toLowerCase()));
    const missing: string[] = [];
    let current = "";
    for (const segment of proposedPath) {
      current = current ? `${current}/${segment}` : segment;
      if (!existing.has(current.toLowerCase())) missing.push(current);
    }
    return missing;
  }, [folders, proposedPath]);

  return (
    <article className={selected ? "review-card selected" : "review-card"}>
      <div className="review-top">
        <label className="check">
          <input
            type="checkbox"
            checked={selected}
            onChange={(event) => onSelect(item.id, event.target.checked)}
            aria-label={`Select ${item.current_name}`}
          />
        </label>
        <div className="file-icon" aria-hidden="true">
          {item.mime_type.startsWith("image/") ? "▧" : item.mime_type === "application/pdf" ? "▤" : "▦"}
        </div>
        <div className="review-heading">
          <h3>{item.original_name}</h3>
          <p className="muted small">
            {classification ? classification.document_type.replace(/_/g, " ") : "No classification"} ·{" "}
            {classification ? classification.rationale : "Manual review"}
          </p>
        </div>
        <div className="confidence-block" title="Model confidence">
          <span className={confidence >= 75 ? "confidence high" : confidence >= 50 ? "confidence medium" : "confidence low"}>
            {confidence}%
          </span>
          <div className="confidence-track" aria-hidden="true">
            <span style={{ width: `${confidence}%` }} />
          </div>
        </div>
      </div>

      <div className="review-grid">
        <label className="field">
          <span>Filename</span>
          <input
            value={draft.name}
            onChange={(event) => onDraftChange(item.id, { name: event.target.value })}
            maxLength={255}
          />
        </label>
        <label className="field">
          <span>Folder path</span>
          <input
            value={draft.pathText}
            onChange={(event) => onDraftChange(item.id, { pathText: event.target.value })}
            placeholder="Career / Resumes"
            list={`folder-options-${item.id}`}
            aria-describedby={`path-help-${item.id}`}
          />
        </label>
        <label className="field">
          <span>Tags</span>
          <input
            value={draft.tags}
            onChange={(event) => onDraftChange(item.id, { tags: event.target.value })}
            placeholder="resume, cloud"
          />
        </label>
      </div>
      <datalist id={`folder-options-${item.id}`}>
        {folders.map((folder) => (
          <option key={folder.id} value={folder.path.join(" / ")} />
        ))}
      </datalist>

      <p id={`path-help-${item.id}`} className="muted small">
        Original → <strong>{item.current_name}</strong> → <strong>{draft.name || item.current_name}</strong> in{" "}
        <strong>{proposedPath.length ? proposedPath.join(" / ") : "Inbox"}</strong>.
      </p>
      {newFolders.length > 0 && (
        <p className="info small">
          <span aria-hidden="true">＋</span> Creates folder{newFolders.length > 1 ? "s" : ""}: {newFolders.join(", ")}
        </p>
      )}
      {classification?.error && <p className="form-error small">{classification.error}</p>}

      <div className="review-actions">
        <button type="button" className="btn ghost small" onClick={() => onPreview(item)}>
          Preview
        </button>
        <button type="button" className="btn danger-ghost small" disabled={busy} onClick={() => onReject(item.id)}>
          Keep in Inbox
        </button>
        <button type="button" className="btn danger-ghost small" disabled={busy} onClick={() => onDelete(item)}>
          Delete
        </button>
        <button
          type="button"
          className="btn primary small"
          disabled={busy}
          onClick={() => onApprove(payloadFromDraft(item, draft))}
        >
          {busy ? "Organizing…" : "Approve & organize"}
        </button>
      </div>
    </article>
  );
}
