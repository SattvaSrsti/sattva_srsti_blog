# Blog pipeline — plain English

> **Current source of truth:** `docs/WORKING_PIPELINE.md`

This pipeline is **separate** from recipe import (Q1/Q2/Q3).  
It only **reads** `recipes_v2` / `all_ingredients` and **writes** `blog_posts`.

## Steps

1. **Read** recipe + ingredients + instructions (never edit those collections)
2. **Eligibility** — image + ingredients + warnings/about (code only)
3. **Humanize** — 1× OpenAI if `OPENAI_API_KEY`, else warning-based prose
4. **Write** slim `blog_posts/{blog_id}` (blog-unique fields only)
5. **Site** joins live recipe facts at read time (no duplicated ingredients/ayurveda in blog doc)

## Commands

```bash
python scripts/batch_first_n_blogs.py --limit 10
python scripts/run_blog_pipeline.py --recipe-id rec_aloo_paratha
python -m http.server 8765 --directory preview
```

## Hosting

`docs/HOSTINGER_ACCESS.md` — domain `sattvasrsti.blog` is parked until you upload `deploy/public/`.
