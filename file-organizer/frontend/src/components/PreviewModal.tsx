import { useEffect, useRef, useState } from "react";
import { api, formatBytes } from "../api";
import type { FileItem } from "../types";

interface Props {
  file: FileItem;
  onClose: () => void;
}

export function PreviewModal({ file, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const isImage = file.mime_type.startsWith("image/");
  const isPdf = file.mime_type === "application/pdf";
  const isText = file.mime_type.startsWith("text/") || file.mime_type === "application/json";

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (isImage || isPdf) return;
    let active = true;
    setLoading(true);
    setError("");
    api
      .fileText(file.id)
      .then((response) => {
        if (active) setText(response.text);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Preview unavailable");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [file.id, isImage, isPdf]);

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="preview-title">
        <header className="modal-header">
          <div>
            <h2 id="preview-title">{file.current_name}</h2>
            <p className="muted small">
              {formatBytes(file.size)} · {file.mime_type} · {file.folder_path.join(" / ") || "Inbox"}
            </p>
          </div>
          <button ref={closeRef} type="button" className="btn ghost" onClick={onClose} aria-label="Close preview">
            ✕
          </button>
        </header>

        <div className="preview-body">
          {isImage && <img src={`/api/files/${file.id}/content`} alt={`Preview of ${file.current_name}`} />}
          {isPdf && (
            <iframe title={`Preview of ${file.current_name}`} src={`/api/files/${file.id}/content`} />
          )}
          {!isImage && !isPdf && (
            <>
              {loading && <p className="muted">Loading extracted text…</p>}
              {error && <p className="form-error">{error}</p>}
              {!loading && !error && (
                <pre className="text-preview">
                  {text.trim() || "No extractable text. This file type may not support preview."}
                </pre>
              )}
            </>
          )}
        </div>

        <footer className="modal-footer">
          <span className="muted small">{isText ? "Extracted text" : "Read-only preview"}</span>
          {(isImage || isPdf || isText) && (
            <a className="btn ghost" href={`/api/files/${file.id}/content`} download={file.current_name}>
              Download
            </a>
          )}
        </footer>
      </section>
    </div>
  );
}
