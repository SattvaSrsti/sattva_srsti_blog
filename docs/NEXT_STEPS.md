# Next steps — host + scale recipes

## What works now (local)

1. Landing: http://127.0.0.1:8765/
2. Post: http://127.0.0.1:8765/post.html?slug=aloo-paratha-dough-kept-tearing
3. Pipeline: `python scripts/run_blog_pipeline.py --recipe-id rec_aloo_paratha --from-local-blog`
4. Firestore write target: **only** `blog_posts/{blog_id}` (never `recipes_v2` / `all_ingredients`)

## Hosting (Hostinger)

Blog custom domain is **only** `sattvasrsti.blog` (Firebase Hosting). Do not point `sattvasrsti.com` / `sattvasrsti.in` at this blog.

**Fast path**
1. Fix or rebuild WordPress / static hosting on Hostinger
2. Upload `preview/` as the site root **or** publish via WP Application Password (see `docs/HOSTINGER_ACCESS.md`)
3. Point CTAs at your real app URL (`APP_RECIPE_BASE`)

**Needed from you**
- Working domain (no 500)
- WP app password **or** static FTP upload access
- Final app deep-link / Play Store URL for CTAs

## Other recipes (same pipeline)

```bash
python scripts/run_blog_pipeline.py --recipe-id rec_mysore_masala_dosa
```

Requires `OPENAI_API_KEY` for a new humanize call.  
Use `--from-local-blog` only when a local `*.blog.json` already exists for that recipe.  
Use `--skip-write` to assemble locally without touching Firebase.

## Security note

App `firestore.rules` are currently open (dev). Before public launch, lock rules so only your backend/service account can write `blog_posts`, and keep `recipes_v2` / `all_ingredients` read-only for the blog pipeline.
