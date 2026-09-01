#!/usr/bin/env python3
"""Remove superseded local blog JSON and rebuild posts-index from latest files."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "preview" / "data"

STALE_PATTERNS = ("-common-mistakes.blog.json",)


def score_blog_file(path: Path, j: dict) -> tuple:
    """Higher is better. Prefer specific questions over generic templates."""
    slug = (j.get("slug") or path.stem).lower()
    pq = (j.get("primary_question") or "").lower()
    score = path.stat().st_mtime
    if "-common-mistakes" in slug or "common mistakes" in pq:
        score -= 1e12
    if "not-turn-out-right" in slug or "not turn out right" in pq:
        score -= 1e11
    if j.get("capability_id"):
        score += 1000
    if (j.get("humanized") or {}).get("related_problems"):
        score += 500
    return (score, path.stat().st_mtime)


def main() -> int:
    by_recipe: dict[str, list[Path]] = {}
    for p in DATA.glob("*.blog.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        rid = j.get("recipe_id")
        if not rid:
            continue
        by_recipe.setdefault(rid, []).append(p)

    removed = []
    kept: dict[str, Path] = {}
    for rid, paths in by_recipe.items():
        scored = []
        for p in paths:
            j = json.loads(p.read_text(encoding="utf-8"))
            scored.append((score_blog_file(p, j), p))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        kept[rid] = best
        for _, p in scored[1:]:
            p.unlink()
            removed.append(p.name)

    posts = []
    for rid, p in sorted(kept.items(), key=lambda x: x[1].stat().st_mtime, reverse=True):
        j = json.loads(p.read_text(encoding="utf-8"))
        H = j.get("humanized") or {}
        slug = j.get("slug") or p.stem.replace(".blog", "")
        posts.append(
            {
                "slug": slug,
                "title": j.get("primary_question") or H.get("primary_question") or slug,
                "hook": H.get("hook"),
                "cuisine": "",
                "meal": "",
                "image_url": "",
                "data_file": f"./data/{p.name}",
                "recipe_id": rid,
                "status": j.get("status") or "ready",
            }
        )

    # Enrich from existing index image/cuisine where recipe_id matches
    idx_path = DATA / "posts-index.json"
    old = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    old_by_rid = {p.get("recipe_id"): p for p in old.get("posts") or [] if p.get("recipe_id")}
    for p in posts:
        prev = old_by_rid.get(p["recipe_id"]) or {}
        p["cuisine"] = prev.get("cuisine") or p["cuisine"]
        p["meal"] = prev.get("meal") or p["meal"]
        p["image_url"] = prev.get("image_url") or p["image_url"]

    idx = {
        "site": {
            "brand": "SattvaSrsti",
            "tagline": "Real cooking problems. Useful answers. Full recipes on SattvaSrsti.",
            "purpose": "cooking_help",
        },
        "posts": posts,
    }
    idx_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Kept {len(kept)} posts, removed {len(removed)} stale files")
    for name in removed:
        print(f"  - {name}")
    print(f"INDEX {idx_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
