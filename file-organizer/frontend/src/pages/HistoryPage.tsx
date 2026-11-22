import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Operation } from "../types";

interface Props {
  onChanged: () => void;
  notify: (message: string, kind?: "ok" | "error") => void;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function HistoryPage({ onChanged, notify }: Props) {
  const [operations, setOperations] = useState<Operation[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string[]>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setOperations(await api.operations());
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not load history", "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const undo = async (operation: Operation) => {
    setBusyId(operation.id);
    setErrors((current) => ({ ...current, [operation.id]: [] }));
    try {
      const response = await api.undo(operation.id);
      setOperations((current) =>
        current.map((entry) => (entry.id === response.operation.id ? response.operation : entry)),
      );
      if (response.errors.length > 0) {
        setErrors((current) => ({ ...current, [operation.id]: response.errors }));
        notify("Undo finished with warnings", "error");
      } else {
        notify("Organize action undone");
      }
      onChanged();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not undo", "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="page">
      <div className="section-heading">
        <div>
          <h2>History</h2>
          <p className="muted small">Every organize action is recorded and can be reversed.</p>
        </div>
      </div>

      {loading ? (
        <p className="muted">Loading…</p>
      ) : operations.length === 0 ? (
        <div className="empty">
          <span aria-hidden="true">↺</span>
          <p>No organize actions yet.</p>
        </div>
      ) : (
        <div className="history-list">
          {operations.map((operation) => (
            <article key={operation.id} className="history-card">
              <div className="history-head">
                <div>
                  <strong>{operation.kind === "auto" ? "Auto-organized" : operation.kind}</strong>
                  <span className="muted small block">{formatDate(operation.created_at)}</span>
                </div>
                <span className={`badge history-${operation.status}`}>{operation.status.replace(/_/g, " ")}</span>
              </div>

              <ul className="history-items">
                {operation.items.map((item) => (
                  <li key={item.id}>
                    <span className="muted small">{item.from_path}</span>
                    <span aria-hidden="true"> → </span>
                    <strong>{item.to_path}</strong>
                    <span className={`badge item-${item.status}`}>{item.status}</span>
                  </li>
                ))}
              </ul>

              {errors[operation.id]?.length > 0 && (
                <ul className="form-error small" role="alert">
                  {errors[operation.id].map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                </ul>
              )}

              {operation.status === "applied" && (
                <button
                  type="button"
                  className="btn ghost small"
                  disabled={busyId === operation.id}
                  onClick={() => undo(operation)}
                >
                  {busyId === operation.id ? "Undoing…" : "Undo this action"}
                </button>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
