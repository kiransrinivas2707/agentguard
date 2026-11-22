import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { PreviewModal } from "../components/PreviewModal";
import { fileIcon, statusLabel } from "../components/FileCard";
import type { FileItem, SearchResponse } from "../types";

const DOCUMENT_TYPES = [
  "certificate",
  "resume",
  "invoice",
  "receipt",
  "identity_document",
  "photo",
  "screenshot",
  "letter",
  "report",
  "notes",
  "other",
];

function Snippet({ text }: { text: string }) {
  if (!text) return null;
  const parts = text.split(/(\[[^\]]*\])/g);
  return (
    <p className="snippet">
      {parts.map((part, index) =>
        part.startsWith("[") && part.endsWith("]") ? (
          <mark key={index}>{part.slice(1, -1)}</mark>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </p>
  );
}

interface Props {
  notify: (message: string, kind?: "ok" | "error") => void;
}

export function SearchPage({ notify }: Props) {
  const [query, setQuery] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [category, setCategory] = useState("");
  const [year, setYear] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<FileItem | null>(null);

  const runSearch = async (event?: FormEvent) => {
    event?.preventDefault();
    setLoading(true);
    try {
      const response = await api.search({ q: query, documentType, category, year });
      setResults(response);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Search failed", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void runSearch();
    // Run once so the page is useful before the first query.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page">
      <div className="section-heading">
        <div>
          <h2>Search</h2>
          <p className="muted small">Search names, extracted text, tags, categories, and folder paths.</p>
        </div>
      </div>

      <form className="search-form" onSubmit={runSearch} role="search">
        <label className="field grow">
          <span>Search your files</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. latest resume, invoices from last year, AWS certificate"
          />
        </label>
        <label className="field">
          <span>Type</span>
          <select value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
            <option value="">Any</option>
            {DOCUMENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Category</span>
          <input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Finance" />
        </label>
        <label className="field">
          <span>Year</span>
          <input
            inputMode="numeric"
            value={year}
            onChange={(event) => setYear(event.target.value.replace(/\D/g, "").slice(0, 4))}
            placeholder="2024"
          />
        </label>
        <button type="submit" className="btn primary" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {results && (
        <p className="muted small" role="status">
          {results.total} result{results.total === 1 ? "" : "s"}
          {results.query ? ` for “${results.query}”` : ""}
        </p>
      )}

      {results && results.hits.length === 0 ? (
        <div className="empty">
          <span aria-hidden="true">⌕</span>
          <p>No files matched. Try a broader phrase or clear the filters.</p>
        </div>
      ) : (
        <div className="file-list">
          {results?.hits.map((hit) => (
            <article key={hit.file.id} className="file-card">
              <div className="file-icon" aria-hidden="true">
                {fileIcon(hit.file)}
              </div>
              <div className="file-body">
                <div className="file-title-row">
                  <h3>{hit.file.current_name}</h3>
                  <span className={`badge status-${hit.file.status}`}>{statusLabel(hit.file.status)}</span>
                </div>
                <p className="muted small">{hit.file.folder_path.join(" / ")}</p>
                <Snippet text={hit.snippet} />
              </div>
              <div className="file-actions">
                <button type="button" className="btn ghost small" onClick={() => setPreview(hit.file)}>
                  Preview
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
