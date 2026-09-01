# SattvaSrsti Blog

Marketing discovery blog: real cooking problem → useful answer → CTA into SattvaSrsti to customize the full recipe.

## Working pipeline (final)

See **`docs/WORKING_PIPELINE.md`**.

```bash
# Daily reconcile (recipes_v2 vs blog_posts — creates missing blogs only)
python scripts/blog_agent.py --reconcile --dry-run
python scripts/blog_agent.py --reconcile --cleanup-duplicates --sync-firestore

# Push local blogs → Firestore (needs GOOGLE_APPLICATION_CREDENTIALS)
python scripts/sync_blog_posts_to_firestore.py

# One recipe
python scripts/run_blog_pipeline.py --recipe-id rec_aloo_paratha

# Local preview
python -m http.server 8765 --directory preview
```

- Landing: http://127.0.0.1:8765/
- Writes **only** `blog_posts` (never `recipes_v2` / `all_ingredients`)

## Host / deploy

```bash
python scripts/build_deploy.py
# then upload deploy/public/ to Hostinger public_html
# or fill FTP_* in .env and run: python scripts/deploy_ftp.py
```

Details: `docs/HOSTINGER_ACCESS.md`

## Env

Copy `.env.example` → `.env` and fill secrets locally (do not commit `.env`).

Required for live agent:
- `OPENAI_API_KEY` — humanization
- Optional: `GOOGLE_APPLICATION_CREDENTIALS` — service account JSON (Admin writes)

## Blog agent (research-first)

```bash
# Mysore master post (live → blog_posts)
python scripts/blog_agent.py --recipe-id rec_mysore_masala_dosa --force --from-seed

# One recipe
python scripts/blog_agent.py --recipe-id rec_aloo_paratha

# Batch (skips recipe_ids that already have a ready blog unless --force)
python scripts/blog_agent.py --batch --limit 10
```

Pipeline internals: `scripts/run_blog_pipeline.py` + `scripts/research_recipe_questions.py`  
Prompt: `prompts/CONTEXT_PROMPT_PACK.md` · Capabilities: `prompts/capabilities.json`
