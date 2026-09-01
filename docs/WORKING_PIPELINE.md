# Working blog pipeline (final) — research-first

This pipeline is **separate** from Q1/Q2/Q3 import.  
It only **reads** `recipes_v2` + `all_ingredients` and **writes** `blog_posts`.

## Agent entrypoint

```bash
python scripts/blog_agent.py --recipe-id rec_mysore_masala_dosa --force --from-seed
python scripts/blog_agent.py --batch --limit 10
```

## Current working flow

```text
recipes_v2/{recipe_id}          ← read only
           │
           ▼
   duplicate check (skip if ready blog unless --force)
           │
           ▼
   research connectors + compress-only evidence
     → primary_question (1) + related_questions (4)
           │
           ▼
   capability selector (code) + slim OpenAI context
           │
           ▼
   OpenAI humanize (1 call, ≤1 retry) + structural validator
           │
           ▼
   blog_posts/{blog_id}         ← WRITE ONLY THIS COLLECTION
           │
           ▼
   Website (display layer — teaser caps in preview/teaser-config.js):
     blog_posts  → story / related problems / CTA (+ optional card fields from sync)
     recipes_v2  → ~80% ingredients, max 4 steps, image, pairings, storage
     all_ingredients → NOT loaded on blog (Ayurveda app-only)
```

## Two-layer model

| Layer | Role | Changed? |
|-------|------|----------|
| **Pipeline** (`blog_agent.py`, OpenAI) | Editorial → `blog_posts` | No |
| **Recipe DB** (`recipes_v2`) | Full recipe source of truth | No |
| **Website** (`landing.js`, `render.js`) | How much to **show** (teaser) | Yes |

Teaser rules (website only): `Math.ceil(ingredients × 0.8)` rows, max **4** preview steps, no Ayurveda accordion.

Local `preview/data/*.blog.json` remain pipeline artifacts; they are **not** deployed (`build_deploy.py` excludes them). The live site reads Firestore at runtime.

**Phase 2 (later):** Cloud Function gateway + lock `recipes_v2` client reads for anti-scrape. Pipeline still unchanged.

## Commands

```bash
# Research only
python scripts/research_recipe_questions.py --recipe-id rec_mysore_masala_dosa --from-seed

# Full agent
python scripts/blog_agent.py --recipe-id rec_mysore_masala_dosa --force --from-seed

# Local site
python -m http.server 8765 --directory preview
# → http://127.0.0.1:8765/post.html?slug=why-is-my-mysore-masala-dosa-not-crispy
```

## Daily reconcile (recipes_v2 ↔ blog_posts)

`blog_posts` is a **flat collection** (no subcollections). Match on **`recipe_id`**, not recipe name.

```bash
# Report gaps only
python scripts/blog_agent.py --reconcile --dry-run

# Delete duplicate Firestore docs, create missing blogs, sync to Firestore
python scripts/blog_agent.py --reconcile --cleanup-duplicates --sync-firestore

# Cap OpenAI spend per run (e.g. 3 new posts max)
python scripts/reconcile_blog_posts.py --max-create 3 --sync-firestore
```

**GitHub Actions (optional backup):** `.github/workflows/blog-reconcile.yml` — primary schedule is Cloud Function `blogReconcileScheduled` (uses `admin/dummy.oKey`, no GitHub OpenAI secret required).

Set secret **`FIREBASE_SERVICE_ACCOUNT`** only if using the GitHub workflow.

**One-time sync** (local → Firestore):

```bash
python scripts/sync_blog_posts_to_firestore.py
```

Requires `GOOGLE_APPLICATION_CREDENTIALS` or `FIREBASE_SERVICE_ACCOUNT` in `.env`.

## Env

`.env` (not committed):

```
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
FIREBASE_PROJECT_ID=sattva-srsti
```

Optional Admin auth: `GOOGLE_APPLICATION_CREDENTIALS=path/to/serviceAccount.json`

## Hosting

Static site files: `deploy/public/` (no bundled blog JSON). Domain: `sattvasrsti.blog`.

Deploy:

```bash
python scripts/build_deploy.py
npx firebase-tools deploy --only hosting:blog,firestore:rules --project sattva-srsti
```

Hosting site: **sattvasrsti-blog** → [https://sattvasrsti.blog](https://sattvasrsti.blog)
