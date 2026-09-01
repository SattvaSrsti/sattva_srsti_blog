# Sattva Srsti — Complete Firestore Database Structure

**Project ID:** `sattva-srsti`  
**Source of truth for this doc:** app constants (`firestore_constants.dart`), dash schemas (flavour / behavior / ayurveda), local audit `exports/live_firestore_audit.json` (2026-05-22), and observed `recipes_v2` / `all_ingredients` shapes.  
**Scope:** every collection / subcollection / field type + example values.  

---

## 0. Map at a glance

```text
sattva-srsti (Firestore)
│
├── recipes_v2/{recipe_id}                          ← CANONICAL recipes (app)
│   ├── ingredients/details
│   ├── instructions/details
│   ├── identity_ingredient_ids/details
│   ├── nutrition/details                           ← optional (often missing)
│   └── nutritional_content_v2/details              ← optional alternate
│
├── all_ingredients/{ingredient_id}                 ← CANONICAL ingredient master
│   ├── ingredient_core/details
│   ├── ingredient_intelligence/details
│   ├── ingredient_nutrition/details
│   ├── ingredient_flavour/profile
│   ├── ingredient_behavior/profile
│   └── ingredient_ayurveda/profile
│
├── users/{uid}                                     ← users (new + legacy fields)
│   ├── taste_profile/main
│   ├── health_profile/main
│   ├── nutrition_profile/main
│   ├── cooking_preferences/main
│   ├── ai_preferences/main
│   ├── dashboard_preferences/main
│   ├── subscriptions/main
│   ├── user_pantry/{itemId}
│   ├── shopping_list/{itemId}
│   ├── saved_recipes/{recipeId}
│   ├── cooking_history/{entryId}
│   ├── recipe_collections/{collectionId}
│   ├── address/{…}          (legacy)
│   ├── wishlist/{…}         (legacy)
│   ├── orders/{…}           (legacy)
│   └── cart/{…}             (legacy)
│
├── blog_posts/{blog_id}                            ← PLANNED (blog pipeline write-only)
├── content_hashtags/{htag_id}                      ← PLANNED (keywords/hashtags pack)
│
├── recipe/{docId}                                  ← LEGACY (~428 recipes)
├── recipes/{docId}                                 ← LEGACY mirror (~428)
├── category/{docId}                                ← LEGACY
├── ingredients/{categoryId}                        ← LEGACY category buckets
├── admin/{docId}                                   ← LEGACY admin/config
├── recipe_v2_failed_generations/{docId}            ← LEGACY/ops
└── recipe_v2_pending_ingredient_mappings/{docId}   ← LEGACY/ops
```

**Type legend**

| Type | Meaning |
|------|---------|
| `string` | Text |
| `number` | int or double |
| `boolean` | true/false |
| `timestamp` | Firestore Timestamp |
| `array<string>` | List of strings |
| `array<object>` | List of maps |
| `map` | Nested object |
| `null` | Explicitly empty / not set |

---

## 1. `recipes_v2` (canonical recipe)

**Path:** `recipes_v2/{recipe_id}`  
**Doc ID example:** `rec_aloo_paratha`  
**Status:** live / primary for app + blog reads

