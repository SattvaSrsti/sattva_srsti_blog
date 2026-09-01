# App deep links from the blog

All SattvaSrsti buttons on the blog open the **app site**, not the blog domain.

## Pattern

```text
https://sattvasrsti.com/recipe/{recipe_slug}?utm_source=blog&utm_medium=cta&utm_campaign={blog_slug}&utm_content={button_id}
```

| Part | Source |
|------|--------|
| Host | `APP_RECIPE_BASE` → `https://sattvasrsti.com/recipe` |
| `{recipe_slug}` | `recipes_v2.slug` (e.g. `mysore-masala-dosa`) |
| `{blog_slug}` | blog post slug (campaign tracking) |
| `{button_id}` | which CTA: `cta-hero`, `cta-preview`, `cta-final`, `nav-app`, … |

## Examples

Mysore hero button:

```text
https://sattvasrsti.com/recipe/mysore-masala-dosa?utm_source=blog&utm_medium=cta&utm_campaign=why-is-my-mysore-masala-dosa-not-crispy&utm_content=cta-hero
```

Upma:

```text
https://sattvasrsti.com/recipe/upma?utm_source=blog&utm_medium=cta&utm_campaign=why-does-my-upma-not-turn-out-right&utm_content=cta-hero
```

Generic “Open app” (no recipe):

```text
https://sattvasrsti.com
```

## Important

- Blog lives on **`sattvasrsti.blog`**
- Recipe CTAs go to **`sattvasrsti.com/recipe/{slug}`**
- DNS for `.com` must point at the **app** host (not the blog Hosting site)

Configured in: `preview/render.js`, `.env` → `APP_RECIPE_BASE`
