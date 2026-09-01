#!/usr/bin/env python3
"""
SattvaSrsti Blog Agent — single entrypoint for the research-first pipeline.

Flow:
  recipes_v2 → duplicate check → research → slim context → OpenAI → blog_posts

Usage:
  python scripts/blog_agent.py --recipe-id rec_mysore_masala_dosa
  python scripts/blog_agent.py --recipe-id rec_mysore_masala_dosa --force --from-seed
  python scripts/blog_agent.py --batch --limit 10
  python scripts/blog_agent.py --reconcile --cleanup-duplicates --sync-firestore
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="SattvaSrsti research-first blog agent")
    ap.add_argument("--recipe-id", default="", help="Single recipe id (e.g. rec_mysore_masala_dosa)")
    ap.add_argument("--batch", action="store_true", help="Run batch_first_n_blogs.py")
    ap.add_argument("--reconcile", action="store_true", help="Daily reconcile recipes_v2 vs blog_posts")
    ap.add_argument("--sync-firestore", action="store_true", help="With --reconcile: push local blogs to Firestore")
    ap.add_argument("--cleanup-duplicates", action="store_true", help="With --reconcile: delete duplicate blog_posts")
    ap.add_argument("--dry-run", action="store_true", help="With --reconcile: report only")
    ap.add_argument("--max-create", type=int, default=0, help="With --reconcile: cap new posts per run")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--from-seed", action="store_true")
    ap.add_argument("--refresh-research", action="store_true")
    ap.add_argument("--skip-write", action="store_true")
    ap.add_argument("--from-local-blog", action="store_true")
    args = ap.parse_args()

    if args.reconcile:
        cmd = [sys.executable, str(ROOT / "scripts" / "reconcile_blog_posts.py")]
        if args.dry_run:
            cmd.append("--dry-run")
        if args.cleanup_duplicates:
            cmd.append("--cleanup-duplicates")
        if args.sync_firestore:
            cmd.append("--sync-firestore")
        if args.skip_write:
            cmd.append("--skip-write")
        if args.max_create:
            cmd.extend(["--max-create", str(args.max_create)])
    elif args.batch:
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "batch_first_n_blogs.py"),
            "--limit",
            str(args.limit),
        ]
        if args.force:
            cmd.append("--force")
        if args.from_seed:
            cmd.append("--from-seed")
        if args.refresh_research:
            cmd.append("--refresh-research")
        if args.skip_write:
            cmd.append("--skip-write")
    else:
        if not args.recipe_id:
            ap.error("--recipe-id is required unless --batch or --reconcile")
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_blog_pipeline.py"),
            "--recipe-id",
            args.recipe_id,
        ]
        if args.force:
            cmd.append("--force")
        if args.from_seed:
            cmd.append("--from-seed")
        if args.refresh_research:
            cmd.append("--refresh-research")
        if args.skip_write:
            cmd.append("--skip-write")
        if args.from_local_blog:
            cmd.append("--from-local-blog")

    print("BLOG AGENT:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
