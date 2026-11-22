# Handoff — AI File Organizer Phase 1 MVP

Status: `READY_FOR_USER_TEST`
Date: 2026-11-21
Main agent: DeepSeek V4.1 Flash (OpenCode)
Validator: Nemotron 3.5 (free variant)
Tester: Big Pickle

## Change/Feature

Local-first, multi-user AI file organizer:

upload → extract → AI proposal → review/edit → approve → organize → browse/preview/search →
history/undo. Files are never deleted by organization.

## Requirement and acceptance criteria

1. Accounts + strict per-user isolation.
2. Multi-file upload with limits, magic-byte checks, hashing, duplicate flagging.
3. TXT/MD/CSV/JSON/PDF/DOCX/image extraction; unsupported stored but never organized/previewed.
4. Strict validated classifier output; prompt injection contained; no tools for the model.
5. Folder tree with system Inbox, reuse, depth cap, sanitized names, create only on approval.
6. Review queue with editable name/path/tags, confidence/rationale, approve/reject, batch partial
   failures.
7. Safe organize: reject traversal/absolute paths/root escape/overwrites; collision-safe names.
8. Operation history + undo, empty created-folder cleanup, partial-undo reporting.
9. Browse/tree/preview/search over names, text, tags, categories, paths.
10. Tests + frontend build.

## Files/areas changed

New project: `file-organizer/`

- `backend/app/` — config, DB/models, auth, storage adapter, extraction, classifier,
  paths/tree, files service, organizer/undo, search, background job, routes, app factory.
- `frontend/src/` — auth, sidebar/tree, upload, file/review cards, preview, inbox/folder/review/
  search/history pages, API client, responsive CSS.
- `tests/` — 68 pytest tests.
- `.opencode/agents/file-classifier.md` — no-tools classification agent.
- `README.md`, `docs/PLAN.md`, `.env.example`, `requirements.txt`.

## Implementation summary

- FastAPI + SQLAlchemy + SQLite (WAL) + FTS5; React 18 + Vite + TypeScript.
- Per-user `data/users/<id>/` storage; logical tree mirrors physical folders.
- Classifier: OpenCode CLI (`opencode run --model ... --agent file-classifier --file ...`) with
  strict Pydantic validation; deterministic mock for tests.
- Plan/apply organization with operation + item records; storage moves before DB commit and are
  rolled back on failure; undo restores folder/name/status and removes empty created folders.
- Search uses FTS5 candidate retrieval plus escaped LIKE fallback; all queries scoped to user.
- Uploads: size cap, magic-byte/extension checks, SHA-256, duplicate flag, per-file errors.

## Tests run and results (commands)

```powershell
cd file-organizer
$env:PYTHONPATH="backend"
.\.venv\Scripts\python -m pytest tests -q
# 68 passed, 1 warning

cd frontend
npm run build
# tsc --noEmit && vite build -> success (44 modules)
```

Independent tester (Big Pickle), fresh temp DB + mock classifier:

- 81/81 black-box checks passed after fixes (was 80/81).
- Cross-user isolation, auth/cookies, uploads, review edit/approve, collision `(2)`, reject,
  undo + folder cleanup + second undo 409, duplicates, negative uploads, path safety, search,
  batch partial failure, static/API 404, malformed JSON, unauthenticated sweep, IDOR, invalid
  params, origin/CORS, security headers.
- Real classifier integration was verified separately with
  `opencode-go/deepseek-v4.1-flash` (valid JSON; reused `Career/Certifications`).
- Browser UI E2E was **not** run because no desktop browser was connected; UI was verified by
  TypeScript/Vite build and API contract tests only.

## Review findings

Round 1 validator: `PASS` (low-risk observations only).

Test round 1: `BUGS_FOUND` — 2 defects. Both triaged, fixed, revalidated, retested.

```text
ID: BUG-1
Severity: medium
Finding: .json files were accepted/extracted but /content returned 415.
Evidence/location: backend/app/extraction.py PREVIEWABLE; routes/files.py content gate.
Reproduction: upload probe.json -> GET /api/files/{id}/content -> 415.
Expected: 200 JSON body.
Actual: 415 "Preview is not available".
Recommended fix: include application/json in PREVIEWABLE + regression test.
Status: fixed | revalidated

ID: BUG-2
Severity: low
Finding: wildcard-only searches (% and _) returned every user file.
Evidence/location: backend/app/search.py LIKE fallback interpolation.
Reproduction: GET /api/search?q=%25 or q=_ -> all files.
Expected: 0 results (literal wildcards).
Actual: all user files.
Recommended fix: escape \, %, _ and use LIKE ... ESCAPE '\' + regression tests.
Status: fixed | revalidated
```

Validator re-review after fixes: `PASS`. Tester retest: `PASS`, 81/81.

## Post-handoff hardening (2026-11-21)

During user testing the classifier failed with an unhelpful "The classifier process failed".
Root cause was provider quota/credits, not the app. Added:

- Actionable failure messages mapped from safe stderr categories (free quota, no credits,
  rate limit, unauthenticated, unavailable model). Raw stderr is never exposed.
