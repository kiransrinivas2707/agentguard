import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import type { LocalImportResponse, Preferences } from "../types";

interface Props {
  onChanged: () => void;
  notify: (message: string, kind?: "ok" | "error") => void;
}

function googleLabel(status: string | undefined): string {
  if (status === "oauth_ready") return "OAuth credentials detected; connector not enabled yet";
  return "Not configured";
}

export function SettingsPage({ onChanged, notify }: Props) {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [threshold, setThreshold] = useState(80);
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [importPath, setImportPath] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<LocalImportResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [cleaning, setCleaning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.preferences();
      setPreferences(data);
      setEnabled(data.auto_organize_enabled);
      setThreshold(Math.round(data.auto_organize_threshold * 100));
      if (!importPath && data.scan_roots[0]) setImportPath(data.scan_roots[0]);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not load settings", "error");
    } finally {
      setLoading(false);
    }
  }, [importPath, notify]);

  useEffect(() => {
    void load();
    // Load once; importPath is intentionally not a dependency after the first fill.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.updatePreferences({
        auto_organize_enabled: enabled,
        auto_organize_threshold: threshold / 100,
      });
      setPreferences(updated);
      notify(`Automation saved: ${enabled ? `auto-organize at ${threshold}%` : "review everything"}`);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not save settings", "error");
    } finally {
      setSaving(false);
    }
  };

  const runImport = async (event: FormEvent) => {
    event.preventDefault();
    setImporting(true);
    setImportResult(null);
    try {
      const result = await api.importLocal({ path: importPath.trim(), recursive, classify: true });
      setImportResult(result);
      onChanged();
      const count = result.uploaded.length;
      if (count > 0) notify(`${count} file${count === 1 ? "" : "s"} imported`);
      if (result.errors.length > 0) notify("Some files could not be imported", "error");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Import failed", "error");
    } finally {
      setImporting(false);
    }
  };

  const runNow = async () => {
    setRunning(true);
    try {
      const result = await api.runAutomation();
      onChanged();
      notify(`Organized ${result.organized} eligible file${result.organized === 1 ? "" : "s"}`);
      if (result.failed > 0) notify(`${result.failed} file(s) could not be organized`, "error");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Automatic organization failed", "error");
    } finally {
      setRunning(false);
    }
  };

  const cleanupEmpty = async () => {
    setCleaning(true);
    try {
      const result = await api.cleanupEmptyFolders();
      onChanged();
      notify(`Removed ${result.removed} empty folder${result.removed === 1 ? "" : "s"}`);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not clean up folders", "error");
    } finally {
      setCleaning(false);
    }
  };

  if (loading || !preferences) {
    return <div className="page"><p className="muted">Loading settings…</p></div>;
  }

  return (
    <div className="page settings-page">
      <section className="panel" aria-labelledby="automation-heading">
        <div className="panel-heading">
          <div>
            <h2 id="automation-heading">Automatic organization</h2>
            <p className="muted small">
              Known file types at or above the threshold are moved without approval. Every move is
              recorded and can be undone. Unknown types always stay in review.
            </p>
          </div>
        </div>

        <label className="check setting-row">
          <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
          Enable automatic organization
        </label>

        <div className="threshold-row">
          <label htmlFor="threshold" className="field grow">
            <span>Confidence threshold: {threshold}%</span>
            <input
              id="threshold"
              type="range"
              min={50}
              max={100}
              step={1}
              value={threshold}
              onChange={(event) => setThreshold(Number(event.target.value))}
              disabled={!enabled}
            />
          </label>
          <span className="muted small">Minimum 80% recommended</span>
        </div>

        <button type="button" className="btn primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save automation settings"}
        </button>
        <div className="button-row">
          <button type="button" className="btn ghost" onClick={runNow} disabled={running || !enabled}>
            {running ? "Organizing…" : "Organize eligible files now"}
          </button>
          <button type="button" className="btn ghost" onClick={cleanupEmpty} disabled={cleaning}>
            {cleaning ? "Removing…" : "Remove empty folders"}
          </button>
        </div>
        <p className="muted small">
          “Organize eligible files now” moves existing files that already meet the threshold — useful
          after changing models or settings. “Remove empty folders” deletes only folders with no
          files and no subfolders.
        </p>
      </section>

      <section className="panel" aria-labelledby="local-import-heading">
        <h2 id="local-import-heading">Import from this computer</h2>
        <p className="muted small">
          Only folders configured as scan roots can be read. Source files are copied into Inbox and
          never moved or deleted.
        </p>

        {preferences.scan_roots.length === 0 ? (
          <div className="callout">
            <strong>No scan roots configured</strong>
            <p className="small">
              Set <code>FILE_ORGANIZER_SCAN_ROOTS</code> to a semicolon-separated list of absolute
              folders (for example <code>C:\Users\you\Pictures;C:\Users\you\Documents</code>) and
              restart the backend. Browser folder upload still works without this.
            </p>
          </div>
        ) : (
          <>
            <p className="muted small">Allowed roots: {preferences.scan_roots.join(" · ")}</p>
            <form className="import-form" onSubmit={runImport}>
              <label className="field grow">
                <span>Folder path</span>
                <input
                  value={importPath}
                  onChange={(event) => setImportPath(event.target.value)}
                  placeholder={preferences.scan_roots[0]}
                  required
                />
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={recursive}
                  onChange={(event) => setRecursive(event.target.checked)}
                />
                Include subfolders
              </label>
              <button type="submit" className="btn primary" disabled={importing || !importPath.trim()}>
                {importing ? "Importing…" : "Import folder"}
              </button>
            </form>
          </>
        )}

        {importResult && (
          <div className="callout" role="status">
            <strong>{importResult.uploaded.length} imported</strong>
            {importResult.skipped > 0 && <span className="muted small"> · {importResult.skipped} skipped</span>}
            {importResult.errors.length > 0 && (
              <ul className="form-error small">
                {importResult.errors.map((item) => (
                  <li key={`${item.filename}-${item.error}`}>
                    {item.filename}: {item.error}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="google-heading">
        <h2 id="google-heading">Google Drive & Google Photos</h2>
        <div className="provider-row">
          <div>
            <strong>Google Drive</strong>
            <p className="muted small">Scoped OAuth access to files you select.</p>
          </div>
          <span className="badge">{googleLabel(preferences.google_drive)}</span>
        </div>
        <div className="provider-row">
          <div>
            <strong>Google Photos</strong>
            <p className="muted small">
              Photos Picker only; Google does not allow full-library scanning by third-party apps.
            </p>
          </div>
          <span className="badge">{googleLabel(preferences.google_photos)}</span>
        </div>
        <p className="muted small">
          Add <code>GOOGLE_CLIENT_ID</code> and <code>GOOGLE_CLIENT_SECRET</code> to enable the OAuth
          flow. See <code>docs/GOOGLE_SETUP.md</code>.
        </p>
      </section>

      <section className="panel" aria-labelledby="learning-heading">
        <h2 id="learning-heading">How learning works</h2>
        <p className="muted small">
          When a proposal is below {threshold}% and you approve it with edits, that destination is
          stored as a feedback example. Future files of the same document type reuse your approved
          folder; if that pushes confidence above the threshold, they are organized automatically.
          Rejected proposals are tracked as negative examples.
        </p>
      </section>
    </div>
  );
}
