#!/usr/bin/env python3
"""Delete fat blog_posts doc and write blog-unique-only Aloo post."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_blog_pipeline import (  # noqa: E402
    CUSTOMIZE_FIXED,
    firestore_doc_from_page,
    load_local_blog_for_recipe,
    read_doc,
    write_blog_post_only,
)

BLOG_ID = "blog_aloo-paratha-dough-kept-tearing"
FS_DOC = (
    "https://firestore.googleapis.com/v1/projects/sattva-srsti/"
    f"databases/(default)/documents/blog_posts/{BLOG_ID}"
)


def main() -> int:
    page = load_local_blog_for_recipe("rec_aloo_paratha")
    if not page:
        print("No local blog")
        return 1

    slim = firestore_doc_from_page(page)
    print("SLIM_KEYS", sorted(slim.keys()))

    # hard delete
    req = urllib.request.Request(FS_DOC, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print("DELETED", r.status)
    except urllib.error.HTTPError as e:
        print("DELETE", e.code)

    path = write_blog_post_only(BLOG_ID, slim, replace=False)
    verify = read_doc(path)
    print("WRITTEN", path)
    print("VERIFY_KEYS", sorted(verify.keys()))
    print("FORBIDDEN_PRESENT", [k for k in (
        "base_ratio", "ingredient_groups", "preview_steps", "ayurveda", "nutrition",
        "related_recipes", "about_recipe", "hashtags", "page", "purpose",
        "image_url", "app_recipe_url", "pairings", "storage", "meta_pills",
    ) if k in verify])

    # local slim mirror for fallback
    local = ROOT / "preview" / "data" / f"{slim['slug']}.blog.json"
    local.write_text(json.dumps(slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # keep alias pointing at slim too (preview joins live recipe)
    (ROOT / "preview" / "data" / "aloo-paratha.blog.json").write_text(
        local.read_text(encoding="utf-8"), encoding="utf-8"
    )
    sample = ROOT / "firestore" / "samples" / f"{BLOG_ID}.json"
    sample.write_text(json.dumps(slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    idx_path = ROOT / "preview" / "data" / "posts-index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    for p in idx.get("posts", []):
        if p.get("slug") == slim["slug"]:
            p["data_file"] = f"./data/{slim['slug']}.blog.json"
            p["title"] = slim["primary_question"]
            p["hook"] = slim["humanized"]["hook"]
            p["recipe_id"] = slim["recipe_id"]
    idx_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("PREVIEW", f"http://127.0.0.1:8765/post.html?slug={slim['slug']}")
    print("LANDING", "http://127.0.0.1:8765/")
    print("customize_fixed_ok", slim.get("customize_fixed") == CUSTOMIZE_FIXED or bool(slim.get("customize_fixed")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