- A **Retry analysis** button for `needs_review` files whose classification errored, so users do
  not need to re-upload.
- README troubleshooting section for classifier quota/credit/auth failures.
- Regression tests for the failure-message mapping; suite is now **68 passed**.
- Frontend build re-run successfully after the retry-button change.
- **PDF preview fix:** the global `frame-ancestors 'none'` CSP (and `X-Frame-Options: DENY`)
  blocked the PDF iframe. File content responses now send `frame-ancestors 'self'` /
  `X-Frame-Options: SAMEORIGIN`. Regression test added.
- Browser E2E verified with a temporary dataset: PDF and JPEG previews both render in the modal;
  PDF uses the built-in viewer, image renders at its natural size.
- Added `run-backend.cmd` (defaults to the working Go model, checks port 8000) and
  `run-frontend.cmd` for one-click startup on Windows.
- `vite.config.ts` now accepts `VITE_API_TARGET` for testing against alternate backends.

OpenCode Console API key supplied by the user was stored in OpenCode's service environment, but
its workspace currently returns **402 (no credits)** for paid models and **429 (free quota)** for
the free model. The working path is the user's **OpenCode Go** subscription
(`opencode-go/deepseek-v4.1-flash`). No secret was written to project files.

## Phase 2 — automation, learning, local import (2026-11-21)

User-approved scope:

- Automatic organization for known document types at or above a per-user threshold (default 80%).
  Missing folders are created; every auto move is recorded and undoable.
- Unknown types (`document_type = "other"`) always stay in review.
- Feedback loop: manual approvals/rejections recorded; approved destinations reused for the same
  document type; rejected proposals used as negative examples.
- Local import: browser folder upload and server-folder scan restricted to
  `FILE_ORGANIZER_SCAN_ROOTS`. Source files are copied, never moved or deleted.
- Settings page for automation, threshold, local roots, import, and Google provider status.
- Google Drive/Photos: setup documentation and status only; OAuth connector deferred until
  credentials are provided.

Added/changed:

- `backend/app/feedback.py`, `auto.py`, `scan.py`, `routes/preferences.py`, `routes/imports.py`.
- User preference columns + Feedback table + additive SQLite migration.
- Classifier context now includes recent user decisions; learned destinations reuse approved paths.
- Frontend `SettingsPage`, folder upload, review path suggestions, auto history label, metadata
  polling after uploads.
- `docs/GOOGLE_SETUP.md`, README/.env updates, `run-backend.cmd` scan-root default
  (`%USERPROFILE%\Pictures`).
- Tests: **76 passed**; frontend build succeeds.
- Browser E2E verified: Settings renders, scan-root import imports a file, auto-organize moves an
  invoice to `Finance/Invoices`, History shows **Auto-organized**, undo available.
- Google OAuth is intentionally **not active**; no Google data is requested until credentials and
  the connector are added.

Phase 2 remaining risks:

- Learning is a deterministic metadata heuristic (same document type -> approved path), not model
  training. Confidence is raised to just above threshold when a learned path applies.
- Server-folder import is only as safe as the configured roots; keep them narrow.
- Auto-organize may move sensitive documents (identity/passport) at high confidence because the
  user did not request a sensitive-type exception.
- Google Drive/Photos need OAuth credentials, consent-screen setup, and (for restricted scopes)
  verification before they can be enabled.

### Phase 2 independent gates

- Validator (Nemotron): **PASS** — no critical/high findings.
- Tester (Big Pickle): **PASS**.
  - New black-box suite: **51/51 passed** (preferences, auto-organize + undo, disable/reject,
    JPEG learning, unknown-type guard, local import caps/roots/traversal, duplicates, concurrency,
    auth, cross-user isolation, static assets).
  - Migration simulation: **8/8 passed** (old DB with 8 users / 228 files upgraded without loss;
    columns + feedback table recreated).
  - Threshold boundary, forced auto-failure rollback, and "no feedback for auto decisions" verified.
  - Prior regression suite: 78/80 as written; both failures are stale expectations caused by the
    new learning feature (an approved folder is reused by design), not regressions. Confirmed in
    DB that no data was lost or overwritten.
  - Browser UI smoke was not available to the tester; the main agent verified Settings, scan-root
    import, auto-organized invoice, and Auto-organized history in the browser.
- Local suite: **76 passed**; frontend build succeeds.
- Known symlink runtime test limitation on Windows (no privilege); code rejects symlinks and the
  traversal/outside-root cases passed.

Status: `READY_FOR_USER_TEST` (Phase 2).

### Phase 2.1 — confidence-authoritative auto-organize + taxonomy (2026-11-21)

User feedback: empty folders appeared because high-confidence proposals had `requires_review=True`
and were skipped; files were still in Inbox. Education/study and photo taxonomy needed refinement.

- Auto-organize eligibility no longer treats `requires_review` as a blocker; confidence at or above
  the threshold wins for known types. Unknown types and classifier errors still stay in review.
- `POST /api/automation/run` + Settings button **Organize eligible files now** reconciles existing
  Inbox files without re-uploading or re-classifying.