### 1.1 Root document fields

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `recipe_id` | string | `"rec_aloo_paratha"` | Same as doc id ideally |
| `title` | string | `"Aloo Paratha"` | |
| `slug` | string | `"aloo-paratha"` | URL-safe |
| `status` | string | `"published"` | e.g. published |
| `about_recipe` | string | `"Aloo Paratha is a popular North Indian flatbread…"` | |
| `image_primary_url` | string | `"https://firebasestorage.googleapis.com/.../rec_aloo_paratha.jpg?alt=media&token=…"` | |
| `cuisine` | string | `"North Indian"` | May be comma-joined regions |
| `dish_type` | string | `"Main Course"` | |
| `difficulty` | string | `"Medium"` | |
| `meal_type` | string | `"Breakfast"` | when present |
| `servings` | number | `1` | |
| `prep_time_minutes` | number | `20` | |
| `cook_time_minutes` | number | `15` | |
| `total_time_minutes` | number | `35` | |
| `ingredient_count` | number | `8` | |
| `step_count` | number | `6` | |
| `diet_tags` | array\<string\> | `["vegetarian","high-fiber","egg-free"]` | |
| `alternative_names` | array\<string\> | `["Stuffed Potato Paratha"]` | |
| `search_tags` | array\<string\> | `["aloo paratha","stuffed paratha","Indian flatbread"]` | **keywords source** |
| `dish_categories` | array\<string\> | `["flatbread","stuffed"]` | |
| `meal_preference_tags` | array\<string\> | `["comfort_food","quick_meal"]` | |
| `cooking_method_tags` | array\<string\> | `["stovetop","pan-frying"]` | |
| `equipment_required` | array\<string\> | `["tawa","spatula"]` | |
| `pairing_recommendations` | array\<string\> | `["yogurt","pickle","butter"]` | |
| `age_group_tags` | array\<string\> | `["kids","adults"]` | |
| `spice_tolerance_level` | string | `"medium"` | |
| `choking_risk_level` | string | `"low"` | |
| `flavor_profile` | map\<string,number\> | `{"salty":6,"spicy":5,"umami":4}` | scores typically 0–10 |
| `occasions` | array\<object\> | see below | |
| `sections_available` | array\<string\> | `["ingredients","instructions","identity_ingredient_ids"]` | |
| `q123_total_tokens` | number | `12345` | import pipeline metric |
| `pipeline_status.q1` | string | `"success"` | dotted keys may appear |
| `pipeline_status.q2` | string | `"success"` | |
| `pipeline_status.q3` | string | `"success"` | |
| `pipeline_status.recipe_nutrition` | string | `"success"` | may succeed even if nutrition doc missing |
| `mood_tags` | array\<string\> | `["crispy","spicy"]` | seen on some recipes (e.g. dosa) |
| `effort_level` | string | `"involved"` | seen on some recipes |

#### `occasions[]` object

| Field | Type | Example |
|-------|------|---------|
| `type` | string | `"everyday_meal"` / `"weekend_meal"` / `"festival"` |
| `name` | string | `"South Indian Breakfast"` |
| `region` | string | `"Karnataka"` |

### 1.2 Subcollection `ingredients` → doc `details`

**Path:** `recipes_v2/{recipe_id}/ingredients/details`

| Field | Type | Example |
|-------|------|---------|
| `recipe_id` | string | `"rec_aloo_paratha"` |
| `base_yield` | map | see below |
| `ingredients` | array\<object\> | ingredient lines |

#### `base_yield`

| Field | Type | Example |
|-------|------|---------|
| `servings` | number | `1` |
| `description` | string | `"1 serving"` |

#### `ingredients[]` line object

| Field | Type | Example |
|-------|------|---------|
| `ingredient_id` | string | `"ing_potato"` |
| `display_name` | string | `"Potato"` |
| `amount` | number | `150` |
| `unit` | string | `"g"` |
| `canonical_amount` | number | `150` |
| `canonical_unit` | string | `"g"` |
| `ingredient_role` | string | `"base"` / `"spice"` / `"fat"` |
| `preparation_state` | string | `"boiled"` / `"raw"` |
| `requirement_level` | string | `"required"` / `"optional"` |

**Example line**

```json
{
  "ingredient_id": "ing_potato",
  "display_name": "Potato",
  "amount": 150,
  "unit": "g",
  "canonical_amount": 150,
  "canonical_unit": "g",
  "ingredient_role": "base",
  "preparation_state": "boiled",
  "requirement_level": "required"
}
```

### 1.3 Subcollection `instructions` → doc `details`

**Path:** `recipes_v2/{recipe_id}/instructions/details`

