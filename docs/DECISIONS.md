# Locked decisions (v1)

Taken so we can ship a first loop without waiting on every preference.

**Blog content rules:** see `docs/BLOG_SPECIFICATION.md` (LOCKED).  
**Master template:** `preview/` rendered from `preview/data/aloo-paratha.blog.json`.

## Product

1. **Blog = discovery layer.** Full recipe stays in SattvaSrsti (Preeti rules).
2. **Public blog host:** Firebase Hosting; custom domain **only** `sattvasrsti.blog` (not `.com` / `.in`).
3. **Source of truth for content generation:** Firestore `recipes_v2` + new `blog_posts` + `content_hashtags`.
4. **First recipe live demo:** `rec_aloo_paratha` (image + ingredients + 6 steps available).
5. **CTA destination:**  
   `https://sattvasrsti.com/recipe/{slug}?utm_…`  
   (`{slug}` = `recipes_v2.slug`, e.g. `mysore-masala-dosa`)  
   Swap base URL via `APP_RECIPE_BASE` in `.env` if the app host changes.
6. **Every post shows exactly one capability** (see `prompts/CONTEXT_PROMPT_PACK.md`).
7. **Hashtags are canonical in Firestore**, copied to blog footer + Instagram + YouTube + Pinterest.

## Theme

- Name: **Sattva Discovery**
- Look: warm paper wash, sage brand, clay CTA, Fraunces + Source Sans 3
- Hero: full-bleed recipe image from Firebase Storage
- Above-fold CTA to app (not “jump to full recipe card”)
- Ingredients with quantities; **3-step lock banner**
- Differentiator vs RecipeTin/Minimalist Baker: we intentionally withhold the rest of the method

## API / prompting

- Use **context prompting**: system policy + full `recipe_context` JSON + one `capability_id`
- Reject thin prompts like “write an emotional blog about aloo paratha”
- Output JSON only → map into WordPress post + social captions

## Out of scope for this first show

- Live WordPress deploy (needs your Hostinger access)
- Writing into production Firestore (needs your approval + service account)
- Building full app web recipe pages
