import { useCallback, useEffect, useState } from "react";
import { api, formatBytes } from "../api";
import { fileIcon } from "../components/FileCard";
import { PreviewModal } from "../components/PreviewModal";
import type { FileItem } from "../types";

interface Props {
  onChanged: () => void;
  notify: (message: string, kind?: "ok" | "error") => void;
}

export function TrashPage({ onChanged, notify }: Props) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [preview, setPreview] = useState<FileItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setFiles(await api.trashList());
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not load Trash", "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const restore = async (file: FileItem) => {
    setBusyId(file.id);
    try {
      const restored = await api.restoreTrash(file.id);
      setFiles((current) => current.filter((entry) => entry.id !== file.id));
      onChanged();
      notify(`Restored to ${restored.folder_path.join(" / ")}`);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not restore file", "error");
    } finally {
      setBusyId(null);
    }
  };

  const purge = async (file: FileItem) => {
    if (
      !window.confirm(
        `Permanently delete "${file.current_name}"? This cannot be undone.`,
      )
    ) {
      return;
    }
    setBusyId(file.id);
    try {
      await api.purgeTrash(file.id);
      setFiles((current) => current.filter((entry) => entry.id !== file.id));
      onChanged();
      notify("File permanently deleted");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not delete file", "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="page">
      <div className="section-heading">
        <div>
          <h2>Trash</h2>
          <p className="muted small">
            Deleted files are kept here until you restore them or delete them permanently.
          </p>
        </div>
      </div>

      {loading ? (
        <p className="muted">Loading…</p>
      ) : files.length === 0 ? (
        <div className="empty">
          <span aria-hidden="true">🗑</span>
          <p>Trash is empty.</p>
        </div>
      ) : (
        <div className="file-list">
          {files.map((file) => (
            <article key={file.id} className={busyId === file.id ? "file-card busy" : "file-card"}>
              <div className="file-icon" aria-hidden="true">
                {fileIcon(file)}
              </div>
              <div className="file-body">
                <div className="file-title-row">
                  <h3>{file.current_name}</h3>
                  <span className="badge status-trashed">In Trash</span>
                </div>
                <p className="muted small">
                  {formatBytes(file.size)} · {file.mime_type}
                  {file.folder_path.length > 0 && <> · was in {file.folder_path.join(" / ")}</>}
                </p>
              </div>
              <div className="file-actions">
                <button type="button" className="btn ghost small" onClick={() => setPreview(file)}>
                  Preview
                </button>
                <button
                  type="button"
                  className="btn ghost small"
                  disabled={busyId === file.id}
                  onClick={() => restore(file)}
                >
                  Restore
                </button>
                <button
                  type="button"
                  className="btn danger-ghost small"
                  disabled={busyId === file.id}
                  onClick={() => purge(file)}
                >
                  Delete permanently
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      {preview && <PreviewModal file={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