| Field | Type | Example |
|-------|------|---------|
| `recipe_id` | string | `"rec_aloo_paratha"` |
| `steps` | array\<object\> | ordered steps |
| `timing_model` | map | active/passive/elapsed minutes |
| `leftover_storage` | map | fridge / reheat / shelf life |

#### `timing_model`

| Field | Type | Example |
|-------|------|---------|
| `total_active_minutes` | number | `25` |
| `total_passive_minutes` | number | `10` |
| `total_elapsed_minutes` | number | `35` |

#### `leftover_storage`

| Field | Type | Example |
|-------|------|---------|
| `refrigeration` | string | `"Store in an airtight container in the fridge."` |
| `reheat` | string | `"Reheat on a pan or microwave until warm."` |
| `shelf_life` | string | `"Consume within 2 days."` |

#### `steps[]` object

| Field | Type | Example |
|-------|------|---------|
| `step` | number | `5` | (also seen as step_number in some payloads) |
| `duration_minutes` | number | `3` |
| `instruction_text` | string | `"Gently roll the filled dough…"` |
| `voice_text` | string | `"Roll gently from the center."` |
| `ingredient_refs` | array\<string\> | `["ing_potato","ing_whole_wheat_flour"]` |
| `mistake_warnings` | array\<string\> | `["Do not press too hard to avoid tearing."]` |
| `safety_notes` | array\<string\> | `["Handle hot pan carefully."]` |
| `sensory_cues` | array\<string\> | `["even thickness","golden brown spots"]` |
| `step_temperature_level` | string | `"medium"` |
| `cooking_temperature` | map\|null | see below |

#### `cooking_temperature` (optional)

| Field | Type | Example |
|-------|------|---------|
| `value` | number | `180` |
| `unit` | string | `"C"` |
| `description` | string | `"medium heat"` |

### 1.4 Subcollection `identity_ingredient_ids` → doc `details`

**Path:** `recipes_v2/{recipe_id}/identity_ingredient_ids/details`

| Field | Type | Example |
|-------|------|---------|
| `recipe_id` | string | `"rec_aloo_paratha"` |
| `identity_ingredient_ids` | array\<string\> | `["ing_whole_wheat_flour","ing_potato","ing_ghee"]` |

### 1.5 Subcollection `nutrition` → doc `details` (optional)

**Path:** `recipes_v2/{recipe_id}/nutrition/details`  
Often **missing** even if pipeline status says success.

| Field | Type | Example |
|-------|------|---------|
| `nutrition_per_serving` | map | macros per serving |
| `aggregated_nutrition` | map | alternate shape |
| `total_nutrition` | map | alternate shape |

Typical nested macros (when present):

| Field | Type | Example |
|-------|------|---------|
| `calories_kcal` | number | `320` |
| `protein_g` | number | `8` |
| `carbohydrates_g` | number | `45` |
| `fat_g` | number | `12` |
| `fiber_g` | number | `5` |

### 1.6 Subcollection `nutritional_content_v2` → doc `details` (optional alternate)

Same purpose as nutrition; repository tries this if `nutrition` missing.

---

## 2. `all_ingredients` (canonical ingredient master)

**Path:** `all_ingredients/{ingredient_id}`  
**Doc ID example:** `ing_potato`

### 2.1 Root document

| Field | Type | Example |
|-------|------|---------|
| `ingredient_id` | string | `"ing_potato"` |
| `status` | string | `"active"` |
| `updated_at` | timestamp | |

### 2.2 `ingredient_core` → `details`

**Path:** `all_ingredients/{id}/ingredient_core/details`

