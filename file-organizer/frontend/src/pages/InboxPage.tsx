import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { FileCard } from "../components/FileCard";
import { PreviewModal } from "../components/PreviewModal";
import { UploadZone } from "../components/UploadZone";
import type { FileItem, UploadResponse } from "../types";

interface Props {
  inboxId: string | null;
  onChanged: () => void;
  notify: (message: string, kind?: "ok" | "error") => void;
}

export function InboxPage({ inboxId, onChanged, notify }: Props) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<FileItem | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!inboxId) return;
    try {
      const data = await api.files({ folderId: inboxId });
      setFiles(data);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not load Inbox", "error");
    } finally {
      setLoading(false);
    }
  }, [inboxId, notify]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  useEffect(() => {
    if (!files.some((file) => file.status === "inbox")) return;
    const timer = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(timer);
  }, [files, load]);

  const uploaded = (response: UploadResponse) => {
    const count = response.uploaded.length;
    if (count > 0) notify(`${count} file${count === 1 ? "" : "s"} added to Inbox`);
    onChanged();
    void load();
  };

  const classify = async (file: FileItem) => {
    setBusyId(file.id);
    try {
      await api.classify(file.id);
      notify("Classification queued");
      void load();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not classify", "error");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (file: FileItem) => {
    if (!window.confirm(`Move "${file.current_name}" to Trash? You can restore it later.`)) return;
    setBusyId(file.id);
    try {
      await api.trashFile(file.id);
      setFiles((current) => current.filter((entry) => entry.id !== file.id));
      onChanged();
      notify("Moved to Trash");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not delete file", "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="page">
      <UploadZone onUploaded={uploaded} onError={(message) => notify(message, "error")} />

      <section aria-labelledby="inbox-heading">
        <div className="section-heading">
          <h2 id="inbox-heading">Inbox</h2>
          <span className="muted small">{files.length} file{files.length === 1 ? "" : "s"}</span>
        </div>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : files.length === 0 ? (
          <div className="empty">
            <span aria-hidden="true">◌</span>
            <p>Your Inbox is empty. Drop files above to get started.</p>
          </div>
        ) : (
          <div className="file-list">
            {files.map((file) => (
              <div key={file.id} className={busyId === file.id ? "busy" : ""}>
                <FileCard file={file} onPreview={setPreview} onClassify={classify} onDelete={remove} />
              </div>
            ))}
          </div>
        )}
      </section>

      {preview && <PreviewModal file={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
