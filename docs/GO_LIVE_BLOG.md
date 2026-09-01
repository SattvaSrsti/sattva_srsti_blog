# Go live — sattvasrsti.blog

## Status (updated)

### Firestore `blog_posts` sync (2026-08-20)

- Synced **11** ready posts from `preview/data/*.blog.json` (via `posts-index.json`) → `blog_posts/{blog_id}` replace.
- No Firestore orphans deleted (local set already matched the 11 doc IDs).
- Local-only leftover file (not indexed / not written): `preview/data/aloo-paratha.blog.json` (same `blog_id` as dough-tearing post).
- Mysore verified in Firestore: `primary_question` match, `capability_id=guided_recipe_customization`, `research` length 5, `related_problems` length 4.

| URL | Status |
|-----|--------|
| https://sattva-srsti.web.app/post.html?slug=why-is-my-mysore-masala-dosa-not-crispy | **LIVE** — use this until `.blog` SSL finishes |
| https://sattvasrsti.blog/ | **Content served**, SSL **not ready yet** (browser shows certificate warning) |
| https://sattvasrsti.blog/post.html?slug=why-is-my-mysore-masala-dosa-not-crispy | Same — site content OK behind pending cert |

### DNS (public — dns.google)

| Record | Value | OK? |
|--------|--------|-----|
| `sattvasrsti.blog` **A** | `199.36.158.100` | Yes |
| `_acme-challenge.sattvasrsti.blog` **TXT** | `uLZPAnFYELwI8asUUXpuyjjn4NDGRbN_JqFbbPl-H4s` | Yes |

### Firebase Hosting domain API

| Field | Value |
|-------|--------|
| `sattvasrsti.blog` dnsStatus | still reports `DNS_MISSING` (lag / internal check) |
| `sattvasrsti.blog` certStatus | **`CERT_PENDING`** ← current blocker |
| Expected IP | `199.36.158.100` |

---

## What to do next (you)

1. Open Firebase Hosting → custom domains:  
   https://console.firebase.google.com/project/sattva-srsti/hosting/sites/sattva-srsti
2. Select **sattvasrsti.blog** → **Refresh / Verify** if shown.
3. Wait until status shows SSL connected / **`CERT_ACTIVE`** (often 15–60 min after DNS is correct; can take a few hours).
4. Then open (no warning):  
   https://sattvasrsti.blog/post.html?slug=why-is-my-mysore-masala-dosa-not-crispy
5. After `.blog` SSL works: remove **`sattvasrsti.com`** and **`sattvasrsti.in`** from this Hosting site (blog = `.blog` only). See `docs/REVERT_COM_IN_DNS.md`.

Do **not** change the A/TXT records again unless Firebase Console shows different values.

---

## QA already done (web.app)

Hero, ingredients, 3 steps, 4 related problems, CTAs, share, mobile, bad-slug fallback — all pass on Hosting.
