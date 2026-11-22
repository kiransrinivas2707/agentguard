import { useRef, useState } from "react";
import { uploadFiles } from "../api";
import type { UploadResponse } from "../types";

interface Props {
  onUploaded: (response: UploadResponse) => void;
  onError: (message: string) => void;
}

const ACCEPT = ".txt,.md,.markdown,.csv,.log,.json,.yaml,.yml,.pdf,.docx,.png,.jpg,.jpeg,.gif,.webp,.bmp,.tiff";

export function UploadZone({ onUploaded, onError }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [errors, setErrors] = useState<string[]>([]);

  const send = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setBusy(true);
    setErrors([]);
    setProgress(0);
    try {
      const response = await uploadFiles(list, setProgress);
      setErrors(response.errors.map((item) => `${item.filename}: ${item.error}`));
      onUploaded(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setErrors([message]);
      onError(message);
    } finally {
      setBusy(false);
      setProgress(0);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <section
      className={dragging ? "dropzone dragging" : "dropzone"}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        void send(event.dataTransfer.files);
      }}
      aria-label="Upload files"
    >
      <div className="dropzone-icon" aria-hidden="true">
        ⤒
      </div>
      <div>
        <strong>Drop files here, or choose files</strong>
        <p className="muted small">
          PDF, DOCX, TXT, Markdown, CSV and images. Up to 25 MB per file. Every move needs your approval.
        </p>
      </div>
      <input
        ref={inputRef}
        id="file-input"
        type="file"
        multiple
        accept={ACCEPT}
        className="visually-hidden"
        onChange={(event) => {
          if (event.target.files) void send(event.target.files);
        }}
      />
      <input
        ref={folderInputRef}
        id="folder-input"
        type="file"
        multiple
        accept={ACCEPT}
        className="visually-hidden"
        {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
        onChange={(event) => {
          if (event.target.files) void send(event.target.files);
        }}
      />
      <div className="upload-actions">
        <button type="button" className="btn primary" disabled={busy} onClick={() => inputRef.current?.click()}>
          {busy ? "Uploading…" : "Choose files"}
        </button>
        <button
          type="button"
          className="btn ghost"
          disabled={busy}
          onClick={() => folderInputRef.current?.click()}
        >
          Upload folder
        </button>
      </div>
      {busy && (
        <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
          <span style={{ width: `${progress}%` }} />
        </div>
      )}
      {errors.length > 0 && (
        <ul className="upload-errors" role="alert">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
