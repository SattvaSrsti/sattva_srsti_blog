#!/usr/bin/env python3
"""
Daily reconcile: recipes_v2 vs blog_posts (flat collection, matched by recipe_id).

1) Paginate all recipes_v2 and blog_posts (no subcollections on blog_posts)
2) Optionally delete duplicate / stale Firestore blog docs per recipe_id
3) Generate blog posts only for eligible recipes with no ready blog
4) Rebuild posts-index + optional sync local → Firestore

Usage:
  python scripts/reconcile_blog_posts.py --dry-run
  python scripts/reconcile_blog_posts.py --cleanup-duplicates --sync-firestore
  python scripts/reconcile_blog_posts.py --max-create 3
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_blog_pipeline import (  # noqa: E402
    best_blog_for_recipe,
    delete_blog_post_only,
    eligibility,
    fetch_recipe_bundle,
    find_existing_blog_for_recipe,
    list_blog_posts_by_recipe,
    list_recipe_ids,
)


def run_pipeline(recipe_id: str, *, skip_write: bool) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_blog_pipeline.py"),
        "--recipe-id",
        recipe_id,
        "--refresh-research",
    ]
    if skip_write:
        cmd.append("--skip-write")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return {
        "recipe_id": recipe_id,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-800:],
    }


def cleanup_firestore_duplicates(*, dry_run: bool) -> list[str]:
    """Keep best blog_posts doc per recipe_id; delete the rest."""
    try:
        by_recipe = list_blog_posts_by_recipe()
    except Exception as e:
        print(f"  SKIP cleanup (cannot list blog_posts): {e}")
        return []
    deleted: list[str] = []
    for rid, posts in by_recipe.items():
        if len(posts) <= 1:
            continue
        keeper = best_blog_for_recipe(posts)
        if not keeper:
            continue
        keep_id = keeper["blog_id"]
        for p in posts:
            bid = p["blog_id"]
            if bid == keep_id:
                continue
            deleted.append(bid)
            print(f"  DELETE duplicate {bid} (recipe {rid}, kept {keep_id})")
            if not dry_run:
                try:
                    delete_blog_post_only(bid)
                except Exception as e:
                    print(f"    WARN delete failed: {e}")
    return deleted


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile recipes_v2 with blog_posts")
    ap.add_argument("--dry-run", action="store_true", help="Report only; no writes or pipeline")
    ap.add_argument("--cleanup-duplicates", action="store_true", help="Delete extra Firestore blog_posts per recipe_id")
    ap.add_argument("--max-create", type=int, default=0, help="Cap new posts per run (0 = no cap)")
    ap.add_argument("--skip-write", action="store_true", help="Pipeline without Firestore write")
    ap.add_argument("--sync-firestore", action="store_true", help="After reconcile, push local *.blog.json to Firestore")
    ap.add_argument("--rebuild-index", action="store_true", default=True)
    ap.add_argument("--no-rebuild-index", action="store_false", dest="rebuild_index")
    args = ap.parse_args()

    print(f"[reconcile] {datetime.now(timezone.utc).isoformat()}")

    recipe_ids = list_recipe_ids()
    print(f"recipes_v2: {len(recipe_ids)} documents")

    try:
        by_recipe = list_blog_posts_by_recipe()
        blog_doc_count = sum(len(v) for v in by_recipe.values())
        print(f"blog_posts: {blog_doc_count} documents, {len(by_recipe)} recipe_ids with at least one post")
    except Exception as e:
        print(f"WARN could not list blog_posts: {e}")
        by_recipe = {}

    deleted: list[str] = []
    if args.cleanup_duplicates:
        print("[cleanup] duplicate blog_posts per recipe_id …")
        deleted = cleanup_firestore_duplicates(dry_run=args.dry_run)
        print(f"  duplicates targeted: {len(deleted)}")

    missing: list[str] = []
    skipped_ineligible: list[tuple[str, str]] = []
    has_blog: list[str] = []

    for rid in sorted(recipe_ids):
        try:
            bundle = fetch_recipe_bundle(rid)
        except Exception as e:
            skipped_ineligible.append((rid, f"read_fail:{e}"))
            continue
        ok, reason = eligibility(bundle)
        if not ok:
            skipped_ineligible.append((rid, reason))
            continue
        existing = find_existing_blog_for_recipe(rid)
        if existing:
            has_blog.append(rid)
            continue
        missing.append(rid)

    print(f"eligible with blog: {len(has_blog)}")
    print(f"eligible missing blog: {len(missing)}")
    print(f"ineligible/skipped: {len(skipped_ineligible)}")

    if missing:
        print("missing recipe_ids:")
        for rid in missing:
            print(f"  - {rid}")

    created: list[dict] = []
    failed: list[dict] = []

    if not args.dry_run and missing:
        to_create = missing
        if args.max_create > 0:
            to_create = missing[: args.max_create]
        print(f"[create] running pipeline for {len(to_create)} recipe(s) …")
        for rid in to_create:
            print(f"\n=== {rid} ===")
            outcome = run_pipeline(rid, skip_write=args.skip_write)
            (created if outcome["ok"] else failed).append(outcome)
            if not outcome["ok"]:
                print(f"  FAIL exit={outcome['exit_code']}")
            else:
                print("  OK")

    if args.rebuild_index and not args.dry_run:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "rebuild_posts_index.py")],
            cwd=str(ROOT),
            check=False,
        )

    if args.sync_firestore and not args.dry_run:
        print("[sync] local blog JSON → Firestore …")
        sync = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sync_blog_posts_to_firestore.py")],
            cwd=str(ROOT),
        )
        if sync.returncode != 0:
            print("WARN Firestore sync had failures (check GOOGLE_APPLICATION_CREDENTIALS)")

    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "recipes_v2_count": len(recipe_ids),
        "blog_posts_recipe_ids": len(by_recipe),
        "has_blog": has_blog,
        "missing": missing,
        "created_ok": [c["recipe_id"] for c in created],
        "created_fail": [f["recipe_id"] for f in failed],
        "duplicates_deleted": deleted,
        "dry_run": args.dry_run,
    }
    out = ROOT / "preview" / "data" / "reconcile-report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nREPORT {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
