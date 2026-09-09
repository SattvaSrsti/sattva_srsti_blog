#!/usr/bin/env python3
"""
Research cooking intents for a recipe (Quora / Reddit / food sites).

Connectors (v1):
  - OpenAI Responses API + web_search (high context), prefer Quora/Reddit by votes, then official food sites
  - quora / food_site → DuckDuckGo HTML lite or curated seed pack
  - reddit → approved OAuth if REDDIT_* env set; else search/seed only (never unauthenticated .json)
  - generated_intent / recipe_db → fill remaining slots only; source_url must be null

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


def is_quora_question_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        from urllib.parse import urlparse

        u = urlparse(url)
        host = (u.hostname or "").replace("www.", "").lower()
        if host != "quora.com":
            return False
        parts = [p for p in (u.path or "").split("/") if p]
        if not parts:
            return False
        first = parts[0].lower()
        if first in {
            "profile",
            "topic",
            "search",
            "about",
            "login",
            "webnode",
            "careers",
            "q",
            "spaces",
            "answer",
            "share",
            "widgets",
            "challenges",
        }:
            return False
        slug = parts[1] if first == "unanswered" else parts[0]
        if not slug or slug.isdigit():
            return False
        return "-" in slug and len(slug.replace("-", "").replace("_", "")) >= 10
    except Exception:
        return False


def is_reddit_thread_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        from urllib.parse import urlparse

        u = urlparse(url)
        host = (u.hostname or "").replace("www.", "").lower()
        if not host.endswith("reddit.com"):
            return False
        return bool(re.search(r"/r/[^/]+/comments/[a-z0-9]+(/|$)", u.path or "", re.I))
    except Exception:
        return False


def classify_url(url: str | None) -> tuple[str, str]:
    """Return (source, evidence_type). Never invent quora/reddit without matching URL."""
    if not url:
        return "generated_intent", "generated"
    u = url.lower()
    if "quora.com" in u:
        if not is_quora_question_url(url):
            return "generated_intent", "generated"
        return "quora", "community"
    if "reddit.com" in u:
        if not is_reddit_thread_url(url):
            return "generated_intent", "generated"
        return "reddit", "community"
    return "food_site", "food_site"


def candidate_from_hit(hit: dict, dish: str) -> dict | None:
    title = (hit.get("title") or "").strip()
    url = hit.get("url")
    snippet = hit.get("snippet") or ""
    source, evidence_type = classify_url(url)
    if source == "generated_intent":
        return None
    if not title and source != "quora":
        return None
    q = title
    if source == "quora":
        if not q or "?" not in q:
            q = title or snippet or url or f"Cooking question about {dish}?"
    elif "?" not in q and not re.match(r"(?i)^(why|how|what|should|can|does|is my)", q):
        # Keep as related intent only if dish mentioned
        if dish.lower().split()[0] not in q.lower() and "dosa" not in q.lower() and dish.lower() not in q.lower():
            return None
        q = f"Why does my {dish} have issues with: {q}?"
    q_source = source
    q_url = url
    if q_source in ("quora", "reddit", "food_site") and not q_url:
        return None

    evidence = compress_evidence([snippet, title])
    if not evidence:
        evidence = compress_evidence([snippet]) or ([snippet[:160]] if snippet else [])
    if not evidence:
        return None

    votes = 0
    vote_m = re.search(r"(\d+)\s*(?:upvote|upvotes|votes|answers)", f"{title} {snippet}", re.I)
    if vote_m:
        votes = int(vote_m.group(1))
    community_bonus = 20.0 if evidence_type == "community" else (8.0 if evidence_type == "food_site" else 0.0)
    return {
        "question": truncate_question(q),
        "source": q_source,
        "source_url": q_url,
        "evidence_type": evidence_type,
        "evidence": evidence[:5],
        "connector": "web_search" if q_source != "reddit" else "approved_reddit",
        "votes": votes,
        "_score": score_candidate(q, dish, evidence_type) + min(votes, 250) / 10 + community_bonus,
    }


GENERIC_PRIMARY_BANNED = (
    "common mistakes when making",
    "not turn out right",
    "not turning out right",
    "fix common mistakes",
)


def is_generic_primary(question: str) -> bool:
    q = question.lower()
    return any(p in q for p in GENERIC_PRIMARY_BANNED)


_WEAK_DISH = {
    "roast",
    "roasted",
    "chicken",
    "rice",
    "curry",
    "fried",
    "sauce",
    "gravy",
    "dish",
    "recipe",
    "with",
    "and",
    "the",
    "for",
    "from",
    "style",
    "home",
    "special",
    "masala",
    "ghee",
    "oil",
    "dry",
    "wet",
    "hot",
    "sweet",
}


def dish_alias_tokens(dish: str) -> list[str]:
    title = re.sub(r"[^a-z0-9\s]", " ", (dish or "").lower())
    tokens = [t for t in title.split() if len(t) > 2]
    aliases = set(tokens)
    if re.search(r"gobi|cauliflower", title) and "manchur" in title.replace(" ", ""):
        aliases.update(["gobi", "manchurian", "cauliflower"])
    if "paneer" in title:
        aliases.add("paneer")
    if "dosa" in title:
        aliases.add("dosa")
    if "idli" in title:
        aliases.add("idli")
    if "biryani" in title:
        aliases.add("biryani")
    if "gulab" in title or "jamun" in title:
        aliases.update(["gulab", "jamun"])
    return list(aliases)


def mentions_dish(text: str, dish: str) -> bool:
    hay = (text or "").lower()
    if not hay.strip():
        return False
    tokens = dish_alias_tokens(dish)
    strong = [t for t in tokens if len(t) > 3 and t not in _WEAK_DISH]
    weak = [t for t in tokens if t in _WEAK_DISH or len(t) <= 3]

    def word_hit(t: str) -> bool:
        return re.search(rf"(?:^|[^a-z0-9]){re.escape(t)}s?(?:[^a-z0-9]|$)", hay) is not None

    if any(word_hit(t) for t in strong):
        return True
    phrase = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (dish or "").lower())).strip()
    if len(phrase) >= 8 and phrase in hay:
        return True
    return sum(1 for t in weak if word_hit(t)) >= 2 and not strong


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
        score += 12.0
    elif evidence_type == "food_site":
        score += 6.0
    elif evidence_type == "recipe_warning":
        score += 1.2
    elif evidence_type == "recipe_cue":
        score += 1.0
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
    out: list[dict] = []
    paths = [
        ROOT / "preview" / "data" / "research_seeds" / f"{recipe_id}.json",
        ROOT / "preview" / "data" / "research_seeds" / "quora_recipe_questions.json",
        ROOT / "functions" / "research_seeds" / f"{recipe_id}.json",
        ROOT / "functions" / "research_seeds" / "quora_recipe_questions.json",
    ]
    for path in paths:
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            out.extend(raw)
        elif isinstance(raw, dict) and raw.get("research_questions"):
            out.extend(_candidates_from_legacy_questions(raw))
        elif isinstance(raw, dict) and raw.get("primary_question"):
            out.extend(_candidates_from_pack(raw))

    # Fallback: migrate legacy mysore research file (preview or deploy copy)
    if recipe_id == "rec_mysore_masala_dosa":
        for legacy in (
            ROOT / "preview" / "data" / "mysore-masala-dosa.research.json",
            ROOT / "deploy" / "public" / "data" / "mysore-masala-dosa.research.json",
        ):
            if not legacy.exists():
                continue
            raw = json.loads(legacy.read_text(encoding="utf-8"))
            if raw.get("research_questions"):
                out.extend(_candidates_from_legacy_questions(raw))
            elif raw.get("primary_question"):
                out.extend(_candidates_from_pack(raw))
    return out

def _openai_research_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_KEY")


def _parse_json_object(text: str) -> dict | None:
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    body = fence.group(1) if fence else raw
    start = body.find("{")
    end = body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(body[start : end + 1])
    except Exception:
        return None


def _extract_responses_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"]
    parts: list[str] = []
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for c in item.get("content") or []:
            if c.get("type") in ("output_text", "text") and c.get("text"):
                parts.append(c["text"])
    return "\n".join(parts)


def openai_web_research(dish: str, cuisine: str, *, mode: str, domains: list[str]) -> list[dict]:
    """OpenAI Responses API + web_search. Real URLs only."""
    key = _openai_research_key()
    if not key:
        return []
    where = (
        'ONLY www.quora.com question pages (https://www.quora.com/How-... or /What-...). '
        "Never help.quora.com, profile, or topic pages. Any cooking question is fine — no vote standards."
        if mode == "community"
        else "ONLY established food websites. Prefer real reader questions or specific problem headlines."
    )
    prompt = (
        f'Find REAL cooking questions people ask about "{dish}" ({cuisine or "Indian"} food).\n'
        f"Search {where}\n"
        f'Need specific kitchen failures — NOT the generic "Why is my {dish} not turning out right?"\n'
        'Return JSON only: {"questions":[{"question":"...","source_url":"https://...",'
        '"votes_or_engagement":"128 upvotes or unknown","evidence":["short snippet"]}]}\n'
        "Rules: natural human questions; copy real URLs from search results; 6–10 distinct questions; do not invent URLs."
    )
    body = {
        "model": os.environ.get("OPENAI_RESEARCH_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4o-mini")),
        "tools": [
            {
                "type": "web_search",
                "search_context_size": "high",
                "user_location": {"type": "approximate", "country": "IN"},
            }
        ],
        "tool_choice": {"type": "web_search"},
        "include": ["web_search_call.action.sources"],
        "input": prompt,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  WARN openai web_search ({mode}): {e}")
        return []
    parsed = _parse_json_object(_extract_responses_text(data)) or {}
    source_urls: list[str] = []
    for item in data.get("output") or []:
        if item.get("type") != "web_search_call":
            continue
        action = item.get("action") or {}
        for s in action.get("sources") or item.get("sources") or []:
            u = s if isinstance(s, str) else (s or {}).get("url")
            if u:
                source_urls.append(str(u))
    hits = []
    seen = set()
    for url in source_urls:
        if url in seen:
            continue
        seen.add(url)
        source, evidence_type = classify_url(url)
        if source == "generated_intent":
            continue
        q = url
        try:
            from urllib.parse import unquote, urlparse

            slug = [p for p in urlparse(url).path.split("/") if p]
            raw = slug[-1] if slug else ""
            words = unquote(raw).replace("-", " ").replace("_", " ").strip()
            if words:
                q = words[0].upper() + words[1:]
                if not q.endswith("?"):
                    q += "?"
        except Exception:
            pass
        hits.append(
            {
                "question": truncate_question(q),
                "source": source,
                "source_url": url,
                "evidence_type": evidence_type,
                "evidence": [f"{source} link: {url}"],
                "connector": "openai_web_search",
                "votes": 0,
                "_score": score_candidate(q, dish, evidence_type) + (40.0 if source == "quora" else 0),
            }
        )
    for item in parsed.get("questions") or []:
        url = item.get("source_url")
        q = (item.get("question") or "").strip()
        if not q or not url or is_generic_primary(q):
            continue
        if source_urls and url.rstrip("/") not in {s.rstrip("/") for s in source_urls}:
            continue
        source, evidence_type = classify_url(url)
        if source == "generated_intent":
            continue
        evidence = compress_evidence(item.get("evidence") or [])
        if not evidence:
            continue
        vote_raw = item.get("votes_or_engagement") or ""
        vote_m = re.search(r"(\d+)", str(vote_raw).replace(",", ""))
        votes = int(vote_m.group(1)) if vote_m else 0
        bonus = 20.0 if evidence_type == "community" else 8.0
        hits.append(
            {
                "question": truncate_question(q),
                "source": source,
                "source_url": url,
                "evidence_type": evidence_type,
                "evidence": evidence[:5],
                "connector": "openai_web_search",
                "votes": votes,
                "_score": score_candidate(q, dish, evidence_type) + min(votes, 250) / 10 + bonus,
            }
        )
    return hits


def collect_openai_web_candidates(dish: str, cuisine: str) -> list[dict]:
    community = openai_web_research(
        dish, cuisine, mode="community", domains=["quora.com", "reddit.com"]
    )
    sites = openai_web_research(
        dish,
        cuisine,
        mode="food_site",
        domains=[
            "seriouseats.com",
            "thekitchn.com",
            "indianhealthyrecipes.com",
            "vegrecipesofindia.com",
            "hebbarskitchen.com",
            "archanaskitchen.com",
            "food52.com",
            "ndtv.com",
            "timesofindia.indiatimes.com",
            "bonappetit.com",
        ],
    )
    print(f"    openai web_search community={len(community)} food_sites={len(sites)}")
    return community + sites


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
    community = []
    for c in uniq:
        if is_generic_primary(c["question"]):
            continue
        hay = f"{c.get('question') or ''} {c.get('source_url') or ''}"
        if not mentions_dish(hay, dish):
            continue
        src = c.get("source")
        url = c.get("source_url")
        if src == "quora" and is_quora_question_url(url):
            community.append(c)
        elif src == "reddit" and is_reddit_thread_url(url):
            community.append(c)
    community.sort(key=lambda c: (0 if c.get("source") == "quora" else 1, -c.get("_score", 0)))
    if len(community) < 3:
        raise RuntimeError(
            f'Need at least 3 same-dish Quora/Reddit links for "{dish}", got {len(community)}'
        )
    picked = community[:6]
    primary = picked[0]
    related = picked[1:]

    def strip(c: dict) -> dict:
        return {
            "question": c["question"],
            "source": c["source"],
            "source_url": c.get("source_url"),
            "evidence_type": c.get("evidence_type"),
            "evidence": (c.get("evidence") or [])[:5],
            "connector": c.get("connector"),
            "votes": c.get("votes") or 0,
        }

    return {
        "recipe": {"title": dish, "cuisine": cuisine},
        "questions": [strip(c) for c in picked],
        "primary_question": strip(primary),
        "related_questions": [strip(r) for r in related],
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

    # Live web research first: Quora/Reddit (votes) then official food sites
    if not from_seed:
        try:
            for item in collect_openai_web_candidates(title, cuisine):
                if validate_provenance(item) and item.get("evidence"):
                    candidates.append(item)
        except Exception as e:
            print(f"    WARN openai research: {e}")

        queries = [
            f'site:www.quora.com "{title}"',
            f"site:www.quora.com {title} recipe",
            f"site:www.quora.com how to make {title}",
            f"site:reddit.com {title} recipe tip OR help",
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

    # Seed / manual curated (honest Quora URLs)
    for item in load_seed_pack(recipe_id):
        if validate_provenance(item) and item.get("evidence"):
            candidates.append(item)

    real_count = len(
        [c for c in candidates if c.get("source") in ("quora", "reddit", "food_site") and c.get("source_url")]
    )
    # Recipe-DB / generated only to fill remaining slots — never as the first choice
    db_evidence = recipe_db_evidence(recipe_id, root)
    if real_count < 5:
        for intent in recipe_db_intents(title, recipe_id, root):
            candidates.append(intent)
        if db_evidence:
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
