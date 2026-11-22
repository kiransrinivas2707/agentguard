import { useMemo, useState } from "react";
import type { Folder, Stats, User } from "../types";

interface Props {
  user: User;
  stats: Stats | null;
  folders: Folder[];
  route: string;
  onNavigate: (route: string) => void;
  onLogout: () => void;
  onClose?: () => void;
}

function FolderNode({
  folder,
  childrenByParent,
  activeId,
  onSelect,
}: {
  folder: Folder;
  childrenByParent: Map<string | null, Folder[]>;
  activeId: string | null;
  onSelect: (folder: Folder) => void;
}) {
  const [open, setOpen] = useState(folder.path.length <= 1);
  const children = childrenByParent.get(folder.id) ?? [];
  const active = activeId === folder.id;

  return (
    <li>
      <div className={active ? "tree-row active" : "tree-row"}>
        {children.length > 0 ? (
          <button
            type="button"
            className="tree-toggle"
            aria-label={`${open ? "Collapse" : "Expand"} ${folder.name}`}
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="tree-toggle placeholder" aria-hidden="true" />
        )}
        <button type="button" className="tree-label" onClick={() => onSelect(folder)}>
          <span className="tree-name">{folder.name}</span>
          <span className="count">{folder.file_count}</span>
        </button>
      </div>
      {open && children.length > 0 && (
        <ul className="tree-children">
          {children.map((child) => (
            <FolderNode
              key={child.id}
              folder={child}
              childrenByParent={childrenByParent}
              activeId={activeId}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function Sidebar({ user, stats, folders, route, onNavigate, onLogout, onClose }: Props) {
  const childrenByParent = useMemo(() => {
    const map = new Map<string | null, Folder[]>();
    for (const folder of folders) {
      if (folder.path.length === 1 && folder.name === "Inbox") continue;
      const list = map.get(folder.parent_id) ?? [];
      list.push(folder);
      map.set(folder.parent_id, list);
    }
    // Inbox is a nav entry, but any subfolders created under it still need a home.
    const inbox = folders.find((folder) => folder.path.length === 1 && folder.name === "Inbox");
    if (inbox) {
      const inboxChildren = map.get(inbox.id) ?? [];
      if (inboxChildren.length > 0) {
        map.set(null, [...(map.get(null) ?? []), ...inboxChildren]);
        map.delete(inbox.id);
      }
    }
    for (const list of map.values()) list.sort((a, b) => a.name.localeCompare(b.name));
    return map;
  }, [folders]);

  const activeFolderId = route.startsWith("folder/") ? route.split("/")[1] : null;
  const go = (next: string) => {
    onNavigate(next);
    onClose?.();
  };

  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          ◈
        </span>
        <div>
          <strong>File Organizer</strong>
          <span className="muted small block">Drop anything</span>
        </div>
      </div>

      <nav className="nav">
        <button type="button" className={route === "inbox" ? "nav-item active" : "nav-item"} onClick={() => go("inbox")}>
          <span aria-hidden="true">▤</span> Inbox <span className="count">{stats?.inbox ?? 0}</span>
        </button>
        <button type="button" className={route === "review" ? "nav-item active" : "nav-item"} onClick={() => go("review")}>
          <span aria-hidden="true">✦</span> Needs Review <span className="count">{stats?.needs_review ?? 0}</span>
        </button>
        <button type="button" className={route === "search" ? "nav-item active" : "nav-item"} onClick={() => go("search")}>
          <span aria-hidden="true">⌕</span> Search
        </button>
        <button type="button" className={route === "history" ? "nav-item active" : "nav-item"} onClick={() => go("history")}>
          <span aria-hidden="true">↺</span> History
        </button>
        <button type="button" className={route === "trash" ? "nav-item active" : "nav-item"} onClick={() => go("trash")}>
          <span aria-hidden="true">🗑</span> Trash <span className="count">{stats?.trashed ?? 0}</span>
        </button>
        <button type="button" className={route === "settings" ? "nav-item active" : "nav-item"} onClick={() => go("settings")}>
          <span aria-hidden="true">⚙</span> Settings
        </button>
      </nav>

      <div className="tree-section">
        <div className="tree-heading">
          <span>Folders</span>
          <span className="muted small">{stats?.organized ?? 0} organized</span>
        </div>
        <ul className="tree">
          {(childrenByParent.get(null) ?? []).map((folder) => (
            <FolderNode
              key={folder.id}
              folder={folder}
              childrenByParent={childrenByParent}
              activeId={activeFolderId}
              onSelect={(selected) => go(`folder/${selected.id}`)}
            />
          ))}
          {(childrenByParent.get(null) ?? []).length === 0 && (
            <li className="muted small tree-empty">Approved files create folders here.</li>
          )}
        </ul>
      </div>

      <div className="sidebar-footer">
        <span className="muted small block" title={user.email}>
          {user.email}
        </span>
        <button type="button" className="btn ghost small" onClick={onLogout}>
          Sign out
        </button>
      </div>
    </aside>
  );
}
