# Blog pipeline runners

OpenAI key comes from Firestore **`admin/dummy`** — no `OPENAI_API_KEY` env secret.

| Field | Purpose |
|-------|---------|
| `b` | Base64 AES-256 key |
| `iv` | Base64 IV |
| `oKey` | Encrypted OpenAI API key (AES-256-CBC, same as main Sattva app) |

Daily posts are created on this Windows PC by Task Scheduler (`SattvaSrstiBlogDaily` at 23:11), not by a Cloud Function.

```powershell
node functions/run_reconcile_once.js
```

The scheduled Cloud Function `blogReconcileScheduled` was removed. Private HTTP helpers (`blogReconcileManual`, `blogAttachTeasersManual`, `blogOpenAiKeyHealth`) remain for one-off tests.

## Crypto

Matches `sattva/functions/index.js`:

```js
decrypt(oKey, b, iv)  // AES-256-CBC, base64 in/out
```
