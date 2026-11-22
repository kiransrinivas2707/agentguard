# AI File Organizer — Phase 1 MVP Plan

Status: READY_FOR_USER_TEST (validator PASS; tester PASS after 2 fixes; user acceptance pending)
Scope owner: user (approved stack: Python FastAPI + SQLite + React/Vite; multi-user accounts;
classifier: OpenCode `opencode/deepseek-v4.1-flash-free` for now, deterministic mock for tests).

## Goal

A local-first, multi-user web app where a user drops files into an Inbox, the app extracts
content/metadata, asks the classifier for a structured organization proposal, lets the user
review/edit/approve, then safely moves the file into an app-managed folder tree. Every move is
recorded and reversible. Users can browse, preview, search, and see duplicate warnings.

## Acceptance criteria

1. **Accounts** — register, login, logout, session persistence; every API resource is scoped to
   the authenticated user. No cross-user file, folder, search, or operation access.
2. **Upload** — single and multi-file upload to Inbox with size/type limits, magic-byte checks,
   SHA-256 hashing, duplicate flagging, and clear per-file errors.
3. **Extraction** — TXT/MD/CSV text, PDF text, DOCX text, image metadata; unsupported types are
   stored but marked unsupported, never silently dropped.
4. **Classification** — provider interface with OpenCode and mock implementations. Output is
   validated server-side against a strict schema; invalid output is rejected and surfaced as a
   failed classification. File content is treated strictly as data (prompt-injection aware).
5. **Folder tree** — per-user tree with a system Inbox; existing folders are offered to the
   classifier; new folders are created only on approval; depth capped; names sanitized.
6. **Review queue** — shows original name, proposed name/path, confidence, rationale, tags;
   user can edit, approve, reject, or leave in Inbox. Batch approve reports partial failures.
7. **Organize** — plan/apply model: path traversal, root escape, absolute paths, unsafe names,
   and overwrites are rejected; collisions get safe suffixes; originals are never deleted.
8. **Undo / history** — each organize action is recorded with before/after state; undo restores
   previous folder/name and removes folders created by that action when empty.
9. **Browse / preview / search** — tree navigation, file list, safe inline preview for
   PDF/images/text, keyword + metadata search over names, extracted text, tags, and paths.
10. **Quality gates** — pytest suite covers auth isolation, upload validation, classifier
    schema, path safety, collisions, duplicates, approve/reject, undo, search. Frontend builds.
    Validator (`nemotron-3.5-super-vl-free`) returns PASS; tester (`big-pickle`) reports PASS.

## Non-goals for Phase 1

Google Drive/Photos, OCR, embeddings/semantic search, auto-organize, file deletion/trash,
background workers across processes, production deployment hardening.

## Data model (SQLite)

- `users` — id, email, password_hash (scrypt), created_at
- `folders` — id, user_id, parent_id, name, is_system, created_at
- `files` — id, user_id, folder_id, names, mime, size, sha256, storage_path, status,
  extracted_text, duplicate_of_id, timestamps
- `classifications` — structured proposal + provider/model + confidence + applied flag
- `operations` / `operation_items` — reversible move records, created folder ids

## Security boundaries

- Server-side authorization on every query; internal IDs only.
- Uploads verified by magic bytes, capped size, stored under a per-user root.
- All storage paths resolved and checked against the user root before any move/read.
- Classifier can only return data; it never touches the filesystem or DB.
- Secrets from env; dev fallback secret persisted with owner-only permissions.
- Logs redact file text, names, tokens, and credentials.
