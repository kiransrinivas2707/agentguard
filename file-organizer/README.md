# AI File Organizer — Phase 1 MVP

Drop files into an Inbox. The app extracts their text/metadata, asks an AI classifier for a
structured proposal, and shows it in a review queue. You approve, edit, or keep each file in the
Inbox. Approved files move into an app-managed folder tree, and every move is reversible.

**Product promise: drop anything anywhere; find it later without remembering its filename or folder.**

Status: `READY_FOR_USER_TEST` (pending user acceptance).

## Stack

- **Backend:** Python 3.13, FastAPI, SQLAlchemy, SQLite (WAL), FTS5 search.
- **Frontend:** React 18 + Vite + TypeScript, plain CSS (responsive, keyboard accessible).
- **AI:** OpenCode CLI with a dedicated no-tools agent (`file-classifier`) and validated JSON
  output. A deterministic mock classifier is available for tests/offline development.
- **Storage:** local, per-user directory with a storage adapter interface so Drive/Photos can be
  added later without rewriting classification logic.

## Features (MVP)

- Multi-user accounts (email + password, scrypt hashes, HttpOnly session cookie).
- Upload one or many files with progress, size limits, magic-byte checks, SHA-256 hashing, and
  exact-duplicate warnings (duplicates are never deleted).
- Extraction for TXT/MD/CSV/JSON/YAML, PDF, DOCX, and images.
- AI classification with strict server-side schema validation: document type, category,
  subcategory, tags, suggested filename, suggested folder path, dates/entities, confidence, and
  rationale. Invalid paths/names are rejected.
- Review queue with editable filename/path/tags, confidence, rationale, and new-folder preview.
- **Automatic organization**: known file types at or above a per-user confidence threshold
  (default 80%) are moved without approval, with an undoable operation. The confidence value is
  authoritative; model review flags do not block a move at or above the threshold. Unknown types
  always stay in review.
- **Run now**: Settings → “Organize eligible files now” applies the rule to files already in Inbox
  (useful after changing models/settings). “Remove empty folders” deletes only empty, non-system
  folders.
- **Learning loop**: manual approvals and rejections are stored as feedback; future files of the
  same document type reuse the approved folder and can cross the threshold automatically.
- **Folder guide**: Education/study → `Education/...`; trip photos → `Photos & Memories/Trips`;
  people/selfies → `Photos & Memories/People`; screenshots → `Photos & Memories/Screenshots`;
  general memories → `Photos & Memories/Memories`; professional certificates →
  `Career/Certifications`; academic certificates/degrees → `Education/...`.
- **Local import**: upload a whole browser folder, or scan a configured server folder
  (`FILE_ORGANIZER_SCAN_ROOTS`). Source files are copied, never moved or deleted.
- Approve individually or in a batch with per-item results and partial-failure reporting.
- Folder tree with expand/collapse and counts; files can be browsed per folder.
- Safe preview for PDF/images/text; extracted-text preview for DOCX and other supported files.
- Operation history with one-click undo; undo removes folders created by that action when empty.
- **Trash**: Delete moves a file to Trash (restorable); Trash → Restore or Delete permanently.
  Trashed files are excluded from Inbox, folders, search, review, and stats.
- Search over names, extracted text, tags, categories, and folder paths with type/category/year
  filters. All results are scoped to the signed-in user.

## Quickstart (Windows, easiest)

Double-click these from `file-organizer`:

1. `run-backend.cmd` — starts the API on port 8000 with
   `FILE_ORGANIZER_MODEL=opencode-go/deepseek-v4.1-flash` and
   `FILE_ORGANIZER_SCAN_ROOTS=%USERPROFILE%\Pictures` unless you set them yourself.
2. `run-frontend.cmd` — starts Vite on port 5173.

Keep both windows open. Open <http://localhost:5173>.

## Quickstart (Windows PowerShell)

From the `file-organizer` directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# Backend (terminal 1)
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

## Quickstart (cmd.exe)

`$env:...` is PowerShell syntax. In cmd use `set`, or skip the env var entirely with
`--app-dir`:

```cmd
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

REM Backend (terminal 1) - no PYTHONPATH needed
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

## Frontend (either shell, terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>, create an account, and drop a file.

### Production-style local run

Works in either shell (no `PYTHONPATH`):

```bash
cd frontend
npm run build
cd ..
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8000
```

FastAPI serves `frontend/dist` at <http://localhost:8000> when the build exists.

## Classifier configuration

Defaults are in `backend/app/config.py` and can be overridden with environment variables
(see `.env.example`):

```powershell
$env:FILE_ORGANIZER_CLASSIFIER = "opencode"          # or "mock"
$env:FILE_ORGANIZER_MODEL = "opencode/deepseek-v4.1-flash-free"
$env:FILE_ORGANIZER_OPENCODE_AGENT = "file-classifier"
$env:FILE_ORGANIZER_CLASSIFY_TIMEOUT = "120"
```

The classifier runs `opencode run --model <model> --agent file-classifier --file <attachment>`.
The agent is defined in `.opencode/agents/file-classifier.md` and denies **all** tools, so the
model can only return JSON. File content is passed as untrusted data and is never treated as
instructions.

**Model note:** the free model can hit a usage cap (for example, `Free usage limit reached`). If
that happens, switch to your active OpenCode Go model:

```powershell
$env:FILE_ORGANIZER_MODEL = "opencode-go/deepseek-v4.1-flash"
```

For offline work or tests, use `FILE_ORGANIZER_CLASSIFIER=mock`.

### Classifier failures

- **"free classifier quota is exhausted"** — the free model hit its usage cap. Set
  `FILE_ORGANIZER_MODEL` to a model your account can use (for example
  `opencode-go/deepseek-v4.1-flash`) and restart the backend.
- **"classifier account has no credits"** — the connected Console workspace has no paid credit
  balance. Top up that workspace or switch models.
- **"classifier is not authenticated"** — connect a provider with `opencode auth login` or set a
  supported provider environment variable.
- After fixing the model/account, open the file in Inbox and click **Retry analysis**. Failed
  classifications stay in Inbox so nothing is lost.
- **Preview shows "localhost refused to connect"** — the backend is not running on port 8000.
  Restart it with `run-backend.cmd` or the uvicorn command above. PDF and image previews are
  served same-origin and allowed to frame; no external viewer is required.

The app passes the selected model through `opencode run`; it never writes the model or credentials
into source files. Use `FILE_ORGANIZER_SECRET` and provider environment variables for secrets.

## Data and privacy

- Data lives under `FILE_ORGANIZER_DATA` (default `file-organizer/data`): SQLite DB plus
  `users/<user-id>/` storage pools.
- The dev JWT secret is generated once and stored in `data/.secret` if no
  `FILE_ORGANIZER_SECRET` is supplied. Set an explicit long secret outside local development.
- Passwords are hashed with scrypt; session cookies are `HttpOnly` and `SameSite=Lax`
  (`Secure` when `FILE_ORGANIZER_COOKIE_SECURE=true`).
- Every API query is scoped to the authenticated user. Preview/download endpoints check ownership.
- Files are treated as untrusted input: bytes are not executed, MIME/extensions are cross-checked,
  preview is limited to a safe allowlist, and classifier output is validated before use.
- No file text, filename, or token is written to application logs by default.
- Organization never deletes a file. Undo restores the previous folder and name.

## Tests and checks

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python -m pytest tests -q

cd frontend
npm run build
```

Current suite: **83 passed** (auth, upload validation, extraction errors, classifier schema,
prompt-injection-safe parsing, actionable classifier errors, path safety, collisions, duplicates,
approve/reject, batch partial failures, undo/partial undo, search (including literal `%`/`_`
handling), JSON preview, PDF frame-preview headers, auto-organize, run-now reconciliation,
learning feedback, threshold validation, taxonomy, empty-folder cleanup, local folder import,
trash/restore/purge, legacy-DB migration, cross-user isolation, headers/CSRF-origin checks,
throttle).

Real-model check used during development:

```powershell
opencode run --model opencode-go/deepseek-v4.1-flash --agent file-classifier --archived `
  --file .\sample.txt "Return JSON for this file."
```

## Manual test scenarios

1. Register two accounts. Upload a file as user A; confirm user B cannot open it, search it, or
   see its folders.
2. Upload a resume and an invoice. Confirm both appear in Inbox, then Needs Review with sensible
   proposals.
3. Edit the proposed filename/path, approve, and confirm the file is physically under
   `data/users/<id>/<folder path>/`.
4. Approve two files with the same proposed name and confirm `(2)` collision handling.
5. Reject a proposal and confirm the file stays in Inbox and leaves the review queue.
6. Undo an organize action and confirm the file returns to Inbox and empty created folders are
   removed.
7. Search by filename, body text, tag, category, and year; confirm no results from another user.
8. Upload an empty file, a fake `.pdf`, an oversized file, and an unsupported `.exe`. Confirm clear
   per-file errors and that unsupported files are never previewed or organized.
9. Try approving with `..`, `C:\...`, or a path deeper than 4 levels; confirm rejection.
10. Enable auto-organize at 80%; upload a resume and confirm it is moved to `Career / Resumes`
    without approval and appears as an **Auto-organized** history entry.
11. Upload an image below 80%, approve it with a new folder, upload another image, and confirm the
    second one reuses your folder and is auto-organized.
12. Upload a folder in the browser; then import a folder under the configured scan root and confirm
    the source files are still present.
13. Check keyboard navigation, focus states, and mobile layout (~375 px wide).

## Known limitations (Phase 1)

- Classification runs in-process (FastAPI background tasks), not a durable queue. A restart can
  leave a file in Inbox; press **Retry analysis** to retry.
- No OCR for scanned PDFs/images, and no embeddings/semantic search yet (FTS + metadata only).
- **Google Drive/Photos connectors are not active yet.** The provider status and
  `docs/GOOGLE_SETUP.md` are ready; OAuth is implemented after credentials exist. Google Photos
  only supports Picker-selected items, not full-library scanning.
- Server-folder import requires explicit `FILE_ORGANIZER_SCAN_ROOTS`; the browser folder upload
  works without it.
- Learning is metadata-based: it reuses approved destinations for the same document type. It does
  not train a model or use file contents across users.
- No file delete/trash action yet (organization never deletes).
- Login throttling is in-memory and per process; not a distributed rate limiter.
- Malware scanning and duplicate *similarity* detection are out of scope for Phase 1.
- The free classifier model can be rate-limited; switch models as described above.
