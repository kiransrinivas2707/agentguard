# Google Drive & Google Photos setup

The app already exposes provider status in Settings, but the OAuth connector is **not active yet**.
This document is the exact setup needed before implementing and enabling it.

## Important limitations

- **Google Drive:** `drive.readonly` is a **restricted scope**. It can read the whole Drive, but
  Google requires OAuth verification and, for production, a security assessment. A safer initial
  option is `drive.file`, which only sees files the app created or the user opened with the app.
- **Google Photos:** the Library API cannot scan a user's entire photo library. Use the **Photos
  Picker API**, where the user explicitly selects photos. Scope:
  `https://www.googleapis.com/auth/photospicker.mediaitems.readonly`.
- Never request both Drive and Photos scopes in one consent unless the user connects both.
- Access must be revocable. Do not store tokens in source, logs, or the browser bundle.

## 1. Create the Google Cloud project

1. Open <https://console.cloud.google.com/>.
2. Create or select a project.
3. Enable **Google Drive API**.
4. Enable **Google Photos Library API** (or the Photos Picker API).
5. Configure the **OAuth consent screen**:
   - User type: External (or Internal for a Workspace org).
   - Add your Google account as a **Test user** while developing.
   - Add the scopes you will request:
     - `https://www.googleapis.com/auth/drive.readonly` (or `drive.file`)
     - `https://www.googleapis.com/auth/photospicker.mediaitems.readonly`

## 2. Create OAuth client credentials

1. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Web application**.
3. Authorized redirect URI for local development:
   `http://localhost:8000/api/integrations/google/callback`
4. Copy the **client ID** and **client secret**.

## 3. Configure the app (local only, never commit)

Set these in the terminal that runs the backend, or in a local `.env` that is gitignored:

```powershell
$env:GOOGLE_CLIENT_ID = "...apps.googleusercontent.com"
$env:GOOGLE_CLIENT_SECRET = "..."
```

The Settings page will change from `setup_required` to `oauth_ready` when both values are present.
The connector itself is implemented in a later step; until then no Google data is accessed.

## 4. Planned connector behavior

- **Connect** button → OAuth authorization URL with `state`, PKCE, and the minimum scopes.
- Callback validates `state`, exchanges the code, encrypts tokens at rest, and stores the account.
- Drive: user selects a folder/tree; the app lists supported files, imports copies into Inbox, and
  never deletes or moves the source.
- Photos: user opens the Picker, selects items, and the app imports only those items.
- Every import creates normal Inbox files with hashes, duplicate flags, classification, and undoable
  organization history.
- **Disconnect** revokes the token at Google and deletes the stored credential.
- Tokens are never logged and never included in classifier prompts.

## 5. Production notes

- Use HTTPS and set `FILE_ORGANIZER_COOKIE_SECURE=true`.
- Complete Google OAuth verification for restricted scopes.
- Keep a privacy policy and a data-deletion path.
- Rate limits and quota errors must be surfaced without exposing tokens.