| Field | Type | Example |
|-------|------|---------|
| `ingredient_id` | string | `"ing_potato"` |
| `display_name` | string | `"Potato"` |
| `display_names` | map\|array | localized names when present |
| `slug` | string | `"potato"` |
| `status` | string | `"active"` |
| `version` | number\|string | `1` |
| `ingredient_form_type` | string | `"whole"` / powder / etc. |
| `physical_state` | string | `"solid"` |
| `canonical_unit` | string | `"g"` |
| `measurement_behavior` | string\|map | how amounts behave |
| `storage_category` | string | `"produce"` |
| `ingredient_category_tags` | array\<string\> | `["vegetable","tuber"]` |
| `diet_tags` | array\<string\> | `["vegan","vegetarian"]` |
| `allergen_tags` | array\<string\> | `[]` |
| `search_keywords` | array\<string\> | `["potato","aloo","alu","batata"]` | **hashtag/keyword source** |
| `aliases` | array\<string\> | `["aloo"]` |
| `direct_tags` | array\<string\> | |
| `ingredient_image_url` | string | Storage URL |

### 2.3 `ingredient_intelligence` → `details`

| Field | Type | Example |
|-------|------|---------|
| `ingredient_id` | string | `"ing_potato"` |
| `food_science` | string\|map | science notes |
| `how_it_is_made` | string | |
| `how_it_looks` | string | |
| `how_to_store` | string | |
| `ingredient_health_benefits` | string\|array | |
| `quality_and_adulteration` | string\|map | |
| `unit_conversions` | map\|array | |
| `g_per_ml` | number | density helper |
| `serving_reference` | map\|string | |
| `substitution_candidates` | array\<object\> | see below |

#### `substitution_candidates[]`

| Field | Type | Example |
|-------|------|---------|
| `ingredient_id` | string | `"ing_sweet_potato"` |
| `display_name` | string | `"Sweet potato"` |
| `reason` | string | `"Works in mashing with sweeter flavor…"` |
| `similarity_score` | number | `0.72` |
| `usage_note` | string | `"Reduce sugar elsewhere"` |
| `replacement_ratio` | string\|number | `"1:1"` |

### 2.4 `ingredient_nutrition` → `details`

| Field | Type | Example |
|-------|------|---------|
| `ingredient_id` | string | `"ing_potato"` |
| `nutrition_per_100g` | map | see below |
| `wellness_tags` | array\<string\> | |
| `health_alerts` | array\|map | |
| `glycemic_metrics` | map | |
| `protein_quality` | map\|string | |

#### `nutrition_per_100g` example (potato)

```json
{
  "macronutrients": {
    "calories_kcal": 77,
    "protein_g": 2,
    "carbohydrates_g": 17.5,
    "fat_g": 0.1,
    "fiber_g": 2.2,
    "sugar_g": 0.8
  },
  "micronutrients": {
    "sodium_mg": 6,
    "potassium_mg": 425,
    "vitamin_c_mg": 19.7,
    "iron_mg": 0.8,
    "calcium_mg": 12
  }
}
```

### 2.5 `ingredient_flavour` → `profile`

| Field | Type | Example |
|-------|------|---------|
| `ingredient_name` | string | `"potato"` |
| `source` | string | `"ai"` / pipeline |
| `prompt_version` | string | |
| `ingredient_flavour` | map\<string,number\> | axes 0–10 |

**Locked flavour axes (int 0–10):**  
`sweet`, `salty`, `sour`, `bitter`, `spicy`, `pungent`, `umami`, `earthy`, `nutty`, `creamy`, `smoky`, `herbal`, `fresh`

### 2.6 `ingredient_behavior` → `profile`

| Field | Type | Example |
|-------|------|---------|
| `ingredient_name` | string | `"potato"` |
| `heat` | map\|string | tolerance / ideal heat |
| `timing` | map\|string | add stage |
| `texture` | map\|array | softens / crisps / … |
| `flavor_change` | map\|array | overcook bitterness etc. |
| `failures` | array\<object\> | see below |

#### `failures[]`

| Field | Type | Allowed / Example |
|-------|------|-------------------|
| `trigger` | string | `high_heat`, `cook_too_long`, `too_much_water`, … |
| `effect` | string | `burnt`, `mushy`, `undercooked`, … |
| `severity` | string | `low` \| `medium` \| `high` \| `critical` |

