# Blog Cloud Functions

OpenAI key comes from Firestore **`admin/dummy`** — no `OPENAI_API_KEY` env secret.

| Field | Purpose |
|-------|---------|
| `b` | Base64 AES-256 key |
| `iv` | Base64 IV |
| `oKey` | Encrypted OpenAI API key (AES-256-CBC, same as main Sattva app) |

## Functions (codebase `blog`)

| Function | Schedule / access | Purpose |
|----------|-------------------|---------|
| `blogReconcileScheduled` | Daily 12:00 AM IST | Decrypt `oKey`, check recipes vs `blog_posts`, create up to 5 missing |
| `blogReconcileManual` | Private HTTP | Manual reconcile run |
| `blogOpenAiKeyHealth` | Private HTTP | Verify decrypt works (never returns key) |

## Deploy

```bash
cd functions
npm install
cd ..
firebase deploy --only functions:blog --project sattva-srsti
```

Do **not** run `firebase deploy --only functions` — that can affect other codebases in the same project.

## Crypto

Matches `sattva/functions/index.js`:

```js
decrypt(oKey, b, iv)  // AES-256-CBC, base64 in/out
```
