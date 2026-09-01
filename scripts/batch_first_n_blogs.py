#!/usr/bin/env python3
"""
Batch: first N recipes_v2 → research → OpenAI → blog_posts.

Skips recipe_id that already has a ready/published blog_posts doc unless --force.
Does not regenerate posts by default when a ready blog exists.

Usage:
  python scripts/batch_first_n_blogs.py --limit 10
  python scripts/batch_first_n_blogs.py --limit 1 --force --from-seed
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_blog_pipeline import (  # noqa: E402
    eligibility,
    fetch_recipe_bundle,
    find_existing_blog_for_recipe,
    FS_BASE,
    list_recipe_ids,
)


def list_recipe_ids_limited(limit: int) -> list[str]:
    ids = list_recipe_ids()
    return ids[:limit] if limit else ids


def run_one(recipe_id: str, *, force: bool, from_seed: bool, skip_write: bool, refresh_research: bool) -> dict:
    cmd = [sys.executable, str(ROOT / "scripts" / "run_blog_pipeline.py"), "--recipe-id", recipe_id]
    if force:
        cmd.append("--force")
    if from_seed:
        cmd.append("--from-seed")
    if skip_write:
        cmd.append("--skip-write")
    if refresh_research:
        cmd.append("--refresh-research")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return {
        "recipe_id": recipe_id,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--force", action="store_true", help="Regenerate even if ready blog exists")
    ap.add_argument("--from-seed", action="store_true")
    ap.add_argument("--refresh-research", action="store_true")
    ap.add_argument("--skip-write", action="store_true")
    ap.add_argument("--recipe-ids", nargs="*", default=None, help="Optional explicit recipe ids")
    args = ap.parse_args()

    ids = args.recipe_ids or list_recipe_ids_limited(args.limit)
    print(f"Found {len(ids)} recipes: {ids}")

    posts_index = {
        "site": {
            "brand": "SattvaSrsti",
            "tagline": "Real cooking problems. Useful answers. Full recipes on SattvaSrsti.",
            "purpose": "cooking_help",
        },
        "posts": [],
    }
    # Keep any existing index entries for recipes we skip
    idx_path = ROOT / "preview" / "data" / "posts-index.json"
    existing_by_recipe: dict[str, dict] = {}
    if idx_path.exists():
        try:
            old = json.loads(idx_path.read_text(encoding="utf-8"))
            for p in old.get("posts") or []:
                if p.get("recipe_id"):
                    existing_by_recipe[p["recipe_id"]] = p
        except Exception:
            pass

    results = []

    for rid in ids:
        print(f"\n=== {rid} ===")
        try:
            bundle = fetch_recipe_bundle(rid)
        except Exception as e:
            print(f"  READ_FAIL {e}")
            results.append({"recipe_id": rid, "ok": False, "error": str(e)})
            continue

        ok, reason = eligibility(bundle)
        if not ok:
            print(f"  SKIP eligibility: {reason}")
            results.append({"recipe_id": rid, "ok": False, "skip": reason})
            continue

        existing = find_existing_blog_for_recipe(rid)
        if existing and not args.force:
            print(f"  SKIP duplicate: already has blog {existing}")
            if rid in existing_by_recipe:
                posts_index["posts"].append(existing_by_recipe[rid])
            results.append({"recipe_id": rid, "ok": True, "skipped_duplicate": existing})
            continue

        outcome = run_one(
            rid,
            force=args.force or bool(existing),
            from_seed=args.from_seed,
            skip_write=args.skip_write,
            refresh_research=args.refresh_research,
        )
        results.append(outcome)
        if not outcome["ok"]:
            print(f"  FAIL exit={outcome['exit_code']}")
            if outcome.get("stderr_tail"):
                print(outcome["stderr_tail"][-500:])
            continue

        # Pick up freshly written local blog for index (newest file wins)
        data_dir = ROOT / "preview" / "data"
        card = None
        candidates = []
        for p in data_dir.glob("*.blog.json"):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if j.get("recipe_id") != rid:
                continue
            candidates.append((p.stat().st_mtime, p, j))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            _, p, j = candidates[0]
            H = j.get("humanized") or {}
            root = bundle["root"]
            card = {
                "slug": j.get("slug"),
                "title": j.get("primary_question") or H.get("primary_question"),
                "hook": H.get("hook"),
                "cuisine": root.get("cuisine") or "",
                "meal": root.get("meal_type") or "",
                "image_url": root.get("image_primary_url") or "",
                "data_file": f"./data/{j.get('slug')}.blog.json",
                "recipe_id": rid,
                "status": j.get("status") or "ready",
            }
        if card:
            posts_index["posts"].append(card)
            print(f"  OK slug={card['slug']}")

    # Preserve posts for recipes not in this batch
    seen = {p.get("recipe_id") for p in posts_index["posts"]}
    for rid, card in existing_by_recipe.items():
        if rid not in seen:
            posts_index["posts"].append(card)

    idx_path.write_text(json.dumps(posts_index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path = ROOT / "preview" / "data" / "batch-first-10-report.json"
    report_path.write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")
    print(f"\nINDEX {idx_path} posts={len(posts_index['posts'])}")
    print(f"REPORT {report_path}")
    print(f"(FS_BASE={FS_BASE})")
    return 0 if any(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