**Example (potato):**

```json
[
  { "trigger": "high_heat", "effect": "burnt", "severity": "high" },
  { "trigger": "cook_too_long", "effect": "mushy", "severity": "medium" },
  { "trigger": "too_much_water", "effect": "mushy", "severity": "medium" }
]
```

### 2.7 `ingredient_ayurveda` → `profile`

| Field | Type | Example |
|-------|------|---------|
| `ingredient_name` | string | `"potato"` |
| `confidence` | string | `"high"` \| `"medium"` \| `"low"` |
| `ingredient_ayurveda` | map | nested ayurveda |

#### `ingredient_ayurveda` nested

| Field | Type | Example |
|-------|------|---------|
| `rasa.primary` | string | `"madhura"` |
| `rasa.secondary` | array\<string\> | `["kashaya"]` |
| `virya` | string | `"shita"` |
| `vipaka` | string | `"madhura"` |
| `guna` | array\<string\> | `["guru","ruksha","manda"]` |
| `dosha_effect.vata` | string | `"aggravates"` \| `"balances"` \| `"neutral"` |
| `dosha_effect.pitta` | string | `"balances"` |
| `dosha_effect.kapha` | string | `"aggravates"` |
| `food_quality` | string | `"sattvic"` \| `"rajasic"` \| `"tamasic"` |
| `agni_effect` | string | `"kindles"` \| `"balances"` \| `"reduces"` |

---

## 3. `users` (app user)

**Path:** `users/{uid}`

### 3.1 Root (new app fields)

| Field | Type | Example |
|-------|------|---------|
| `uid` | string | Firebase Auth uid |
| `displayName` | string | `"Preeti"` |
| `email` | string | `"user@email.com"` |
| `phoneNumber` | string | `"+91…"` |
| `photoUrl` | string | |
| `isOnboarded` | boolean | `true` |
| `createdAt` | timestamp | |
| `updatedAt` | timestamp | |
| `lastLoginAt` | timestamp | |
| `onboardingCompleted` | boolean | legacy |

### 3.2 Root (legacy encrypted / old app fields)

| Field | Type | Example |
|-------|------|---------|
| `id` | string | uid |
| `userName` | string | |
| `image` | string | |
| `data` | string\|map | often encrypted payload |
| `InstalledDate` | string\|timestamp | |
| `lastWatchedAd` | string\|timestamp | |

### 3.3 Profile singletons (`…/main`)

#### `taste_profile/main`

| Field | Type | Example |
|-------|------|---------|
| `kitchen_personality_tags` | array\<string\> | |
| `spice_level` | string\|number | `"medium"` |
| `dietary_profile_tags` | array\<string\> | |
| `special_diet_tags` | array\<string\> | |
| `health_goal_tags` | array\<string\> | |
| `favorite_meal_types` | array\<string\> | |
| `completed` | boolean | `true` |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

#### `health_profile/main`

| Field | Type | Example |
|-------|------|---------|
| `allergies` | array\<string\> | `["peanut"]` |
| `diseases` | array\<string\> | |
| `healthGoals` | array\<string\> | |
| `dietaryRestrictions` | array\<string\> | |

#### `nutrition_profile/main`

| Field | Type | Example |
|-------|------|---------|
| `dailyCalories` | number | `2000` |
| `proteinGoal` | number | `80` |
| `carbGoal` | number | `220` |
| `fatGoal` | number | `60` |
| `fiberGoal` | number | `25` |

#### `cooking_preferences/main`

| Field | Type | Example |
|-------|------|---------|
| `preferredCookingTime` | string\|number | `30` |
| `difficultyLevel` | string | `"easy"` |
| `favoriteOccasions` | array\<string\> | |

#### `ai_preferences/main`

| Field | Type | Example |
|-------|------|---------|
| `preferredAssistantStyle` | string | `"friendly"` |
| `voiceCookingEnabled` | boolean | `true` |
| `smartSuggestionsEnabled` | boolean | `true` |

