#!/usr/bin/env python3
"""Push best local *.blog.json per recipe_id to Firestore blog_posts (requires auth)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rebuild_posts_index import score_blog_file  # noqa: E402
from run_blog_pipeline import (  # noqa: E402
    cleanup_superseded_blog,
    firestore_doc_from_page,
    read_doc,
    write_blog_post_only,
)


def best_local_blogs() -> dict[str, tuple[Path, dict]]:
    by_recipe: dict[str, list[tuple[Path, dict, tuple]]] = {}
    data_dir = ROOT / "preview" / "data"
    for p in data_dir.glob("*.blog.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        rid = j.get("recipe_id")
        if not rid:
            continue
        by_recipe.setdefault(rid, []).append((p, j, score_blog_file(p, j)))
    best: dict[str, tuple[Path, dict]] = {}
    for rid, items in by_recipe.items():
        items.sort(key=lambda x: x[2], reverse=True)
        best[rid] = (items[0][0], items[0][1])
    return best


def enrich_doc_from_recipe(doc: dict, recipe_id: str) -> dict:
    """Denormalize card fields onto blog_posts at sync time (homepage reads only)."""
    try:
        root = read_doc(f"recipes_v2/{recipe_id}")
        doc["image_url"] = root.get("image_primary_url") or ""
        doc["cuisine"] = root.get("cuisine") or ""
        doc["meal_type"] = root.get("meal_type") or ""
    except Exception as e:
        print(f"  warn: could not enrich {recipe_id}: {e}")
    return doc


def main() -> int:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "rebuild_posts_index.py")],
        cwd=str(ROOT),
        check=False,
    )

    ok = 0
    fail = 0
    for rid, (p, slim) in sorted(best_local_blogs().items()):
        blog_id = slim.get("blog_id")
        slug = slim.get("slug")
        if not blog_id or not rid:
            continue
        page = {
            **slim,
            "blog_post_id": blog_id,
            "humanized": {
                **(slim.get("humanized") or {}),
                "primary_question": slim.get("primary_question"),
            },
            "seo": {
                "title": slim.get("seo_title"),
                "meta_description": slim.get("meta_description"),
                "canonical_url": slim.get("blog_public_url"),
            },
        }
        doc = firestore_doc_from_page(page)
        doc = enrich_doc_from_recipe(doc, rid)
        try:
            cleanup_superseded_blog(rid, blog_id, slug)
            path = write_blog_post_only(blog_id, doc)
            verify = read_doc(path)
            print(f"OK {blog_id} ({p.name}) keys={len(verify)}")
            ok += 1
        except Exception as e:
            print(f"FAIL {blog_id}: {e}")
            fail += 1
    print(f"\nDone: {ok} written, {fail} failed")
    if fail:
        print("Set GOOGLE_APPLICATION_CREDENTIALS or FIREBASE_SERVICE_ACCOUNT in .env for writes.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