- `POST /api/folders/cleanup-empty` + Settings button **Remove empty folders** deletes only
  empty, non-system folders.
- Classifier prompt now includes a folder guide; mock rules cover Education/Study Materials,
  academic certificates/degrees, trips, people/selfies, screenshots, memories, signatures.
- Tests: **79 passed**; frontend build succeeds.
- User's current data audit: 5 files still in `Inbox`, 0 organize operations; folders were empty
  because no move had been applied yet. After restart, **Organize eligible files now** will move the
  95%/86%/82% files; the 72% ID photo remains in review; the 0% passport needs **Retry analysis**.
- Validator: **PASS**. Tester (Big Pickle): **PASS** — forced `requires_review=True` file organized
  by run-now, second run skips, `other@0.95`/`0.79` stay review, `0.8` organizes, taxonomy paths
  correct, cleanup removes only empty folders, regressions pass.
- Note: undo returns an auto-organized file to `classified`/Inbox; running **Organize eligible files
  now** again will re-organize it. Undo is not a permanent “do not auto-organize” flag.

Status: `READY_FOR_USER_TEST` (Phase 2.1).

### Phase 2.2 — legacy DB migration fix + Trash (2026-11-21)

User reported auto-organize failing and **Approve & organize returning 500**. Root cause: an older
local SQLite DB was missing `operation_items.previous_classification_id`; fresh test DBs had it, so
tests passed. Every approve/auto insert failed with `OperationalError`.

- Added additive migration for `operation_items.previous_classification_id` and
  `files.previous_status`; verified approval succeeds on a copy of the user's live DB.
- Applied the migration to the live DB and ran the reconcile:
  **all 6 current files organized** (the backend/User retries also reclassified the two remaining
  files at high confidence). Folders now contain the files.
- Auto-eligibility now retries files whose only error is a previous **automatic organization
  failure**; classifier errors still block.
- Added **Trash**:
  - `DELETE /api/files/{id}` moves a file to `Trash/<file-id>/` and marks it `trashed`.
  - `GET /api/trash`, `POST /api/trash/{id}/restore`, `DELETE /api/trash/{id}` (permanent).
  - UI: Delete buttons on Inbox/Review/Folder cards; Trash page with Restore and Delete permanently.
  - Trashed files are excluded from files/folders/search/review/stats; preview still works.
- Tests: **83 passed**; frontend build succeeds.
- Legacy migration regression test added (drops the missing column, runs `init_db`, verifies repair).
- Trash restores/purges now remove the empty `Trash/<file-id>` directory too (cosmetic cleanup found by the tester).
- Validator: **PASS**. Tester (Big Pickle): **PASS** — legacy DB migration 6/6, trash lifecycle, auto retry, cross-user isolation, and regressions verified.

Status: `READY_FOR_USER_TEST` (Phase 2.2).

## Known limitations / accepted risks

- Classification is an in-process background task, not a durable queue. Restart can leave a file
  in Inbox; user can press Analyze.
- No OCR, embeddings/semantic search, Drive/Photos adapters, delete/trash, malware scanning,
  similarity duplicates, or auto-organize in Phase 1.
- Login throttling is in-memory/per process.
- CSRF relies on `SameSite=Lax` cookies + Origin checks, not per-request CSRF tokens. Suitable for
  the local-first MVP; revisit for public deployment.
- `SameSite=lax` rather than `strict`; secure cookies require
  `FILE_ORGANIZER_COOKIE_SECURE=true` behind HTTPS.
- Free classifier quota can be exhausted; switch `FILE_ORGANIZER_MODEL` to the active Go model.
- Browser UI E2E not executed in this environment.
- Dead code: `looks_like_text` and the unused `TagUpdate` schema remain (no functional impact).

## How to run

See `README.md` Quickstart. Short version:

```powershell
cd file-organizer
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:PYTHONPATH="backend"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

cd frontend
npm install
npm run dev   # http://localhost:5173
```

Production-style local run: `npm run build`, then serve FastAPI on port 8000.

Classifier: default `opencode/deepseek-v4.1-flash-free`; if quota is exhausted set
`FILE_ORGANIZER_MODEL=opencode-go/deepseek-v4.1-flash`. For offline/tests use
`FILE_ORGANIZER_CLASSIFIER=mock`.

## Suggested manual tests

1. Register two accounts; verify isolation across files, previews, search, folders, history.
2. Upload a resume and an invoice; review/edit/approve; verify physical folder placement.
3. Approve two same-named files; verify `(2)` suffix.
4. Reject a proposal; verify it stays in Inbox.
5. Undo; verify folder/name restored and empty created folders removed.
6. Search by name, text, tag, category, year; try `%` and `_`.
7. Negative uploads (empty, fake PDF, oversized, `.exe`); path attempts (`..`, `C:\`, 5 levels).
8. Keyboard navigation, focus states, and ~375 px mobile layout.

## Next agent/action

**User**: run the app, execute the manual scenarios, and explicitly accept/reject. Until then the
feature is not complete and must not be deployed/published.
