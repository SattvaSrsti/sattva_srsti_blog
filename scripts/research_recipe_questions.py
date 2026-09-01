#!/usr/bin/env python3
"""
Research cooking intents for a recipe (Quora / Reddit / food sites).

Connectors (v1):
  - quora / food_site → web_search (DuckDuckGo HTML lite or curated seed pack)
  - reddit → approved OAuth if REDDIT_* env set; else manual/seed only (never unauthenticated .json)
  - generated_intent → fill remaining slots; source_url must be null

Normalizer = extract + compress only (no new cooking claims).

Output: preview/data/{slug}.research.json
  primary_question (1) + related_questions (4) = 5 intents, no duplication.

Usage:
  python scripts/research_recipe_questions.py --recipe-id rec_mysore_masala_dosa
  python scripts/research_recipe_questions.py --recipe-id rec_mysore_masala_dosa --from-seed
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
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
    if "arrayValue" in value:
        return [from_fs(v) for v in value.get("arrayValue", {}).get("values", [])]
    if "mapValue" in value:
        fields = value.get("mapValue", {}).get("fields", {})
        return {k: from_fs(v) for k, v in fields.items()}
    return value


def read_doc(path: str) -> dict:
    url = f"{FS_BASE}/{path}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return {k: from_fs(v) for k, v in (raw.get("fields") or {}).items()}


def slugify(text: str) -> str:
    out = []
    for ch in text.lower().strip():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_/" and (not out or out[-1] != "-"):
            out.append("-")
    return "".join(out).strip("-") or "recipe"


def normalize_question_key(q: str) -> str:
    q = q.lower().strip()
    q = re.sub(r"[^a-z0-9\s]", " ", q)
    q = re.sub(r"\s+", " ", q)
    return q


def compress_evidence(snippets: list[str], *, max_bullets: int = 5) -> list[str]:
    """Extract + compress only. No new cooking claims — trim and dedupe source lines."""
    bullets: list[str] = []
    seen: set[str] = set()
    for raw in snippets:
        if not raw:
            continue
        # Split long blobs into sentence-ish chunks; keep only short explicit claims
        parts = re.split(r"(?<=[.!])\s+|\n+", str(raw).strip())
        for part in parts:
            line = re.sub(r"\s+", " ", part).strip(" -•*\t")
            if len(line) < 12 or len(line) > 180:
                continue
            # Drop meta / UI noise
            low = line.lower()
            if any(x in low for x in ("cookie", "subscribe", "sign up", "javascript", "cloudflare")):
                continue
            key = normalize_question_key(line)[:80]
            if key in seen:
                continue
            seen.add(key)
            bullets.append(line)
            if len(bullets) >= max_bullets:
                return bullets
    return bullets[:max_bullets]


def truncate_question(q: str, max_words: int = 28) -> str:
    words = q.strip().split()
    if len(words) <= max_words:
        return q.strip()
    return " ".join(words[:max_words]).rstrip(".,;:") + "?"


# ---------- Connectors ----------

def connector_web_search(query: str, *, limit: int = 8) -> list[dict]:
    """
    Lightweight web search via DuckDuckGo HTML (no API key).
    Returns candidate dicts with title, url, snippet — may be empty if blocked.
    """
    results: list[dict] = []
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SattvaSrstiBlogResearch/1.0 (+local research)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return results

    # Very small parser: result links + snippets
    for m in re.finditer(
        r'uddg=([^&"]+).*?class="result__a"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</(?:a|td)',
        html,
        flags=re.I | re.S,
    ):
        try:
            link = urllib.parse.unquote(m.group(1))
        except Exception:
            continue
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", m.group(3)).strip()
        if not title:
            continue
        results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) >= limit:
            break

    if results:
        return results

    # Fallback simpler pattern
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S):
        href = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if "uddg=" in href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            link = urllib.parse.unquote(qs.get("uddg", [href])[0])
        else:
            link = href
        results.append({"title": title, "url": link, "snippet": title})
        if len(results) >= limit:
            break
    return results


def connector_reddit_approved(query: str, *, limit: int = 8) -> list[dict]:
    """
    Reddit via approved OAuth client credentials if env present.
    Never use unauthenticated search.json.
    """
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return []

    auth = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        headers={
            "User-Agent": os.environ.get("REDDIT_USER_AGENT", "SattvaSrstiBlog/1.0"),
        },
        method="POST",
    )
    # Basic auth
    import base64

    token = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    auth.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(auth, timeout=30) as resp:
            tok = json.loads(resp.read().decode("utf-8")).get("access_token")
    except Exception:
        return []
    if not tok:
        return []

    search_url = (
        "https://oauth.reddit.com/search?"
        + urllib.parse.urlencode({"q": query, "limit": str(limit), "sort": "relevance", "type": "link"})
    )
    req = urllib.request.Request(
        search_url,
        headers={
            "Authorization": f"Bearer {tok}",
            "User-Agent": os.environ.get("REDDIT_USER_AGENT", "SattvaSrstiBlog/1.0"),
        },
        method="GET",
    )
    out: list[dict] = []
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    for child in (data.get("data") or {}).get("children") or []:
        d = child.get("data") or {}
        title = d.get("title") or ""
        permalink = d.get("permalink") or ""
        selftext = (d.get("selftext") or "")[:400]
        if not title:
            continue
        url = f"https://www.reddit.com{permalink}" if permalink else None
        out.append({"title": title, "url": url, "snippet": selftext or title})
    return out


def classify_url(url: str | None) -> tuple[str, str]:
    """Return (source, evidence_type). Never invent quora/reddit without matching URL."""
    if not url:
        return "generated_intent", "generated"
    u = url.lower()
    if "quora.com" in u:
        return "quora", "community"
    if "reddit.com" in u:
        return "reddit", "community"
    return "food_site", "food_site"


def candidate_from_hit(hit: dict, dish: str) -> dict | None:
    title = (hit.get("title") or "").strip()
    url = hit.get("url")
    snippet = hit.get("snippet") or ""
    if not title:
        return None
    # Prefer titles that look like questions
    q = title
    if "?" not in q and not re.match(r"(?i)^(why|how|what|should|can|does|is my)", q):
        # Keep as related intent only if dish mentioned
        if dish.lower().split()[0] not in q.lower() and "dosa" not in q.lower() and dish.lower() not in q.lower():
            return None
        q = f"Why does my {dish} have issues with: {q}?"
    source, evidence_type = classify_url(url)
    # food_site cannot be labeled quora/reddit
    if source == "food_site":
        # Question source for food-site-only hits becomes generated_intent unless title is from community
        # Keep food_site as evidence_type; question source = generated_intent if not community
        q_source = "generated_intent"
        q_url = None
        evidence_type = "food_site"
    else:
        q_source = source
        q_url = url
        if q_source in ("quora", "reddit") and not q_url:
            return None

    evidence = compress_evidence([snippet, title])
    if not evidence:
        evidence = compress_evidence([snippet]) or [snippet[:160]] if snippet else []
    if not evidence:
        return None

    return {
        "question": truncate_question(q),
        "source": q_source if q_source != "food_site" else "generated_intent",
        "source_url": q_url,
        "evidence_type": evidence_type,
        "evidence": evidence[:5],
        "connector": "web_search" if q_source != "reddit" else "approved_reddit",
        "_score": score_candidate(q, dish, evidence_type),
    }


GENERIC_PRIMARY_BANNED = (
    "common mistakes when making",
    "not turn out right",
    "fix common mistakes",
)


def is_generic_primary(question: str) -> bool:
    q = question.lower()
    return any(p in q for p in GENERIC_PRIMARY_BANNED)


def score_candidate(question: str, dish: str, evidence_type: str) -> float:
    q = question.lower()
    score = 0.0
    if dish.lower() in q:
        score += 3.0
    for token in dish.lower().split():
        if len(token) > 3 and token in q:
            score += 0.5
    if any(w in q for w in ("why", "how", "not", "crispy", "stick", "soft", "batter")):
        score += 1.5
    if evidence_type == "community":
        score += 2.0
    elif evidence_type == "food_site":
        score += 0.8
    elif evidence_type == "recipe_warning":
        score += 4.0
    elif evidence_type == "recipe_cue":
        score += 3.0
    if is_generic_primary(q):
        score -= 8.0
    return score


def _warning_to_question(dish: str, warning: str) -> str | None:
    """Map a recipe warning to a concrete cooking question."""
    w = warning.lower()
    d = dish
    if "crisp" in w or "crispy" in w or "crackling" in w:
        return f"Why is my {d} not crispy?"
    if "stick" in w or "stuck" in w or "tear" in w or "tearing" in w:
        return f"Why does my {d} stick or tear?"
    if "soggy" in w or " mushy" in w or "too soft" in w:
        return f"Why is my {d} turning out soggy?"
    if "bitter" in w or "burnt" in w or "scorch" in w:
        return f"Why does my {d} taste bitter or burnt?"
    if "batter" in w or "ferment" in w:
        return f"Why is my {d} batter not right?"
    if "water" in w and ("soak" in w or "rinse" in w):
        return f"Why does rinsing or soaking affect my {d}?"
    if "oil" in w or "ghee" in w:
        return f"Why does the oil or fat stage matter for {d}?"
    if "spice" in w or "heat" in w or "chilli" in w or "chili" in w:
        return f"Why is my {d} too spicy or bland?"
    if "curdle" in w or "split" in w:
        return f"Why does my {d} curdle or split?"
    if "dense" in w or "heavy" in w or "dry" in w:
        return f"Why is my {d} too dense or dry?"
    return None


def recipe_db_intents(dish: str, recipe_id: str, root: dict) -> list[dict]:
    """Concrete questions grounded in mistake_warnings and sensory_cues from recipes_v2."""
    warnings: list[str] = []
    cues: list[str] = []
    try:
        instructions = read_doc(f"recipes_v2/{recipe_id}/instructions/details")
    except Exception:
        instructions = {}
    for step in instructions.get("steps") or []:
        for w in step.get("mistake_warnings") or []:
            warnings.append(str(w))
        for c in step.get("sensory_cues") or []:
            cues.append(str(c))
    about = root.get("about_recipe")
    if about:
        warnings.append(str(about))

    intents: list[dict] = []
    seen: set[str] = set()

    for w in warnings:
        q = _warning_to_question(dish, w)
        if not q or is_generic_primary(q):
            continue
        key = normalize_question_key(q)
        if key in seen:
            continue
        seen.add(key)
        ev = compress_evidence([w])
        if not ev:
            continue
        intents.append(
            {
                "question": truncate_question(q),
                "source": "generated_intent",
                "source_url": None,
                "evidence_type": "recipe_warning",
                "evidence": ev[:5],
                "connector": "recipe_db",
                "_score": score_candidate(q, dish, "recipe_warning"),
            }
        )

    related_templates = [
        (f"How can I improve my {dish}?", warnings[:8], "recipe_warning"),
        (f"How do I know {dish} is ready?", cues[:8], "recipe_cue"),
        (f"How do I get better texture for {dish}?", warnings[:6] + cues[:4], "recipe_warning"),
        (f"What should I watch while making {dish}?", warnings[:8], "recipe_warning"),
        (f"How can I improve the taste of my {dish}?", warnings[:6], "recipe_warning"),
    ]
    for template_q, pool, ev_type in related_templates:
        key = normalize_question_key(template_q)
        if key in seen:
            continue
        ev = compress_evidence(pool)
        if not ev:
            continue
        seen.add(key)
        intents.append(
            {
                "question": truncate_question(template_q),
                "source": "generated_intent",
                "source_url": None,
                "evidence_type": ev_type,
                "evidence": ev[:5],
                "connector": "recipe_db",
                "_score": score_candidate(template_q, dish, ev_type),
            }
        )
    return intents


def generated_intents_for(dish: str, cuisine: str, pool_evidence: list[str]) -> list[dict]:
    """New questions OK; evidence must come only from retrieved/known recipe material."""
    templates = [
        f"How do I get better texture for {dish}?",
        f"What should I watch while making {dish}?",
        f"How do I know {dish} is ready?",
        f"How can I improve my {dish}?",
        f"How can I improve the taste of my {dish}?",
        f"Why does {dish} taste different from restaurant versions?",
    ]
    evidence = compress_evidence(pool_evidence)
    if not evidence:
        return []
    out = []
    for t in templates:
        out.append(
            {
                "question": truncate_question(t),
                "source": "generated_intent",
                "source_url": None,
                "evidence_type": "generated",
                "evidence": evidence[:5],
                "connector": "code",
                "_score": 0.15,
            }
        )
    return out


def recipe_db_evidence(recipe_id: str, root: dict) -> list[str]:
    """Compress-only evidence from Firebase recipe facts (warnings, cues, about)."""
    snippets: list[str] = []
    about = root.get("about_recipe")
    if about:
        snippets.append(str(about))
    try:
        instructions = read_doc(f"recipes_v2/{recipe_id}/instructions/details")
    except Exception:
        instructions = {}
    for step in instructions.get("steps") or []:
        for w in step.get("mistake_warnings") or []:
            snippets.append(str(w))
        for c in step.get("sensory_cues") or []:
            snippets.append(str(c))
        tip = step.get("pro_tip") or step.get("tip")
        if tip:
            snippets.append(str(tip))
    return compress_evidence(snippets, max_bullets=12)


def _candidates_from_legacy_questions(raw: dict) -> list[dict]:
    hits = []
    title = raw.get("recipe_title") or (raw.get("recipe") or {}).get("title") or ""
    for item in raw.get("research_questions") or []:
        src = item.get("source") or "food_site"
        url = item.get("source_url")
        if src == "established_site":
            src = "food_site"
        answers = item.get("source_answers") or item.get("evidence") or []
        evidence = compress_evidence(answers)
        if src in ("quora", "reddit", "food_site"):
            q_source = src
            q_url = url
            evidence_type = "community" if src in ("quora", "reddit") else "food_site"
        else:
            q_source = "generated_intent"
            q_url = None
            evidence_type = "generated"
        hits.append(
            {
                "question": truncate_question(item.get("q") or item.get("question") or ""),
                "source": q_source,
                "source_url": q_url,
                "evidence_type": evidence_type,
                "evidence": evidence,
                "connector": "manual",
                "_score": score_candidate(item.get("q") or item.get("question") or "", title, evidence_type),
            }
        )
    return [h for h in hits if h.get("question") and h.get("evidence")]


def _candidates_from_pack(pack: dict) -> list[dict]:
    """Turn an existing research pack (new schema) back into scored candidates."""
    hits = []
    title = (pack.get("recipe") or {}).get("title") or ""
    items = []
    if pack.get("primary_question"):
        items.append(pack["primary_question"])
    items.extend(pack.get("related_questions") or [])
    for item in items:
        src = item.get("source") or "generated_intent"
        if src == "established_site":
            src = "food_site"
        evidence = item.get("evidence") or []
        if not evidence:
            continue
        hits.append(
            {
                "question": truncate_question(item.get("question") or ""),
                "source": src,
                "source_url": item.get("source_url"),
                "evidence_type": item.get("evidence_type")
                or ("community" if src in ("quora", "reddit") else ("food_site" if src == "food_site" else "generated")),
                "evidence": evidence[:5],
                "connector": item.get("connector") or "manual",
                "_score": score_candidate(item.get("question") or "", title, item.get("evidence_type") or ""),
            }
        )
    return hits


def load_seed_pack(recipe_id: str) -> list[dict]:
    """Optional curated seed file for recipes (manual connector)."""
    path = ROOT / "preview" / "data" / "research_seeds" / f"{recipe_id}.json"
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict) and raw.get("research_questions"):
            return _candidates_from_legacy_questions(raw)
        if isinstance(raw, dict) and raw.get("primary_question"):
            return _candidates_from_pack(raw)
        return []

    # Fallback: migrate legacy mysore research file (preview or deploy copy)
    for legacy in (
        ROOT / "preview" / "data" / "mysore-masala-dosa.research.json",
        ROOT / "deploy" / "public" / "data" / "mysore-masala-dosa.research.json",
    ):
        if recipe_id != "rec_mysore_masala_dosa" or not legacy.exists():
            continue
        raw = json.loads(legacy.read_text(encoding="utf-8"))
        if raw.get("research_questions"):
            return _candidates_from_legacy_questions(raw)
        if raw.get("primary_question"):
            return _candidates_from_pack(raw)
    return []

def validate_provenance(item: dict) -> bool:
    src = item.get("source")
    url = item.get("source_url")
    if src in ("quora", "reddit", "food_site"):
        return bool(url)
    if src == "generated_intent":
        return url is None
    return False


def select_five(candidates: list[dict], dish: str, cuisine: str) -> dict:
    # Filter provenance
    clean = [c for c in candidates if validate_provenance(c) and c.get("evidence")]
    # Dedupe by question key
    seen: set[str] = set()
    uniq: list[dict] = []
    for c in sorted(clean, key=lambda x: -x.get("_score", 0)):
        key = normalize_question_key(c["question"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    pool_evidence: list[str] = []
    for c in uniq:
        pool_evidence.extend(c.get("evidence") or [])

    if len(uniq) < 5:
        for g in generated_intents_for(dish, cuisine, pool_evidence):
            key = normalize_question_key(g["question"])
            if key in seen:
                continue
            if not g.get("evidence"):
                continue
            seen.add(key)
            uniq.append(g)
            if len(uniq) >= 5:
                break

    if not uniq:
        raise RuntimeError("No research candidates with grounded evidence")

    primary = None
    for c in uniq:
        if not is_generic_primary(c["question"]):
            primary = c
            break
    if not primary:
        primary = uniq[0]
    related = []
    for c in uniq[1:]:
        if normalize_question_key(c["question"]) == normalize_question_key(primary["question"]):
            continue
        related.append(c)
        if len(related) == 4:
            break

    # Fill related to 4
    if len(related) < 4:
        for g in generated_intents_for(dish, cuisine, pool_evidence):
            if normalize_question_key(g["question"]) == normalize_question_key(primary["question"]):
                continue
            if any(normalize_question_key(g["question"]) == normalize_question_key(r["question"]) for r in related):
                continue
            if not g.get("evidence"):
                continue
            related.append(g)
            if len(related) == 4:
                break

    if len(related) < 4:
        raise RuntimeError(f"Could not fill 4 related questions (got {len(related)})")

    def strip(c: dict) -> dict:
        return {
            "question": c["question"],
            "source": c["source"],
            "source_url": c.get("source_url"),
            "evidence_type": c.get("evidence_type"),
            "evidence": (c.get("evidence") or [])[:5],
            "connector": c.get("connector"),
        }

    return {
        "recipe": {"title": dish, "cuisine": cuisine},
        "primary_question": strip(primary),
        "related_questions": [strip(r) for r in related[:4]],
    }


def research_recipe(recipe_id: str, *, from_seed: bool = False, refresh: bool = False) -> dict:
    root = read_doc(f"recipes_v2/{recipe_id}")
    title = root.get("title") or "Recipe"
    cuisine = root.get("cuisine") or "Indian"
    tags = root.get("search_tags") or []
    slug = root.get("slug") or slugify(title)

    out_path = ROOT / "preview" / "data" / f"{slug}.research.json"
    if out_path.exists() and not refresh and not from_seed:
        # Prefer new schema; migrate if old
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        if existing.get("primary_question") and existing.get("related_questions"):
            return existing

    candidates: list[dict] = []

    # Always collect recipe-DB evidence (warnings/cues/about) for grounded generated intents
    db_evidence = recipe_db_evidence(recipe_id, root)
    for intent in recipe_db_intents(title, recipe_id, root):
        candidates.append(intent)

    # Seed / manual first (honest curated)
    for item in load_seed_pack(recipe_id):
        if validate_provenance(item) and item.get("evidence"):
            candidates.append(item)

    if not from_seed:
        queries = [
            f"site:quora.com {title} cooking problem OR mistake OR soft OR stick",
            f"site:reddit.com {title} recipe tip OR help",
            f"{title} common cooking mistakes",
            f"{title} how to make better at home",
        ]
        if tags:
            queries.append(f"{tags[0]} cooking tips problems")

        for q in queries[:4]:
            for hit in connector_web_search(q, limit=6):
                c = candidate_from_hit(hit, title)
                if c:
                    candidates.append(c)
            for hit in connector_reddit_approved(q, limit=5):
                c = candidate_from_hit(hit, title)
                if c:
                    c["connector"] = "approved_reddit"
                    candidates.append(c)

    # If web/seed thin, fill with generated intents grounded in recipe DB evidence
    if len([c for c in candidates if validate_provenance(c) and c.get("evidence")]) < 5 and db_evidence:
        for g in generated_intents_for(title, cuisine, db_evidence):
            candidates.append(g)

    pack = select_five(candidates, title, cuisine)
    pack["recipe_id"] = recipe_id
    pack["slug"] = slug
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return pack


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe-id", required=True)
    ap.add_argument("--from-seed", action="store_true", help="Use curated seed/manual only")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    pack = research_recipe(args.recipe_id, from_seed=args.from_seed, refresh=args.refresh)
    print(json.dumps({"ok": True, "primary": pack["primary_question"]["question"], "related": len(pack["related_questions"]), "path": f"preview/data/{pack.get('slug')}.research.json"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
