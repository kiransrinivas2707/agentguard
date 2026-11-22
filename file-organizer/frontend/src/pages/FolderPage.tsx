import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { FileCard } from "../components/FileCard";
import { PreviewModal } from "../components/PreviewModal";
import type { FileItem, Folder } from "../types";

interface Props {
  folderId: string;
  folders: Folder[];
  onChanged: () => void;
  notify: (message: string, kind?: "ok" | "error") => void;
  onNavigate: (route: string) => void;
}

export function FolderPage({ folderId, folders, onChanged, notify, onNavigate }: Props) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<FileItem | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const folder = folders.find((entry) => entry.id === folderId);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setFiles(await api.files({ folderId }));
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not load folder", "error");
    } finally {
      setLoading(false);
    }
  }, [folderId, notify]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  const remove = async (file: FileItem) => {
    if (!window.confirm(`Move "${file.current_name}" to Trash? You can restore it later.`)) return;
    try {
      await api.trashFile(file.id);
      setFiles((current) => current.filter((entry) => entry.id !== file.id));
      onChanged();
      notify("Moved to Trash");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not delete file", "error");
    }
  };

  const createFolder = async (event: FormEvent) => {
    event.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await api.createFolder(newName.trim(), folderId);
      setNewName("");
      onChanged();
      notify("Folder created");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not create folder", "error");
    } finally {
      setCreating(false);
    }
  };

  if (!folder) {
    return (
      <div className="page">
        <div className="empty">
          <p>This folder is no longer available.</p>
          <button type="button" className="btn primary" onClick={() => onNavigate("inbox")}>
            Back to Inbox
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="breadcrumb muted small">
        {folder.path.map((segment, index) => (
          <span key={`${segment}-${index}`}>
            {index > 0 && <span aria-hidden="true"> / </span>}
            {segment}
          </span>
        ))}
      </div>

      <div className="section-heading">
        <h2>{folder.name}</h2>
        <div className="button-row">
          <span className="muted small">{files.length} file{files.length === 1 ? "" : "s"}</span>
          <button type="button" className="btn ghost small" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      <form className="inline-form" onSubmit={createFolder}>
        <label className="visually-hidden" htmlFor="new-folder">
          New subfolder name
        </label>
        <input
          id="new-folder"
          value={newName}
          onChange={(event) => setNewName(event.target.value)}
          placeholder="New subfolder name"
          maxLength={60}
        />
        <button type="submit" className="btn ghost small" disabled={creating || !newName.trim()}>
          {creating ? "Creating…" : "Add subfolder"}
        </button>
      </form>

      {loading ? (
        <p className="muted">Loading…</p>
      ) : files.length === 0 ? (
        <div className="empty">
          <p>This folder is empty. Approve files from Needs Review to organize them here.</p>
        </div>
      ) : (
        <div className="file-list">
          {files.map((file) => (
            <FileCard key={file.id} file={file} onPreview={setPreview} onDelete={remove} />
          ))}
        </div>
      )}

      {preview && <PreviewModal file={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