#### `dashboard_preferences/main`

| Field | Type | Example |
|-------|------|---------|
| `showNutritionCard` | boolean | `true` |
| `showPantryCard` | boolean | `true` |
| `showRecommendations` | boolean | `true` |

#### `subscriptions/main`

| Field | Type | Example |
|-------|------|---------|
| `plan` | string | `"free"` / `"premium"` |
| `status` | string | `"active"` |
| `startedAt` | timestamp | |
| `expiresAt` | timestamp | |

### 3.4 List-style user subcollections

#### `user_pantry/{itemId}`

| Field | Type | Example |
|-------|------|---------|
| `ingredientId` | string | `"ing_potato"` |
| `ingredientName` | string | `"Potato"` |
| `quantity` | number | `2` |
| `unit` | string | `"kg"` |
| `expiryDate` | timestamp\|string | |
| `confidence` | number\|string | |

#### `shopping_list/{itemId}`

| Field | Type | Example |
|-------|------|---------|
| `ingredientId` | string | |
| `ingredientName` | string | |
| `quantity` | number | |
| `unit` | string | |
| `isPurchased` | boolean | `false` |

#### `saved_recipes/{recipeId}`

| Field | Type | Example |
|-------|------|---------|
| `savedAt` | timestamp | |
| (+ recipe ref id as doc id) | | |

#### `cooking_history/{entryId}`

| Field | Type | Example |
|-------|------|---------|
| `cookedAt` | timestamp | |
| `rating` | number | `5` |
| `customized` | boolean | `false` |
| (+ recipe id fields as used by session repo) | | |

#### `recipe_collections/{collectionId}`

User-created recipe lists (structure app-defined; typically name + recipe id list).

### 3.5 Legacy user subcollections

`address`, `wishlist`, `orders`, `cart` — used by older commerce flows.

---

## 4. Planned blog collections (write targets for blog pipeline)

> Blog pipeline **reads** `recipes_v2` / `all_ingredients` and **writes only** these. It does not mutate recipe/ingredient docs.

### 4.1 `blog_posts/{blog_id}`

Blog-unique marketing fields only. **Never** store `base_ratio`, ingredient quantities, steps, ayurveda, nutrition, hashtags, or other recipe facts — those stay in `recipes_v2` / `all_ingredients` and are live-joined at read time (Ingredients section only for quantities).

| Field | Type | Example |
|-------|------|---------|
| `blog_id` | string | `"blog_aloo-paratha-dough-kept-tearing"` |
| `recipe_id` | string | `"rec_aloo_paratha"` | pointer only |
| `slug` | string | `"aloo-paratha-dough-kept-tearing"` |
| `status` | string | `draft` \| `ready` \| `published` \| `skipped_*` |
| `primary_question` | string | `"Why does my aloo paratha keep tearing?"` |
| `seo_title` | string | `"… \| SattvaSrsti"` |
| `meta_description` | string | SEO snippet (~155 chars) |
| `blog_public_url` | string\|null | Hostinger URL after publish |
| `humanized` | map | LLM prose only |
| `customize_fixed` | map | brand CTA copy (not LLM) |

#### `humanized` (LLM keys only)

| Key | Type |
|-----|------|
| `hook` | string |
| `story` | array\<string\> |
| `useful_answer` | string (no base_ratio / quantity dump) |
| `common_questions` | array\<object\> `{q,a}` length 5 |
| `emotional_ending` | string |

### 4.2 `content_hashtags/{htag_id}`

Doc id pattern: `htag_{recipe_id}` e.g. `htag_rec_aloo_paratha`

