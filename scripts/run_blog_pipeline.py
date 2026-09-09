#!/usr/bin/env python3
"""
SattvaSrsti blog pipeline — one recipe end-to-end.

READ (never mutate): recipes_v2, all_ingredients
WRITE (only):        blog_posts/{blog_id}

Flow:
  1) Read recipe (+ instructions) from Firestore
  2) Eligibility gate (code)
  3) Optional slim LLM humanize (or reuse local humanized JSON)
  4) Assemble page from LLM + DB facts
  5) Write blog_posts only
  6) Refresh local preview + posts-index

Usage:
  python scripts/run_blog_pipeline.py --recipe-id rec_aloo_paratha
  python scripts/run_blog_pipeline.py --recipe-id rec_aloo_paratha --from-local-blog
  python scripts/run_blog_pipeline.py --recipe-id rec_aloo_paratha --skip-write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv()

PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "sattva-srsti")
FS_BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"
ALLOWED_WRITE_COLLECTION = "blog_posts"
APP_BASE = os.environ.get("APP_RECIPE_BASE", "https://sattvasrsti.com/recipe")
BLOG_PUBLIC_BASE = os.environ.get("BLOG_PUBLIC_BASE", "https://sattvasrsti.blog")

_FS_TOKEN_CACHE: str | None = None
_SA_PATH_CACHE: Path | None = None


def _resolve_service_account_path() -> Path | None:
    """Path to service account JSON (file or materialized from inline env JSON)."""
    global _SA_PATH_CACHE
    if _SA_PATH_CACHE and _SA_PATH_CACHE.exists():
        return _SA_PATH_CACHE
    raw = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not raw:
        return None
    p = Path(raw)
    if p.exists():
        _SA_PATH_CACHE = p
        return p
    if raw.strip().startswith("{"):
        import tempfile

        tmp = Path(tempfile.gettempdir()) / f"firebase-sa-{PROJECT_ID}.json"
        tmp.write_text(raw, encoding="utf-8")
        _SA_PATH_CACHE = tmp
        return tmp
    return None


def _firestore_bearer_token() -> str | None:
    """
    Optional auth for locked rules.
    Supports:
      FIREBASE_ID_TOKEN — Firebase Auth ID token
      GOOGLE_APPLICATION_CREDENTIALS / FIREBASE_SERVICE_ACCOUNT — service account JSON path or inline JSON
    Service accounts bypass security rules (Admin-style).
    """
    global _FS_TOKEN_CACHE
    if _FS_TOKEN_CACHE:
        return _FS_TOKEN_CACHE
    explicit = os.environ.get("FIREBASE_ID_TOKEN") or os.environ.get("FIRESTORE_BEARER_TOKEN")
    if explicit:
        _FS_TOKEN_CACHE = explicit
        return _FS_TOKEN_CACHE
    sa_path = _resolve_service_account_path()
    if sa_path:
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request

            creds = service_account.Credentials.from_service_account_file(
                str(sa_path),
                scopes=["https://www.googleapis.com/auth/datastore", "https://www.googleapis.com/auth/cloud-platform"],
            )
            creds.refresh(Request())
            _FS_TOKEN_CACHE = creds.token
            return _FS_TOKEN_CACHE
        except Exception as e:
            print(f"WARN service-account auth failed: {e}")
    return None


def _http_json(method: str, url: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = _firestore_bearer_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} for {url}: {body[:800]}") from e

# Public blog teaser only — full method stays in recipes_v2 (app; published is anonymously readable).
TEASER_INGREDIENT_RATIO = 0.7
TEASER_MAX_STEPS = 4

CUSTOMIZE_FIXED = {
    "title": "Cook the full recipe on SattvaSrsti",
    "body": (
        "When you are ready for every step, open the full recipe on SattvaSrsti — "
        "adjust ingredients, spice, and servings to match your kitchen."
    ),
    "cta_label": "Open full recipe on SattvaSrsti",
}

def _humanize_system_prompt() -> str:
    """Locked answer voice — prompts/HUMANIZE_SYSTEM.txt (same as Cloud Function)."""
    return (ROOT / "prompts" / "HUMANIZE_SYSTEM.txt").read_text(encoding="utf-8").strip()

FORBIDDEN_PHRASES = (
    "you are not alone",
    "common mistakes when making",
    "home cooks often struggle",
    "once upon a time",
    "useful answer first",
    "product second",
    "marketing through",
)
GENERIC_PRIMARY_PATTERNS = (
    "common mistakes when making",
    "not turn out right",
    "not turning out right",
    "fix common mistakes",
)
QUANTITY_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:g|kg|ml|l|tsp|tbsp|teaspoon|tablespoon|cup|cups)\b",
    re.I,
)
METHOD_VERBS = (
    "rinse", "soak", "grind", "ferment", "knead", "roll", "boil", "simmer", "fry", "roast",
)


# ---------- Firestore helpers (read any; write blog_posts only) ----------

def from_fs(value: dict) -> Any:
    if "stringValue" in value:
        return value["stringValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "nullValue" in value:
        return None
    if "timestampValue" in value:
        return value["timestampValue"]
    if "arrayValue" in value:
        return [from_fs(v) for v in value.get("arrayValue", {}).get("values", [])]
    if "mapValue" in value:
        fields = value.get("mapValue", {}).get("fields", {})
        return {k: from_fs(v) for k, v in fields.items()}
    return value


def doc_fields(doc: dict) -> dict:
    return {k: from_fs(v) for k, v in (doc.get("fields") or {}).items()}


def to_fs(value: Any) -> dict:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [to_fs(v) for v in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {k: to_fs(v) for k, v in value.items()}}}
    return {"stringValue": str(value)}


def read_doc(path: str) -> dict:
    return doc_fields(_http_json("GET", f"{FS_BASE}/{path}"))


def list_collection_docs(collection: str, *, page_size: int = 100) -> list[dict]:
    """Paginate a top-level Firestore collection. Returns [{id, fields}, ...]."""
    out: list[dict] = []
    url = f"{FS_BASE}/{collection}?pageSize={page_size}"
    while url:
        raw = _http_json("GET", url)
        for doc in raw.get("documents") or []:
            doc_id = doc["name"].rstrip("/").split("/")[-1]
            out.append({"id": doc_id, "fields": doc_fields(doc)})
        token = raw.get("nextPageToken")
        if not token:
            break
        url = f"{FS_BASE}/{collection}?pageSize={page_size}&pageToken={token}"
    return out


def run_query_status_equals(collection: str, status: str, *, page_size: int = 200) -> list[dict]:
    """Anonymous-safe list: must match rules (status == published)."""
    url = (
        f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
        "/databases/(default)/documents:runQuery"
    )
    body = {
        "structuredQuery": {
            "from": [{"collectionId": collection}],
            "where": {
                "fieldFilter": {
                    "field": {"fieldPath": "status"},
                    "op": "EQUAL",
                    "value": {"stringValue": status},
                }
            },
            "limit": page_size,
        }
    }
    rows = _http_json("POST", url, body)
    out: list[dict] = []
    if isinstance(rows, list):
        for row in rows:
            doc = row.get("document") if isinstance(row, dict) else None
            if not doc:
                continue
            doc_id = doc["name"].rstrip("/").split("/")[-1]
            out.append({"id": doc_id, "fields": doc_fields(doc)})
    return out


def list_recipe_ids() -> list[str]:
    """Only published recipes_v2 — matches anonymous app queries."""
    try:
        docs = list_collection_docs("recipes_v2")
        return [
            d["id"]
            for d in docs
            if str(d["fields"].get("status") or "").lower() == "published"
        ]
    except RuntimeError as e:
        err = str(e)
        if "403" not in err and "PERMISSION" not in err.upper():
            raise
        return [d["id"] for d in run_query_status_equals("recipes_v2", "published")]


def blog_post_quality_score(*, slug: str, primary_question: str, fields: dict) -> float:
    """Higher = prefer keeping this doc when duplicates exist for one recipe_id."""
    slug_l = (slug or "").lower()
    pq_l = (primary_question or "").lower()
    score = 0.0
    if fields.get("capability_id"):
        score += 1000
    humanized = fields.get("humanized") or {}
    if isinstance(humanized, dict) and humanized.get("related_problems"):
        score += 500
    if fields.get("research"):
        score += 200
    if "-common-mistakes" in slug_l or "common mistakes" in pq_l:
        score -= 1e6
    if "not-turn-out-right" in slug_l or "not turn out right" in pq_l:
        score -= 1e5
    return score


_BLOG_POSTS_BY_RECIPE_CACHE: dict[str, list[dict]] | None = None
_BLOG_POSTS_CACHE_SOURCE: str = ""


def list_blog_posts_by_recipe(*, ready_only: bool = False, refresh: bool = False) -> dict[str, list[dict]]:
    """Map recipe_id → list of blog post summaries from Firestore (all pages)."""
    global _BLOG_POSTS_BY_RECIPE_CACHE, _BLOG_POSTS_CACHE_SOURCE
    if _BLOG_POSTS_BY_RECIPE_CACHE is not None and not refresh:
        if ready_only:
            return {
                rid: [p for p in posts if p.get("status") in ("ready", "published")]
                for rid, posts in _BLOG_POSTS_BY_RECIPE_CACHE.items()
                if any(p.get("status") in ("ready", "published") for p in posts)
            }
        return _BLOG_POSTS_BY_RECIPE_CACHE

    by_recipe: dict[str, list[dict]] = {}
    source = "firestore"
    try:
        docs = list_collection_docs("blog_posts")
    except Exception as e:
        if _BLOG_POSTS_BY_RECIPE_CACHE is None:
            print(f"WARN list blog_posts failed ({e}); using local files only")
        by_recipe = _local_blog_posts_by_recipe(ready_only=False)
        source = "local"
        _BLOG_POSTS_BY_RECIPE_CACHE = by_recipe
        _BLOG_POSTS_CACHE_SOURCE = source
        if ready_only:
            return {
                rid: [p for p in posts if p.get("status") in ("ready", "published")]
                for rid, posts in by_recipe.items()
                if any(p.get("status") in ("ready", "published") for p in posts)
            }
        return by_recipe

    for doc in docs:
        f = doc["fields"]
        rid = f.get("recipe_id")
        if not rid:
            continue
        status = f.get("status") or ""
        if ready_only and status not in ("ready", "published"):
            continue
        slug = f.get("slug") or ""
        pq = f.get("primary_question") or ""
        entry = {
            "blog_id": f.get("blog_id") or doc["id"],
            "slug": slug,
            "status": status,
            "primary_question": pq,
            "_score": blog_post_quality_score(slug=slug, primary_question=pq, fields=f),
        }
        by_recipe.setdefault(rid, []).append(entry)
    _BLOG_POSTS_BY_RECIPE_CACHE = by_recipe
    _BLOG_POSTS_CACHE_SOURCE = source
    if ready_only:
        return {
            rid: [p for p in posts if p.get("status") in ("ready", "published")]
            for rid, posts in by_recipe.items()
            if any(p.get("status") in ("ready", "published") for p in posts)
        }
    return by_recipe


def _local_blog_posts_by_recipe(*, ready_only: bool = False) -> dict[str, list[dict]]:
    by_recipe: dict[str, list[dict]] = {}
    for p in (ROOT / "preview" / "data").glob("*.blog.json"):
        try:
            f = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        rid = f.get("recipe_id")
        if not rid:
            continue
        status = f.get("status") or ""
        if ready_only and status not in ("ready", "published"):
            continue
        slug = f.get("slug") or ""
        pq = f.get("primary_question") or ""
        by_recipe.setdefault(rid, []).append(
            {
                "blog_id": f.get("blog_id") or f.get("blog_post_id") or p.stem,
                "slug": slug,
                "status": status,
                "primary_question": pq,
                "_score": blog_post_quality_score(slug=slug, primary_question=pq, fields=f),
            }
        )
    return by_recipe


def best_blog_for_recipe(posts: list[dict]) -> dict | None:
    ready = [p for p in posts if p.get("status") in ("ready", "published")]
    pool = ready or posts
    if not pool:
        return None
    return max(pool, key=lambda p: p.get("_score", 0))


def write_blog_post_only(blog_id: str, payload: dict, *, replace: bool = True) -> str:
    """HARD RULE: only blog_posts collection may be written."""
    collection = ALLOWED_WRITE_COLLECTION
    if "/" in blog_id or blog_id.startswith("recipes_") or blog_id.startswith("all_"):
        raise ValueError(f"Unsafe blog_id: {blog_id}")
    if collection != "blog_posts":
        raise RuntimeError("Write aborted: only blog_posts is allowed")
    url = f"{FS_BASE}/{collection}/{blog_id}"
    if replace:
        # Drop stale fields when rules allow DELETE; otherwise PATCH overwrites known fields.
        try:
            _http_json("DELETE", url)
        except RuntimeError as e:
            if "HTTP 404" not in str(e) and "HTTP 403" not in str(e):
                raise
    body = {"fields": {k: to_fs(v) for k, v in payload.items()}}
    _http_json("PATCH", url, body)
    return f"{collection}/{blog_id}"


def delete_blog_post_admin(blog_id: str) -> bool:
    """Delete via Firebase Admin SDK (bypasses security rules). Requires service account."""
    sa_path = _resolve_service_account_path()
    if not sa_path:
        raise RuntimeError(
            "Service account required to delete blog_posts under locked rules "
            "(set GOOGLE_APPLICATION_CREDENTIALS or FIREBASE_SERVICE_ACCOUNT)"
        )
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(sa_path))
        firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
    ref = firestore.client().collection(ALLOWED_WRITE_COLLECTION).document(blog_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True


def delete_blog_post_only(blog_id: str) -> bool:
    """Delete a superseded blog_posts doc (same collection guard as write)."""
    if "/" in blog_id or blog_id.startswith("recipes_") or blog_id.startswith("all_"):
        raise ValueError(f"Unsafe blog_id: {blog_id}")
    url = f"{FS_BASE}/{ALLOWED_WRITE_COLLECTION}/{blog_id}"
    try:
        _http_json("DELETE", url)
        return True
    except RuntimeError as e:
        if "HTTP 404" in str(e):
            return False
        if "HTTP 403" in str(e):
            return delete_blog_post_admin(blog_id)
        raise


def cleanup_superseded_blog(recipe_id: str, new_blog_id: str, new_slug: str) -> None:
    """Remove old local + Firestore blog when slug/blog_id changes on regenerate."""
    data_dir = ROOT / "preview" / "data"
    for p in data_dir.glob("*.blog.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if j.get("recipe_id") != recipe_id:
            continue
        old_id = j.get("blog_id") or j.get("blog_post_id")
        old_slug = j.get("slug")
        if old_id == new_blog_id and old_slug == new_slug:
            continue
        if old_id and old_id != new_blog_id:
            try:
                delete_blog_post_only(old_id)
                print(f"    deleted superseded Firestore doc {old_id}")
            except Exception as e:
                print(f"    WARN could not delete {old_id}: {e}")
        if old_slug and old_slug != new_slug and p.name == f"{old_slug}.blog.json":
            try:
                p.unlink()
                print(f"    removed local {p.name}")
            except Exception as e:
                print(f"    WARN could not remove {p.name}: {e}")


def community_questions_from(research: dict | None, humanized: dict | None) -> list[dict]:
    research = research or {}
    humanized = humanized or {}
    items = research.get("questions") or (
        [research.get("primary_question") or {}] + list(research.get("related_questions") or [])
    )
    related = humanized.get("related_problems") or []
    useful = humanized.get("useful_answer") or ""
    if isinstance(useful, dict):
        useful = useful.get("text") or useful.get("answer") or ""
    out = []
    for i, item in enumerate(items[:6]):
        q = item.get("question")
        if not q:
            continue
        if i == 0:
            ans = useful
        else:
            prev = related[i - 1] if i - 1 < len(related) else {}
            ans = (prev or {}).get("a") or (prev or {}).get("answer") or ""
        out.append(
            {
                "question": q,
                "source": item.get("source") or "",
                "url": item.get("source_url") or "",
                "answer": str(ans or ""),
            }
        )
    return out


def firestore_doc_from_page(page: dict) -> dict:
    """
    Blog-unique editorial fields plus a capped public `display` teaser.
    Full ingredients, method, Ayurveda, and nutrition stay in recipes_v2
    (app only). The public website must not read recipes_v2.
    """
    H = page.get("humanized") or {}
    blog_id = page.get("blog_post_id") or page.get("blog_id")
    seo = page.get("seo") or {}
    useful = H.get("useful_answer")
    if isinstance(useful, dict):
        useful = useful.get("text") or useful.get("answer") or useful.get("useful_answer") or ""
    story = H.get("story")
    if isinstance(story, list):
        story = " ".join(str(s) for s in story if s)
    related = H.get("related_problems") or H.get("common_questions") or []
    # Normalize related to {q,a}
    norm_related = []
    for item in related:
        if not isinstance(item, dict):
            continue
        q = item.get("q") or item.get("question")
        a = item.get("a") or item.get("answer")
        if q and a:
            norm_related.append({"q": q, "a": a})
    doc = {
        "blog_id": blog_id,
        "recipe_id": page["recipe_id"],
        "slug": page["slug"],
        "status": page.get("status", "ready"),
        "primary_question": H.get("primary_question") or page.get("primary_question"),
        "seo_title": page.get("seo_title") or seo.get("title"),
        "meta_description": (
            page.get("meta_description")
            or H.get("meta_description")
            or seo.get("meta_description")
        ),
        "blog_public_url": page.get("blog_public_url") or seo.get("canonical_url"),
        "capability_id": page.get("capability_id") or "guided_recipe_customization",
        "humanized": {
            "hook": H.get("hook"),
            "story": story or "",
            "useful_answer": useful,
            "related_problems": norm_related,
            "emotional_ending": H.get("emotional_ending"),
        },
        "customize_fixed": page.get("customize_fixed") or CUSTOMIZE_FIXED,
        "research": page.get("research") or [],
        "community_questions": page.get("community_questions") or [],
    }
    return attach_display_teaser(doc)


def slugify(text: str) -> str:
    out = []
    for ch in text.lower().strip():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_/" and (not out or out[-1] != "-"):
            out.append("-")
    return "".join(out).strip("-") or "recipe"


def fetch_recipe_bundle(recipe_id: str) -> dict:
    root = read_doc(f"recipes_v2/{recipe_id}")
    instructions = {}
    try:
        instructions = read_doc(f"recipes_v2/{recipe_id}/instructions/details")
    except Exception:
        instructions = {}
    ingredients = []
    try:
        # Prefer nested ingredients list on root if present; else ingredients/details
        if isinstance(root.get("ingredients"), list):
            ingredients = root["ingredients"]
        else:
            ing_doc = read_doc(f"recipes_v2/{recipe_id}/ingredients/details")
            ingredients = ing_doc.get("items") or ing_doc.get("ingredients") or []
    except Exception:
        ingredients = root.get("ingredients") or []
    return {"recipe_id": recipe_id, "root": root, "instructions": instructions, "ingredients": ingredients}


_ROLE_LABELS = {
    "base": "Base",
    "protein": "Protein",
    "spice": "Spices",
    "aromatic": "Aromatics",
    "fat": "Fats & oils",
    "liquid": "Liquids",
    "acid": "Acids",
    "garnish": "Garnish",
}
_ROLE_ORDER = ["base", "protein", "spice", "aromatic", "fat", "liquid", "acid", "garnish"]


def _role_label(role: str) -> str:
    key = str(role or "").lower()
    if key in _ROLE_LABELS:
        return _ROLE_LABELS[key]
    if not key:
        return "Other"
    return key[0].upper() + key[1:]


def _group_ingredients(ings: list) -> list[dict]:
    groups: dict[str, list] = {}
    for it in ings or []:
        if not isinstance(it, dict):
            continue
        name = it.get("display_name") or it.get("name") or "Ingredient"
        notes = []
        prep = it.get("preparation_state")
        if prep and prep != "raw":
            notes.append(str(prep))
        if str(it.get("requirement_level") or "").lower() == "optional":
            notes.append("optional")
        row = {
            "amount": it.get("amount"),
            "unit": it.get("unit") or "",
            "canonical_amount": it.get("canonical_amount"),
            "canonical_unit": it.get("canonical_unit") or "",
            "name": name,
            "note": ", ".join(notes) if notes else "",
        }
        role_key = str(it.get("ingredient_role") or "other").lower()
        groups.setdefault(role_key, []).append(row)
    ordered = [k for k in _ROLE_ORDER if groups.get(k)]
    ordered += [k for k in groups if k not in _ROLE_ORDER]
    return [{"name": _role_label(k), "items": groups[k]} for k in ordered]


def _preview_step_label(text: str, i: int) -> str:
    low = (text or "").lower()
    if low.startswith("rinse") or low.startswith("soak"):
        return "Prep"
    if low.startswith("boil"):
        return "Boil"
    if "grind" in low:
        return "Grind"
    if "mash" in low or "filling" in low:
        return "Fill"
    if "dough" in low or "knead" in low:
        return "Dough"
    if "roll" in low:
        return "Roll"
    if "cook" in low or "pan" in low or "tawa" in low:
        return "Cook"
    return f"Step {i + 1}"


def display_teaser_from_bundle(
    bundle: dict,
    *,
    ingredient_ratio: float = TEASER_INGREDIENT_RATIO,
    max_steps: int = TEASER_MAX_STEPS,
) -> dict:
    """Capped public teaser copied onto blog_posts. Not the full recipe."""
    import math

    root = bundle.get("root") or {}
    ings = bundle.get("ingredients") or []
    inst = bundle.get("instructions") or {}
    steps = inst.get("steps") or []
    storage = inst.get("leftover_storage") or {}
    groups = _group_ingredients(ings)
    total = sum(len(g.get("items") or []) for g in groups)
    max_show = max(1, math.ceil(total * ingredient_ratio)) if total else 0
    shown = 0
    capped = []
    for g in groups:
        if shown >= max_show:
            break
        items = []
        for item in g.get("items") or []:
            if shown >= max_show:
                break
            items.append(item)
            shown += 1
        if items:
            capped.append({"name": g["name"], "items": items})
    preview_steps = []
    for i, s in enumerate((steps or [])[:max_steps]):
        if not isinstance(s, dict):
            continue
        text = s.get("instruction_text") or s.get("text") or ""
        preview_steps.append({"label": _preview_step_label(text, i), "text": text})
    diet = root.get("diet_tags") or []
    if not isinstance(diet, list):
        diet = []
    pairings = root.get("pairing_recommendations") or []
    if not isinstance(pairings, list):
        pairings = []
    pairings = [str(p).replace("_", " ") for p in pairings]
    tags = root.get("search_tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags[:3]]
    yield_info = root.get("base_yield") or {}
    servings = 1
    if isinstance(yield_info, dict):
        servings = yield_info.get("servings") or 1
    total_time = root.get("total_time_minutes") or (
        (root.get("prep_time_minutes") or 0) + (root.get("cook_time_minutes") or 0) or None
    )
    title = root.get("title") or "Recipe"
    slug = root.get("slug") or str(title).lower().replace(" ", "-")
    return {
        "recipe_title": title,
        "recipe_slug": slug,
        "image_url": root.get("image_primary_url") or "",
        "cuisine": root.get("cuisine") or "",
        "meal_type": root.get("meal_type") or "",
        "diet_tags": [str(d) for d in diet],
        "total_time_minutes": total_time or 0,
        "difficulty": root.get("difficulty") or "",
        "spice_tolerance_level": root.get("spice_tolerance_level") or "",
        "servings": servings,
        "about_recipe": root.get("about_recipe") or "",
        "pairing_recommendations": pairings,
        "search_tags": tags,
        "ingredient_groups": capped,
        "ingredient_hidden": max(0, total - shown),
        "steps": preview_steps,
        "step_hidden": max(0, len(steps) - max_steps),
        "storage": {
            "refrigeration": storage.get("refrigeration") or storage.get("fridge") or "",
            "reheat": storage.get("reheat") or "",
            "shelf_life": storage.get("shelf_life") or storage.get("duration") or "",
        },
    }


def attach_display_teaser(doc: dict, bundle: dict | None = None) -> dict:
    """Attach capped `display` onto a blog_posts payload. Never writes recipes_v2."""
    rid = doc.get("recipe_id")
    if not rid:
        return doc
    try:
        b = bundle or fetch_recipe_bundle(str(rid))
        teaser = display_teaser_from_bundle(b)
    except Exception as e:
        print(f"  warn: display teaser skipped for {rid}: {e}")
        return doc
    doc["recipe_title"] = teaser["recipe_title"]
    doc["image_url"] = teaser["image_url"]
    doc["cuisine"] = teaser["cuisine"]
    doc["meal_type"] = teaser["meal_type"]
    doc["display"] = teaser
    return doc


def eligibility(bundle: dict) -> tuple[bool, str]:
    root = bundle["root"]
    ings = bundle["ingredients"]
    if not root.get("title"):
        return False, "missing_title"
    if not root.get("image_primary_url"):
        return False, "missing_image"
    if not ings:
        return False, "missing_ingredients"
    return True, "ok"


def find_existing_blog_for_recipe(recipe_id: str) -> dict | None:
    """Return best ready/published blog_posts doc for recipe_id (local + Firestore)."""
    best_local = None
    best_local_score = -1e18
    for p in (ROOT / "preview" / "data").glob("*.blog.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if j.get("recipe_id") != recipe_id:
            continue
        if j.get("status") not in ("ready", "published"):
            continue
        sc = blog_post_quality_score(
            slug=j.get("slug") or "",
            primary_question=j.get("primary_question") or "",
            fields=j,
        )
        if sc > best_local_score:
            best_local_score = sc
            best_local = {
                "blog_id": j.get("blog_id") or j.get("blog_post_id"),
                "slug": j.get("slug"),
                "status": j.get("status"),
                "source": "local",
                "_score": sc,
            }
    try:
        fs_posts = list_blog_posts_by_recipe().get(recipe_id) or []
        best_fs = best_blog_for_recipe(fs_posts)
        if best_fs:
            best_fs = {**best_fs, "source": "firestore"}
            if best_local and best_local.get("_score", 0) >= best_fs.get("_score", 0):
                return {k: v for k, v in best_local.items() if not k.startswith("_")}
            return {k: v for k, v in best_fs.items() if not k.startswith("_")}
    except Exception:
        pass
    if best_local:
        return {k: v for k, v in best_local.items() if not k.startswith("_")}
    return None


def load_capabilities() -> dict:
    path = ROOT / "prompts" / "capabilities.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "default_id": "guided_recipe_customization",
        "capabilities": [
            {"id": "guided_recipe_customization", "label": "Guided recipe customization", "enabled": True}
        ],
    }


def select_capability(research: dict, root: dict) -> dict:
    """Code-selected capability. LLM must not invent capabilities."""
    caps = load_capabilities()
    default_id = caps.get("default_id") or "guided_recipe_customization"
    enabled = {
        c["id"]: c
        for c in (caps.get("capabilities") or [])
        if c.get("enabled", True) or c["id"] == default_id
    }
    blob = " ".join(
        [
            (research.get("primary_question") or {}).get("question") or "",
            *[
                (q.get("question") or "")
                for q in (research.get("related_questions") or [])
            ],
        ]
    ).lower()
    chosen = default_id
    if "substitut" in blob and "ingredient_substitution" in enabled and enabled["ingredient_substitution"].get("enabled", False):
        chosen = "ingredient_substitution"
    elif any(w in blob for w in ("too spicy", "less spicy", "spice level")) and enabled.get("spice_customization", {}).get("enabled"):
        chosen = "spice_customization"
    elif any(w in blob for w in ("servings", "for 4", "for guests", "scale")) and enabled.get("serving_scaling", {}).get("enabled"):
        chosen = "serving_scaling"
    cap = enabled.get(chosen) or enabled.get(default_id) or {
        "id": default_id,
        "label": "Guided recipe customization",
    }
    return {"id": cap["id"], "label": cap.get("label") or cap["id"]}


def load_research_pack(recipe_id: str, *, refresh: bool = False, from_research: Path | None = None, from_seed: bool = False) -> dict:
    if from_research and from_research.exists():
        return json.loads(from_research.read_text(encoding="utf-8"))
    sys.path.insert(0, str(ROOT / "scripts"))
    from research_recipe_questions import research_recipe  # noqa: WPS433

    return research_recipe(recipe_id, from_seed=from_seed, refresh=refresh)


def slim_intent(item: dict) -> dict:
    """Strip URLs before sending to OpenAI."""
    return {
        "question": item.get("question"),
        "source": item.get("source"),
        "evidence_type": item.get("evidence_type"),
        "evidence": (item.get("evidence") or [])[:5],
    }


def build_research_context(research: dict, capability: dict) -> dict:
    """Slim context only — no recipe dump."""
    recipe = research.get("recipe") or {}
    primary = research.get("primary_question") or {}
    related = research.get("related_questions") or []
    return {
        "recipe": {
            "title": recipe.get("title"),
            "cuisine": recipe.get("cuisine"),
        },
        "primary_question": slim_intent(primary),
        "related_questions": [slim_intent(q) for q in related[:5]],
        "capability": {
            "id": capability.get("id"),
            "label": capability.get("label"),
        },
    }


def normalize_humanized(h: dict, research: dict) -> dict:
    """Normalize story/related_problems shapes; build page FAQ later as primary + 4."""
    out = dict(h)
    story = out.get("story")
    if isinstance(story, list):
        out["story"] = " ".join(str(s).strip() for s in story if s)
    related = out.get("related_problems") or out.get("common_questions") or []
    norm = []
    for item in related:
        if not isinstance(item, dict):
            continue
        q = item.get("q") or item.get("question")
        a = item.get("a") or item.get("answer")
        if q and a:
            norm.append({"q": str(q).strip(), "a": str(a).strip()})
    # If model returned 5 including primary, drop primary match
    pq = (research.get("primary_question") or {}).get("question") or out.get("primary_question") or ""
    pq_key = re.sub(r"[^a-z0-9\s]", "", pq.lower())
    filtered = [x for x in norm if re.sub(r"[^a-z0-9\s]", "", x["q"].lower()) != pq_key]
    research_related = research.get("related_questions") or []
    locked = []
    used = set()
    for i, rq in enumerate(research_related):
        q = str(rq.get("question") or "").strip()
        a = ""
        rq_key = re.sub(r"[^a-z0-9\s]", "", q.lower())
        for j, item in enumerate(filtered):
            if j in used:
                continue
            if re.sub(r"[^a-z0-9\s]", "", item["q"].lower()) == rq_key:
                a = item["a"]
                used.add(j)
                break
        if not a:
            for j, item in enumerate(filtered):
                if j in used:
                    continue
                a = item["a"]
                used.add(j)
                break
        if q and a:
            locked.append({"q": q, "a": a})
    want = len(research_related)
    if locked:
        out["related_problems"] = locked[:want] if want else locked
    elif filtered:
        out["related_problems"] = filtered[: max(want, 2)]
    else:
        out["related_problems"] = norm[: max(want, 2)]
    if pq:
        out["primary_question"] = pq
    out.pop("common_questions", None)
    return out


def validate_research_provenance(research: dict) -> list[str]:
    errs = []
    items = research.get("questions") or (
        [research.get("primary_question") or {}] + list(research.get("related_questions") or [])
    )
    items = [x for x in items if x and x.get("question")]
    if not (3 <= len(items) <= 6):
        errs.append("community_count")
    for item in items:
        src = item.get("source")
        url = item.get("source_url")
        if src in ("quora", "reddit", "food_site") and not url:
            errs.append(f"missing_url_{src}")
        if src == "generated_intent" and url is not None:
            errs.append("generated_must_null_url")
        if not (item.get("evidence") or []):
            errs.append("empty_evidence")
        if not item.get("question"):
            errs.append("empty_question")
    # primary not in related
    pq = ((research.get("primary_question") or {}).get("question") or "").lower().strip()
    for r in research.get("related_questions") or []:
        if (r.get("question") or "").lower().strip() == pq:
            errs.append("primary_duplicated_in_related")
    return errs


def validate_humanized(h: dict, *, research: dict | None = None) -> list[str]:
    errs = []
    for k in ("primary_question", "hook", "useful_answer", "emotional_ending", "meta_description"):
        if not h.get(k):
            errs.append(f"missing_{k}")
    story = h.get("story")
    if isinstance(story, list):
        if not (2 <= len(story) <= 4):
            errs.append("story_len")
    elif not isinstance(story, str) or len(story.strip()) < 20:
        errs.append("story_len")

    qs = h.get("related_problems") or h.get("common_questions") or []
    want = len((research or {}).get("related_questions") or [])
    if not isinstance(qs, list):
        errs.append("related_problems_count")
    elif want and len(qs) != want:
        errs.append("related_problems_count")
    elif not want and not (2 <= len(qs) <= 5):
        errs.append("related_problems_count")
    if isinstance(qs, list) and any(
        not isinstance(x, dict) or not (x.get("q") or x.get("question")) or not (x.get("a") or x.get("answer"))
        for x in qs
    ):
        errs.append("related_problems_shape")

    pq = str(h.get("primary_question") or "")
    for pat in GENERIC_PRIMARY_PATTERNS:
        if pat in pq.lower():
            errs.append("generic_primary_question")
            break
    if research:
        expected = ((research.get("primary_question") or {}).get("question") or "").strip()
        if expected and expected.lower() != pq.strip().lower():
            errs.append("primary_not_preserved")

    blob = " ".join(
        [
            str(h.get("hook") or ""),
            str(h.get("story") if not isinstance(h.get("story"), list) else " ".join(h.get("story") or [])),
            str(h.get("useful_answer") or ""),
            str(h.get("emotional_ending") or ""),
            *[str((x.get("a") or x.get("answer") or "")) for x in qs if isinstance(x, dict)],
        ]
    ).lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in blob:
            errs.append(f"forbidden:{phrase}")
            break
    if QUANTITY_RE.search(blob):
        errs.append("quantity_leak")
    verb_hits = sum(1 for v in METHOD_VERBS if re.search(rf"\b{v}\b", blob))
    if verb_hits >= 6:
        errs.append("method_dump")
    meta = str(h.get("meta_description") or "")
    if len(meta) > 155:
        errs.append("meta_too_long")

    # Distinct related questions
    if isinstance(qs, list) and qs:
        keys = []
        for x in qs:
            q = (x.get("q") or x.get("question") or "").lower().strip()
            keys.append(q)
        if len(set(keys)) < len(keys):
            errs.append("related_not_distinct")
        if pq.lower().strip() in keys:
            errs.append("primary_in_related_problems")
        for x in qs:
            a = str((x.get("a") or x.get("answer") or "")).strip()
            if len(a) < 60:
                errs.append("related_answer_too_short")
                break
    return errs


def primary_question_for(title: str, warnings: list[str]) -> str:
    """Legacy helper — avoid 'common mistakes' wording."""
    t = title.lower()
    blob = " ".join(warnings).lower()
    if "paratha" in t and ("tear" in blob or "press" in blob or "sticky" in blob):
        return f"Why does my {title.lower()} keep tearing?"
    if "dosa" in t:
        return f"Why is my {title.lower()} not crispy?"
    return f"How do I make better {title} at home?"


def build_llm_context(bundle: dict) -> dict:
    """Deprecated — use build_research_context. Kept for import compatibility."""
    raise RuntimeError("build_llm_context is deprecated; use research + build_research_context")


def openai_call(ctx: dict) -> tuple[dict, dict]:
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _humanize_system_prompt()},
            {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    usage = raw.get("usage") or {}
    humanized = json.loads(raw["choices"][0]["message"]["content"])
    report = {
        "ok": True,
        "model": body["model"],
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "calls": 1,
        "retry_count": 0,
        "validation_result": "pending",
        "purpose": "research_humanization_v2",
    }
    return humanized, report


def group_ingredients(ings: list[dict]) -> list[dict]:
    groups: dict[str, list] = {"Dough": [], "Filling": [], "Cooking": [], "Other": []}
    for it in ings:
        role = (it.get("ingredient_role") or "").lower()
        name = it.get("display_name") or it.get("name") or "Ingredient"
        low = name.lower()
        note_parts = []
        if it.get("preparation_state") and it["preparation_state"] not in ("raw", None, ""):
            note_parts.append(str(it["preparation_state"]))
        if (it.get("requirement_level") or "").lower() == "optional":
            note_parts.append("optional")
        item = {
            "amount": it.get("amount"),
            "unit": it.get("unit"),
            "name": name,
            "note": ", ".join(note_parts) if note_parts else None,
            "canonical_amount": it.get("canonical_amount"),
            "canonical_unit": it.get("canonical_unit"),
            "ingredient_id": it.get("ingredient_id"),
        }
        if "flour" in low:
            groups["Dough"].append(item)
        elif role in ("fat", "oil") or "ghee" in low or low.endswith(" oil"):
            groups["Cooking"].append(item)
        elif role in ("base", "aromatic", "spice", "herb", "seasoning", "") or role:
            groups["Filling"].append(item)
        else:
            groups["Other"].append(item)
    out = []
    for gname, items in groups.items():
        if not items:
            continue
        seen, uniq = set(), []
        for x in items:
            key = x.get("ingredient_id") or x["name"]
            if key in seen:
                continue
            seen.add(key)
            uniq.append(x)
        out.append({"name": gname, "items": uniq})
    return out


def preview_steps_from_instructions(instructions: dict, n: int = 3) -> list[dict]:
    steps = instructions.get("steps") or []
    out = []
    for i, s in enumerate(steps[:n], start=1):
        text = s.get("instruction_text") or s.get("text") or ""
        label = (text.split(".")[0][:28] if text else f"Step {i}")
        # nicer short labels
        low = text.lower()
        if low.startswith("boil"):
            label = "Boil"
        elif "mash" in low or "filling" in low:
            label = "Fill"
        elif "dough" in low or "knead" in low:
            label = "Dough"
        elif "roll" in low:
            label = "Roll"
        elif "cook" in low or "pan" in low:
            label = "Cook"
        out.append(
            {
                "n": i,
                "label": label,
                "text": text,
                "mistake_warnings": s.get("mistake_warnings") or [],
                "sensory_cues": s.get("sensory_cues") or [],
            }
        )
    return out


def hashtags_from_recipe(root: dict, title: str) -> dict:
    tags = ["#SattvaSrsti", "#SattvaSrstiRecipes", "#CookWithSattva"]
    clean = "".join(ch for ch in title.title() if ch.isalnum() or ch == " ")
    tags.append("#" + clean.replace(" ", ""))
    for t in (root.get("search_tags") or [])[:3]:
        piece = "".join(ch for ch in str(t).title() if ch.isalnum() or ch == " ")
        if piece:
            tags.append("#" + piece.replace(" ", ""))
    # unique preserve order
    seen, display = set(), []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            display.append(t)
    return {"display": display, "instagram_subset": display[:5]}


def assemble_blog(bundle: dict, humanized: dict, api_report: dict | None) -> dict:
    root = bundle["root"]
    recipe_id = bundle["recipe_id"]
    title = root.get("title") or "Recipe"
    slug_recipe = root.get("slug") or slugify(title)
    pq = humanized.get("primary_question") or primary_question_for(title, [])
    post_slug = slugify(pq.replace("?", ""))
    blog_id = f"blog_{post_slug}"
    cuisine = root.get("cuisine") or "Indian"
    meal = root.get("meal_type") or ""
    diet = root.get("diet_tags") or []
    veg = "Vegetarian" if any("vegetarian" in str(d).lower() for d in diet) else ""
    servings = (root.get("base_yield") or {}).get("servings") or 1
    total = root.get("total_time_minutes") or (
        (root.get("prep_time_minutes") or 0) + (root.get("cook_time_minutes") or 0)
    )
    storage = (bundle["instructions"] or {}).get("leftover_storage") or {}
    pairings = root.get("pairing_recommendations") or []

    page = {
        "blog_post_id": blog_id,
        "recipe_id": recipe_id,
        "slug": post_slug,
        "status": "ready",
        "blog_public_url": f"{BLOG_PUBLIC_BASE.rstrip('/')}/{post_slug}",
        "purpose": "marketing_acquisition",
        "seo": {
            "title": f"{pq} | SattvaSrsti",
            "meta_description": humanized.get("meta_description") or pq,
            "canonical_url": f"{BLOG_PUBLIC_BASE.rstrip('/')}/{post_slug}",
            "og_type": "article",
            "robots": "index,follow",
        },
        "breadcrumbs": [
            {"name": "Home", "path": "/"},
            {"name": "Blog", "path": "/blog"},
            {"name": cuisine, "path": f"/blog/cuisine/{slugify(cuisine)}"},
            {"name": title, "path": f"/blog/{post_slug}"},
        ],
        "hero": {
            "eyebrow": " · ".join(x for x in [cuisine, meal, veg] if x),
            "title": pq,
            "hook": humanized.get("hook"),
            "image_url": root.get("image_primary_url"),
            "image_alt": f"{title} from SattvaSrsti recipe photo",
            "meta_pills": [
                f"{total} min" if total else None,
                root.get("difficulty"),
                f"Spice: {root.get('spice_tolerance_level')}" if root.get("spice_tolerance_level") else None,
                f"{servings} serving" if servings else None,
            ],
        },
        "humanized": {
            "primary_question": pq,
            "hook": humanized.get("hook"),
            "story": humanized.get("story"),
            "useful_answer": humanized.get("useful_answer"),
            "related_problems": humanized.get("related_problems") or [],
            "emotional_ending": humanized.get("emotional_ending"),
            "meta_description": humanized.get("meta_description"),
        },
        "about_recipe": {"text": root.get("about_recipe") or f"{title} from SattvaSrsti."},
        "ingredient_groups": group_ingredients(bundle["ingredients"]),
        "preview_steps": preview_steps_from_instructions(bundle["instructions"], 3),
        "preview_lock_note": "The remaining steps are in the full SattvaSrsti recipe when you are ready to cook through.",
        "related_problems": humanized.get("related_problems") or [],
        "customize_fixed": CUSTOMIZE_FIXED,
        "capability_id": humanized.get("capability_id") or bundle.get("capability_id") or "guided_recipe_customization",
        "research": bundle.get("research_provenance") or [],
        "pairings": {
            "title": "What goes well with it",
            "items": [str(x).replace("_", " ").title() if isinstance(x, str) else x for x in pairings],
        },
        "storage": {
            "title": "Storage",
            "refrigeration": storage.get("refrigeration") or storage.get("fridge") or "Store in an airtight container in the fridge.",
            "reheat": storage.get("reheat") or "Reheat on a pan or microwave until warm.",
            "shelf_life": storage.get("shelf_life") or storage.get("duration") or "Consume within 2 days.",
        },
        "cta": {
            "app_base": APP_BASE,
            "recipe_slug": slug_recipe,
            "utm_campaign": post_slug,
            "slots": {
                "hero": {"label": "Cook & customize on SattvaSrsti", "content": "hero"},
                "preview": {"label": "Continue in SattvaSrsti", "content": "preview-lock"},
                "final": {"label": "Open full recipe & customize", "content": "final"},
            },
        },
        "hashtags": hashtags_from_recipe(root, title),
        "social": {
            "mode": "share_buttons",
            "note": "Share this post URL. Tags are only a caption helper.",
            "instagram_url": None,
            "facebook_url": None,
            "youtube_url": None,
        },
        "api_report": api_report,
    }
    # clean null pills
    page["hero"]["meta_pills"] = [p for p in page["hero"]["meta_pills"] if p]
    return page


def update_posts_index(page: dict) -> None:
    path = ROOT / "preview" / "data" / "posts-index.json"
    if path.exists():
        idx = json.loads(path.read_text(encoding="utf-8"))
    else:
        idx = {"site": {"brand": "SattvaSrsti"}, "posts": []}
    entry = {
        "slug": page["slug"],
        "title": page["hero"]["title"],
        "hook": page["hero"]["hook"],
        "cuisine": (page["hero"].get("eyebrow") or "").split("·")[0].strip(),
        "meal": "",
        "image_url": page["hero"]["image_url"],
        "data_file": f"./data/{page['slug']}.blog.json",
        "recipe_id": page["recipe_id"],
        "status": page.get("status", "ready"),
    }
    # parse meal from eyebrow if present
    parts = [p.strip() for p in (page["hero"].get("eyebrow") or "").split("·")]
    if len(parts) > 1:
        entry["meal"] = parts[1]
    posts = [
        p
        for p in idx.get("posts", [])
        if p.get("slug") != page["slug"] and p.get("recipe_id") != page["recipe_id"]
    ]
    posts.insert(0, entry)
    idx["posts"] = posts
    path.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_local(page: dict, ctx: dict | None, humanized: dict | None, report: dict | None) -> Path:
    data_dir = ROOT / "preview" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    slim = firestore_doc_from_page(page)
    out = data_dir / f"{slim['slug']}.blog.json"
    out.write_text(json.dumps(slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if slim["recipe_id"] == "rec_aloo_paratha":
        (data_dir / "aloo-paratha.blog.json").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    if ctx:
        (data_dir / f"{slim['slug']}.llm-context.json").write_text(
            json.dumps(ctx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if humanized:
        (data_dir / f"{slim['slug']}.humanized.json").write_text(
            json.dumps(humanized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if report:
        (data_dir / f"{slim['slug']}.api-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    sample = ROOT / "firestore" / "samples" / f"{slim['blog_id']}.json"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text(json.dumps(slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # posts index needs a display image — read from recipe root if assembling full page
    index_page = {
        **slim,
        "hero": page.get("hero") or {
            "title": slim["primary_question"],
            "hook": slim["humanized"].get("hook"),
            "image_url": (page.get("hero") or {}).get("image_url"),
            "eyebrow": (page.get("hero") or {}).get("eyebrow") or "",
        },
    }
    update_posts_index(index_page if page.get("hero") else {
        "slug": slim["slug"],
        "recipe_id": slim["recipe_id"],
        "blog_post_id": slim["blog_id"],
        "status": slim["status"],
        "hero": {
            "title": slim["primary_question"],
            "hook": slim["humanized"].get("hook"),
            "image_url": "",
            "eyebrow": "",
        },
        "humanized": slim["humanized"],
    })
    return out


def load_local_blog_for_recipe(recipe_id: str) -> dict | None:
    # Prefer known aloo file
    candidates = list((ROOT / "preview" / "data").glob("*.blog.json"))
    for p in candidates:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            if j.get("recipe_id") == recipe_id:
                return j
        except Exception:
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe-id", required=True)
    ap.add_argument("--from-local-blog", action="store_true", help="Use existing assembled blog JSON (skip LLM)")
    ap.add_argument("--from-research", type=str, default="", help="Path to research JSON")
    ap.add_argument("--refresh-research", action="store_true")
    ap.add_argument("--from-seed", action="store_true", help="Research from curated seed only")
    ap.add_argument("--force", action="store_true", help="Allow overwrite when blog already ready for recipe")
    ap.add_argument("--skip-write", action="store_true", help="Do not write Firestore")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print(f"[1] READ recipes_v2/{args.recipe_id} (read-only)")
    bundle = fetch_recipe_bundle(args.recipe_id)
    ok, reason = eligibility(bundle)
    if not ok:
        print(f"SKIP eligibility: {reason}")
        return 3
    print(f"    title={bundle['root'].get('title')} eligibility=ok")

    existing = find_existing_blog_for_recipe(args.recipe_id)
    if existing and not args.force and not args.from_local_blog:
        print(f"SKIP duplicate: recipe already has blog {existing}")
        print("    use --force to regenerate")
        return 2

    page = None
    ctx = None
    humanized = None
    report = None
    research = None

    if args.from_local_blog:
        print("[2] Reuse local blog JSON (skip LLM)")
        page = load_local_blog_for_recipe(args.recipe_id)
        if not page:
            print("No local blog JSON found for recipe")
            return 4
        if page.get("blog_id") and not page.get("blog_post_id"):
            page["blog_post_id"] = page["blog_id"]
        humanized = page.get("humanized")
        report = None
    else:
        print("[2] Research intents (connectors + compress-only evidence)")
        research_path = Path(args.from_research) if args.from_research else None
        research = load_research_pack(
            args.recipe_id,
            refresh=args.refresh_research,
            from_research=research_path,
            from_seed=args.from_seed,
        )
        prov_errs = validate_research_provenance(research)
        if prov_errs:
            print(f"SKIP research provenance: {prov_errs}")
            return 6
        capability = select_capability(research, bundle["root"])
        print(f"    primary={research['primary_question']['question']}")
        print(f"    related={len(research['related_questions'])} capability={capability['id']}")

        ctx = build_research_context(research, capability)
        slug_hint = research.get("slug") or slugify(bundle["root"].get("title") or "recipe")
        ctx_path = ROOT / "preview" / "data" / f"{slug_hint}.llm-context.json"
        ctx_path.write_text(json.dumps(ctx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"    slim context saved {ctx_path}")

        print("[3] OpenAI humanize (1 call, at most 1 retry)")
        humanized, report = openai_call(ctx)
        humanized = normalize_humanized(humanized, research)
        errs = validate_humanized(humanized, research=research)
        report["validation_result"] = "pass" if not errs else f"fail:{errs}"
        report["retry_count"] = 0
        if errs:
            print(f"    validate fail: {errs} — retry once")
            first_in = report.get("input_tokens") or 0
            first_out = report.get("output_tokens") or 0
            first_tot = report.get("total_tokens") or 0
            humanized2, report2 = openai_call({**ctx, "validator_errors": errs})
            humanized2 = normalize_humanized(humanized2, research)
            errs2 = validate_humanized(humanized2, research=research)
            report = report2
            report["retry_count"] = 1
            report["calls"] = 2
            report["input_tokens"] = first_in + (report2.get("input_tokens") or 0)
            report["output_tokens"] = first_out + (report2.get("output_tokens") or 0)
            report["total_tokens"] = first_tot + (report2.get("total_tokens") or 0)
            report["validation_result"] = "pass" if not errs2 else f"fail:{errs2}"
            humanized = humanized2
            errs = errs2
            if errs:
                print(f"SKIP gen failed after retry: {errs}")
                print(json.dumps({"api_report": report}, indent=2))
                draft = assemble_blog(bundle, humanized, report)
                draft["status"] = "draft_failed"
                draft["capability_id"] = capability["id"]
                draft["research"] = _research_provenance_list(research)
                bundle["capability_id"] = capability["id"]
                bundle["research_provenance"] = draft["research"]
                save_local(draft, ctx, humanized, report)
                return 5

        print(
            f"    tokens in={report.get('input_tokens')} out={report.get('output_tokens')} "
            f"total={report.get('total_tokens')} retry={report.get('retry_count')} "
            f"validation={report.get('validation_result')}"
        )
        humanized["capability_id"] = capability["id"]
        print("[4] Assemble page from LLM + DB (Firebase stores blog-only subset)")
        bundle["capability_id"] = capability["id"]
        bundle["research_provenance"] = _research_provenance_list(research)
        page = assemble_blog(bundle, humanized, report)
        page["capability_id"] = capability["id"]
        page["research"] = bundle["research_provenance"]
        page["community_questions"] = community_questions_from(research, humanized)

    page.setdefault("customize_fixed", CUSTOMIZE_FIXED)
    page["status"] = page.get("status") or "ready"
    if not page.get("blog_post_id"):
        page["blog_post_id"] = page.get("blog_id") or f"blog_{page['slug']}"

    local_path = save_local(page, ctx, humanized, report)
    print(f"[5] Local slim blog saved: {local_path}")

    fs_path = None
    fs_write_error = None
    slim_doc = firestore_doc_from_page(page)
    if args.force:
        cleanup_superseded_blog(args.recipe_id, slim_doc["blog_id"], slim_doc["slug"])
    if args.skip_write or args.dry_run:
        print("[6] Skip Firestore write")
    else:
        print(f"[6] WRITE {ALLOWED_WRITE_COLLECTION}/{slim_doc['blog_id']} (blog-only fields)")
        try:
            fs_path = write_blog_post_only(slim_doc["blog_id"], slim_doc)
            verify = read_doc(fs_path)
            print(f"    verified keys={sorted(verify.keys())}")
        except Exception as e:
            fs_write_error = str(e)
            print(f"    WARN Firestore write failed (local blog saved): {e}")

    summary = {
        "ok": True,
        "recipe_id": args.recipe_id,
        "blog_id": slim_doc["blog_id"],
        "slug": slim_doc["slug"],
        "capability_id": slim_doc.get("capability_id"),
        "firestore_fields": sorted(slim_doc.keys()),
        "local_path": str(local_path),
        "firestore_path": fs_path,
        "firestore_write_error": fs_write_error,
        "api_report": report,
        "landing": "http://127.0.0.1:8765/",
        "post": f"http://127.0.0.1:8765/post.html?slug={slim_doc['slug']}",
        "write_policy": "blog_posts only — no recipe fact copies",
    }
    print(json.dumps(summary, indent=2))
    (ROOT / "preview" / "data" / "last-pipeline-run.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return 0


def _research_provenance_list(research: dict) -> list[dict]:
    items = []
    primary = research.get("primary_question") or {}
    if primary.get("question"):
        items.append(
            {
                "q": primary.get("question"),
                "source": primary.get("source"),
                "source_url": primary.get("source_url"),
                "evidence_type": primary.get("evidence_type"),
            }
        )
    for r in research.get("related_questions") or []:
        items.append(
            {
                "q": r.get("question"),
                "source": r.get("source"),
                "source_url": r.get("source_url"),
                "evidence_type": r.get("evidence_type"),
            }
        )
    return items


if __name__ == "__main__":
    raise SystemExit(main())
