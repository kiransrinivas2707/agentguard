import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { PreviewModal } from "../components/PreviewModal";
import {
  ReviewCard,
  draftFromFile,
  payloadFromDraft,
  type ReviewDraft,
} from "../components/ReviewCard";
import type { ApprovePayload, FileItem, Folder } from "../types";

interface Props {
  folders: Folder[];
  onChanged: () => void;
  notify: (message: string, kind?: "ok" | "error") => void;
}

export function ReviewPage({ folders, onChanged, notify }: Props) {
  const [items, setItems] = useState<FileItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchErrors, setBatchErrors] = useState<string[]>([]);
  const [preview, setPreview] = useState<FileItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.review();
      setItems(data);
      const next: Record<string, ReviewDraft> = {};
      for (const item of data) next[item.id] = draftFromFile(item);
      setDrafts(next);
      setSelected(new Set());
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not load review queue", "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const removeItem = (id: string) => {
    setItems((current) => current.filter((item) => item.id !== id));
    setSelected((current) => {
      const next = new Set(current);
      next.delete(id);
      return next;
    });
  };

  const approve = async (payload: ApprovePayload) => {
    setBusyId(payload.file_id);
    try {
      const response = await api.approve(payload);
      removeItem(payload.file_id);
      onChanged();
      notify(`Organized as ${response.file.current_name} in ${response.file.folder_path.join(" / ")}`);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not organize file", "error");
    } finally {
      setBusyId(null);
    }
  };

  const reject = async (id: string) => {
    setBusyId(id);
    try {
      await api.reject(id);
      removeItem(id);
      onChanged();
      notify("Kept in Inbox");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not reject file", "error");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (file: FileItem) => {
    if (!window.confirm(`Move "${file.current_name}" to Trash? You can restore it later.`)) return;
    setBusyId(file.id);
    try {
      await api.trashFile(file.id);
      removeItem(file.id);
      onChanged();
      notify("Moved to Trash");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not delete file", "error");
    } finally {
      setBusyId(null);
    }
  };

  const batchApprove = async () => {
    const chosen = items.filter((item) => selected.has(item.id));
    if (chosen.length === 0) return;
    setBatchBusy(true);
    setBatchErrors([]);
    try {
      const payloads = chosen.map((item) => payloadFromDraft(item, drafts[item.id] ?? draftFromFile(item)));
      const response = await api.approveBatch(payloads);
      const failures = response.results.filter((result) => !result.ok);
      for (const result of response.results.filter((entry) => entry.ok)) removeItem(result.file_id);
      const okCount = response.results.length - failures.length;
      if (okCount > 0) notify(`${okCount} file${okCount === 1 ? "" : "s"} organized`);
      if (failures.length > 0) {
        setBatchErrors(failures.map((failure) => `${failure.file_id}: ${failure.error ?? "failed"}`));
      }
      onChanged();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Batch approval failed", "error");
    } finally {
      setBatchBusy(false);
    }
  };

  const allSelected = items.length > 0 && selected.size === items.length;
  const selectedCount = selected.size;

  const draftFor = useMemo(
    () => (item: FileItem) => drafts[item.id] ?? draftFromFile(item),
    [drafts],
  );

  return (
    <div className="page">
      <div className="section-heading">
        <div>
          <h2>Needs Review</h2>
          <p className="muted small">Approve the proposal, edit it, or keep the file in Inbox.</p>
        </div>
        <div className="batch-actions">
          <button type="button" className="btn ghost small" onClick={() => void load()} disabled={loading || batchBusy}>
            Refresh
          </button>
          <label className="check inline">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={(event) =>
                setSelected(event.target.checked ? new Set(items.map((item) => item.id)) : new Set())
              }
              aria-label="Select all files"
            />
            Select all
          </label>
          <button
            type="button"
            className="btn primary small"
            disabled={selectedCount === 0 || batchBusy}
            onClick={batchApprove}
          >
            {batchBusy ? "Organizing…" : `Approve selected${selectedCount ? ` (${selectedCount})` : ""}`}
          </button>
        </div>
      </div>

      {batchErrors.length > 0 && (
        <div className="callout error" role="alert">
          <strong>Some files could not be organized</strong>
          <ul>
            {batchErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      )}

      {loading ? (
        <p className="muted">Loading…</p>
      ) : items.length === 0 ? (
        <div className="empty">
          <span aria-hidden="true">✓</span>
          <p>Nothing to review. Upload files to Inbox and they will appear here with a proposal.</p>
        </div>
      ) : (
        <div className="review-list">
          {items.map((item) => (
            <ReviewCard
              key={item.id}
              item={item}
              draft={draftFor(item)}
              folders={folders}
              selected={selected.has(item.id)}
              busy={busyId === item.id || batchBusy}
              onDraftChange={(id, patch) =>
                setDrafts((current) => ({
                  ...current,
                  [id]: { ...(current[id] ?? draftFromFile(item)), ...patch },
                }))
              }
              onSelect={(id, isSelected) =>
                setSelected((current) => {
                  const next = new Set(current);
                  if (isSelected) next.add(id);
                  else next.delete(id);
                  return next;
                })
              }
              onApprove={approve}
              onReject={reject}
              onDelete={remove}
              onPreview={setPreview}
            />
          ))}
        </div>
      )}

      {preview && <PreviewModal file={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