| Field | Type | Example |
|-------|------|---------|
| `recipe_id` | string | `"rec_aloo_paratha"` |
| `slug` | string | `"aloo-paratha"` |
| `keywords` | array\<string\> | from `search_tags` + names |
| `brand_hashtags` | array\<string\> | `["#SattvaSrsti","#SattvaSrstiRecipes","#CookWithSattva"]` |
| `recipe_hashtags` | array\<string\> | `["#AlooParatha","#StuffedParatha"]` |
| `ingredient_hashtags` | array\<string\> | `["#Aloo","#Atta","#Ghee"]` |
| `category_hashtags` | array\<string\> | `["#VegetarianBreakfast"]` |
| `instagram_hashtags` | array\<string\> | max 5 |
| `youtube_keywords` | array\<string\> | without `#` |
| `full_display_string` | string | space-joined hashtags |
| `updated_at` | timestamp | |

---

## 5. Legacy / other root collections

### 5.1 `recipe` and `recipes` (~428 each)

Monolithic recipe documents (older schema). Common top-level keys from audit:

| Field | Type (typical) | Notes |
|-------|----------------|-------|
| `recipe_name` | string | |
| `about_the_recipe` | string | |
| `alternative_name` | string\|array | |
| `ingredients` | array\<object\> | nested; often `ingredient_name` |
| `cooking_instructions` | array\|map | |
| `health_and_nutrition` | map | |
| `images` | array | |
| `cuisine_type` | string | |
| `dish_type` | string | |
| `dish_category` | string | |
| `meal_type` | string | |
| `region` | string | |
| `season` | string\|array | |
| `occasion` | string\|array | |
| `preparation_time` | string\|number | |
| `cooking_time` | string\|number | |
| `cooking_difficulty` | string | |
| `special_diets` | array | |
| `pairing_recommendations` | array | |
| `cultural_significance` | string | |
| `usage` | string\|map | |
| `price` / `standard_price` / `spicy_price` | number\|map | commerce |
| `likes` / `shares` | number | |
| `trending` / `top_selling` | boolean\|number | |
| `age_group` | string\|array | |
| `index` | number | |
| `createdAt` | timestamp | |

Prefer **`recipes_v2`** for new work.

### 5.2 `category`

Category docs for browsing (legacy). Fields vary; used for cuisine/category UI.

### 5.3 `ingredients` (legacy buckets)

Doc ids like `dry_goods`, `fresh_goods`, `oils_and_liquids` — category groupings with nested item lists (audit: ~206 sample items under categories).

### 5.4 `admin`

Config docs e.g. `discount`, `dummy`, `images` (encryption keys / assets config in older app).

### 5.5 Ops leftovers

| Collection | Purpose |
|------------|---------|
| `recipe_v2_failed_generations` | failed generation logs |
| `recipe_v2_pending_ingredient_mappings` | pending mappings |

---

## 6. Full example: Aloo Paratha (assembled)

### Root `recipes_v2/rec_aloo_paratha` (abbreviated)

```json
{
  "recipe_id": "rec_aloo_paratha",
  "title": "Aloo Paratha",
  "slug": "aloo-paratha",
  "status": "published",
  "about_recipe": "Aloo Paratha is a popular North Indian flatbread stuffed with a spiced potato filling…",
  "image_primary_url": "https://firebasestorage.googleapis.com/v0/b/sattva-srsti.appspot.com/o/recipe_v1_image%2Frec_aloo_paratha.jpg?alt=media&token=3dabdd3f-d114-46db-8208-ca682e5400a1",
  "cuisine": "North Indian",
  "dish_type": "Main Course",
  "difficulty": "Medium",
  "prep_time_minutes": 20,
  "cook_time_minutes": 15,
  "total_time_minutes": 35,
  "servings": 1,
  "step_count": 6,
  "spice_tolerance_level": "medium",
  "choking_risk_level": "low",
  "diet_tags": ["vegetarian", "high-fiber", "egg-free", "nut-free"],
  "search_tags": ["aloo paratha", "stuffed paratha", "Indian flatbread", "potato", "breakfast"],
  "alternative_names": ["Stuffed Potato Paratha"],
  "meal_preference_tags": ["comfort_food", "quick_meal"],
  "cooking_method_tags": ["stovetop", "pan-frying"],
  "pairing_recommendations": ["yogurt", "pickle", "butter"],
  "flavor_profile": { "salty": 6, "spicy": 5, "umami": 4, "creamy": 3, "crunchy": 2 },
  "sections_available": ["ingredients", "instructions", "identity_ingredient_ids", "recipe_nutrition"]
}
```

