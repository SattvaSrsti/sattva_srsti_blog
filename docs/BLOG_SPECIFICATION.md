# SattvaSrsti Blog Specification (LOCKED v1)

Status: **LOCKED v1.1 — acquisition knowledge node**  
Primary goal: answer a **real food question** people already search, then lead them to the full SattvaSrsti recipe.  
Not: an ad-driven recipe blog. Not: an app landing page. Not: a full recipe dump.

**Funnel:** Search/Quora/Social → Blog answer → Recipe → (later) Community / Reviews / Related → User cooks → Feedback

**Revenue stance:** Optimize for valuable traffic into SattvaSrsti first. Ads are optional later — never the page design driver.

---

## Content hierarchy (always)

| Priority | Role |
|----------|------|
| 1 Primary | Human food story (problem → frustration → discovery → relief) |
| 2 Secondary | Useful recipe intelligence (quantities, tips, culture, storage…) |
| 3 Tertiary | SattvaSrsti product (appears because it solved the problem) |

If a section serves only product marketing, cut it.

---

## Mandatory vs optional

### MANDATORY (every post)

| # | Element | Rules |
|---|---------|--------|
| M1 | Primary question headline | Searchable cooking question when possible (“Why does…?”). |
| M2 | Hero image | From recipe `image_primary_url`. Descriptive alt text. |
| M3 | Opening situation | Short. Real kitchen. No purple prose. |
| M3b | Useful answer | Short practical answer from warnings/cues. Before product pitch. No ingredient quantity / base-ratio block. |
| M4 | Cultural context | 2–4 sentences. Not Wikipedia. |
| M5 | Problem → product moment | Natural. No Firestore/IDs/“structured data”. |
| M6 | Ingredients WITH quantities | Live-joined from `recipes_v2` ingredients/details (not stored on blog_posts). Never invent. |
| M7 | Ingredient grouping | Dough / Filling / Cooking (or best-fit). |
| M8 | Exactly 3 preview steps | Not full method. |
| M9 | Full-recipe separation | Remaining steps on SattvaSrsti. |
| M10 | One capability demonstrated | Exactly one `capability_id`. |
| M11 | Practical tip block | Problem-solving. |
| M11b | Common questions | 3–5 Q&As from mistake_warnings / real questions when available. |
| M12 | Pairings | Reader-facing list. |
| M13 | Emotional ending | Closure before final CTA. |
| M14 | CTA set (max 3) | Hero + after preview + final. |
| M15 | Author + dates | Required. |
| M16 | Breadcrumbs | Home → Blog → Category → Page |
| M17 | SEO head | title, description, canonical, OG, Twitter |
| M18 | JSON-LD | Article + BreadcrumbList; FAQPage when common_questions present; no full Recipe |
| M19 | UTM on app CTAs | Required |
| M20 | Hashtags | Brand + recipe; no tech explanation on page |

### OPTIONAL (include when Firestore has real data)

| # | Element | Rules |
|---|---------|--------|
| O1 | Storage / leftover | Use `leftover_storage` when present. |
| O2 | Nutrition summary | Only real recipe nutrition docs. Omit if missing. |
| O3 | Safety note | From safety_notes / genuine risk. One short block. |
| O4 | Customization tease | Links to app. |
| O5 | Substitutions | From `ingredient_intelligence.substitution_candidates`. |
| O6 | Related recipes | From recipe graph. |
| O7 | Grocery tease | Only if capability fits. |
| O8 | Social destination links | Only real URLs. |
| O9 | Community / reviews | Only when real data exists — else omit. |

### FORBIDDEN on public pages

- `recipes_v2`, recipe document IDs, Firestore, “canonical hashtags”, “structured data”
- Full cooking method (more than 3 steps)
- Invented nutrition, storage, or related recipes
- Fake YouTube/Instagram search URLs presented as “our content”
- More than 3 primary CTAs to the app
- Purple prose / SEO keyword stuffing / “Once upon a time”

