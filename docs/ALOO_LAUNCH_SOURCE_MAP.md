# Aloo Paratha blog — launch source map & API tokens

## API call (exactly one)

| Field | Value |
|--------|--------|
| Endpoint | `https://api.openai.com/v1/chat/completions` |
| Model | `gpt-4o-mini` |
| Calls | **1** |
| Input tokens | **487** |
| Output tokens | **383** |
| Total | **870** |

Report file: `preview/data/aloo-paratha.api-report.json`  
Context sent: `preview/data/aloo-paratha.llm-context.json`  
Humanized returned: `preview/data/aloo-paratha.humanized.json`

### What was sent to the API
- recipe title, cuisine, meal filters  
- 1 primary question + 5 candidate questions  
- mistake_warnings + sensory_cues from `instructions/details`  
- **Not** full ingredients list, **not** all 6 steps  

### What came back from the API
- `primary_question`, `hook`, `story`, `useful_answer`  
- 5× `common_questions`  
- `customize_mention`, `emotional_ending`, `meta_description`  

---

## Where each on-page block comes from

| UI block | Source |
|----------|--------|
| Hero image, time, difficulty, spice | `recipes_v2/rec_aloo_paratha` |
| Hero title + hook + story + short answer + FAQs + ending | **LLM** → stored conceptually as `blog_posts.humanized` |
| About / where dish sits | `recipes_v2.about_recipe` |
| Ingredients + amounts (live-joined; not stored on blog_posts) | `ingredients/details` |
| 3 preview steps + cues/warnings under steps | `instructions/details` |
| Nutrition ring (~617.5 kcal est.) | `all_ingredients/*/ingredient_nutrition` × canonical grams |
| Ayurveda cards | `all_ingredients/*/ingredient_ayurveda/profile` |
| Pairings | `pairing_recommendations` |
| Storage | `leftover_storage` |
| Hashtags | `search_tags` + brand (code) |

No dummy water/pinch rows. Salt is real DB **0.5 tsp**.

---

## Preview

Serve `preview/` and open http://127.0.0.1:8765/