### `ingredients/details` (abbreviated)

```json
{
  "recipe_id": "rec_aloo_paratha",
  "base_yield": { "servings": 1, "description": "1 serving" },
  "ingredients": [
    { "ingredient_id": "ing_whole_wheat_flour", "display_name": "Whole Wheat Flour", "amount": 100, "unit": "g", "canonical_amount": 100, "canonical_unit": "g", "ingredient_role": "base", "preparation_state": "raw", "requirement_level": "required" },
    { "ingredient_id": "ing_potato", "display_name": "Potato", "amount": 150, "unit": "g", "canonical_amount": 150, "canonical_unit": "g", "ingredient_role": "base", "preparation_state": "boiled", "requirement_level": "required" },
    { "ingredient_id": "ing_ghee", "display_name": "Ghee", "amount": 1, "unit": "tbsp", "canonical_amount": 15, "canonical_unit": "g", "ingredient_role": "fat", "preparation_state": "raw", "requirement_level": "required" }
  ]
}
```

### `instructions/details` — one step example

```json
{
  "step": 5,
  "instruction_text": "Gently roll the filled dough into a flat circle, being careful not to tear it.",
  "mistake_warnings": ["Do not press too hard to avoid tearing."],
  "sensory_cues": ["even thickness"],
  "safety_notes": [],
  "ingredient_refs": ["ing_potato", "ing_whole_wheat_flour"]
}
```

### Linked ingredient `all_ingredients/ing_potato/ingredient_ayurveda/profile` (example)

```json
{
  "ingredient_name": "potato",
  "confidence": "medium",
  "ingredient_ayurveda": {
    "rasa": { "primary": "madhura", "secondary": ["kashaya"] },
    "virya": "shita",
    "vipaka": "madhura",
    "guna": ["guru", "ruksha", "manda"],
    "dosha_effect": { "vata": "aggravates", "pitta": "balances", "kapha": "aggravates" },
    "food_quality": "tamasic",
    "agni_effect": "reduces"
  }
}
```

---

## 7. Storage / media

Recipe and ingredient images live in **Firebase Storage**, not as binary in Firestore:

- Bucket pattern: `sattva-srsti.appspot.com`
- Common path: `recipe_v1_image/rec_{slug}.jpg`
- Firestore stores only the **download URL string** (`image_primary_url` / `ingredient_image_url`).

---

## 8. Blog pipeline write policy (reminder)

| Collection | Blog pipeline |
|------------|---------------|
| `recipes_v2` | **READ ONLY** |
| `all_ingredients` | **READ ONLY** |
| `blog_posts` | **WRITE** humanized content |
| `content_hashtags` | **WRITE** keyword/hashtag packs |
| Legacy `recipe` / `recipes` | Prefer not to use for new blogs |

---

## 9. Related files in this repo

| File | Role |
|------|------|
| `firestore/schemas/blog_posts.json` | Planned blog_posts schema |
| `firestore/schemas/content_hashtags.json` | Planned hashtag pack schema |
| `docs/KEYWORDS_HASHTAGS.md` | How tags become keywords/hashtags |
| `docs/PIPELINE_PLAIN_ENGLISH.md` | Blog pipeline explanation |
| `docs/BLOG_SPECIFICATION.md` | Blog content rules |

App-side constants:  
`sattva_srsti_app/lib/core/constants/firestore_constants.dart`  
`sattva_srsti_app/lib/core/constants/legacy_firestore_constants.dart`

---

*Document generated for Sattva Srsti documentation. If a live field appears in Console that is not listed, treat this as the locked app contract and note new fields as extensions.*