---

## Section order (master template)

1. Site header (brand + Blog + single soft App link in nav)
2. Breadcrumbs  
3. Hero: **primary question as H1** + hook + image + meta + **CTA #1**  
4. Short story (situation) — optional length, keep tight  
5. **Useful answer** (short practical fix; no base-ratio / quantity dump) — mandatory for question posts  
6. Cultural context (2–4 sentences)  
7. Problem → SattvaSrsti (natural, one capability)  
8. Ingredients (grouped, quantities)  
9. Substitutions (optional — from ingredient intelligence)  
10. Customization tease (optional)  
11. Cooking preview (3 steps) + lock + **CTA #2**  
12. Practical tip  
13. **Common questions** (3–5; from mistake_warnings / real search questions — not a “Quora” dump)  
14. Pairings  
15. Storage / safety / health (optional; real data only)  
16. Community / reviews — **omit until real data exists** (cross-link later, don’t fake)  
17. Emotional ending  
18. **CTA #3**  
19. Related recipes  
20. Hashtags / share  
21. Footer  

### FAQ JSON-LD
When `common_questions` has ≥1 item, emit `FAQPage` JSON-LD matching visible Q&As. Still **no full Recipe schema** on discovery posts.  

---

## CTA policy

| Slot | Placement | Label style |
|------|-----------|-------------|
| CTA #1 | Hero | “Cook the full recipe on SattvaSrsti” |
| CTA #2 | After 3-step lock | “Continue the remaining steps” |
| CTA #3 | After emotional ending | “Open Aloo Paratha on SattvaSrsti” |

Nav “App” link is allowed once; do not duplicate mid-article banners beyond the three CTAs.

---

## SEO policy

### Always
- Unique `<title>` (problem-led, include dish name once)
- Meta description ≤ 155 chars, useful, not stuffed
- Canonical = public blog URL
- `og:*` + `twitter:card=summary_large_image`
- JSON-LD `Article` (headline, image, datePublished, dateModified, author, description)
- JSON-LD `BreadcrumbList`

### Recipe schema
**Default for discovery posts: do NOT emit full `Recipe` JSON-LD** while only 3 steps are shown.  
Reason: we must not claim a complete recipe in structured data when the page withholds the method.

Exception (future): if a post is explicitly a full recipe mirror, then `Recipe` is allowed — out of scope for v1 discovery blogs.

---

## Architecture (required going forward)

```text
recipes_v2 (+ subcollections)
    → Blog Generator (context prompt + capability_id)
    → blog_posts JSON  (Firestore)
    → SEO Renderer / Template
    → Public page (WordPress or static)
    → CTA → SattvaSrsti full recipe
```

Hard-coded HTML is allowed only as a **rendered preview** of a JSON document.  
Master content lives in `blog_posts` JSON (see `firestore/schemas/blog_posts.json`).

---

## Voice

- Short sentences. Conversational.
- Specific > dramatic.
- Product name appears where it earned its place — not every paragraph.

Better: “I wanted Ratatouille, but I had somehow made it much spicier than I expected.”  
Worse: “As the aroma transported me through the timeless corridors…”

---

## Compliance checklist (gate before publish)

- [ ] Hierarchy feels story-first, product-third  
- [ ] No technical/internal language on page  
- [ ] ≤ 3 app CTAs  
- [ ] Grouped ingredients with quantities  
- [ ] Exactly 3 steps  
- [ ] Cultural context present  
- [ ] Emotional ending present (before final CTA)  
- [ ] Pairings as a proper section  
- [ ] Storage/nutrition/safety only if real data  
- [ ] SEO head + Article + BreadcrumbList JSON-LD  
- [ ] Author + dates + breadcrumbs  
- [ ] Related recipes real or omitted  
- [ ] Social links real or hashtag-only  

**Aloo Paratha page must pass 100% of mandatory items before it is called the master template.**
