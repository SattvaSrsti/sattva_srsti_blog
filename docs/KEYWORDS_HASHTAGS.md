# Keywords & hashtags (from live DB)

Built in **code** from existing fields — **not** from an extra LLM call.

## Sources in Firebase (already exist)

| Source | Fields | Use |
|--------|--------|-----|
| `recipes_v2` | `search_tags`, `alternative_names`, `diet_tags`, `meal_preference_tags`, `cooking_method_tags`, `cuisine`, `meal_type`, `mood_tags` | Keywords + hashtags |
| `all_ingredients/.../ingredient_core` | `display_name`, `search_keywords`, aliases | Ingredient hashtags / keyword extras |
| Brand (fixed) | — | Universal hashtags every post |

---

## Universal hashtags (every post / every platform)

Keep these **stable**:

- `#SattvaSrsti`
- `#SattvaSrstiRecipes`
- `#CookWithSattva`

Optional universal (use sparingly):

- `#IndianFood`
- `#HomeCooking`
- `#EasyIndianRecipes`

---

## Per-recipe hashtags (from DB)

### Rule
1. Take `search_tags` + `alternative_names`  
2. Convert to hashtags (`aloo paratha` → `#AlooParatha`)  
3. Add **2–4 identity ingredient** names (not all 20)  
4. Add **1–2** category tags from cuisine / meal / diet  
5. Cap Instagram at **5 total** (brand 1–2 + dish 2–3)

### Examples from live data

**Aloo Paratha**
- Keywords: `aloo paratha`, `stuffed paratha`, `Indian flatbread`, `potato`, `breakfast`, `Stuffed Potato Paratha`
- Hashtags: `#AlooParatha` `#StuffedParatha` `#IndianFlatbread` `#Potato` `#VegetarianBreakfast` + brand
- Ingredient extras: `#Atta` / `#Aloo` / `#Ghee` (from potato, whole wheat flour, ghee keywords)

**Mysore Masala Dosa**
- Keywords: `mysore masala dosa`, `mysuru masala dose`, `south indian dosa`, `crispy dosa`, `karnataka breakfast`, …
- Hashtags: `#MysoreMasalaDosa` `#SouthIndianDosa` `#CrispyDosa` `#KarnatakaBreakfast` + brand
- Ingredient extras (pick few): `#UradDal` `#Potato` `#DosaBatter`

**Instant Rava Dosa**
- `#InstantRavaDosa` `#RavaDosa` `#SoojiDosa` `#SemolinaDosa` `#SouthIndianBreakfast`

**Butter Chicken**
- `#ButterChicken` `#MurghMakhani` `#NorthIndianCurry` `#ChickenCurry`

**Curd Rice**
- `#CurdRice` `#ThayirSadam` `#YogurtRice` `#SouthIndianFood`

---

## Platform packing (same set, different length)

| Platform | What to send |
|----------|----------------|
| Blog footer | Full set (brand + recipe + category + 2 ingredients) |
| Instagram | Max 5: brand + top dish tags |
| YouTube tags | Keywords without `#` (from same list) |
| Pinterest | Keyword phrases (`aloo paratha recipe`) |

Interlink idea: **same `content_hashtags/{recipe_id}` doc** used by blog + IG caption + YT description.

---

## What we do NOT do

- Do not ask the LLM to invent hashtags  
- Do not put 30 diet tags as hashtags (`#ShellfishFree` spam)  
- Do not use internal IDs (`#rec_aloo_paratha`) as public tags  
