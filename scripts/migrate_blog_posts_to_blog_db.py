#!/usr/bin/env python3
"""Copy blog_posts from (default) → named blog database (one-time migration)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_blog_pipeline import BLOG_DATABASE_ID, PROJECT_ID, _resolve_service_account_path  # noqa: E402


def main() -> int:
    sa_path = _resolve_service_account_path()
    if not sa_path:
        print("Need GOOGLE_APPLICATION_CREDENTIALS or FIREBASE_SERVICE_ACCOUNT for Admin SDK.")
        return 1

    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(sa_path))
        firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})

    default_db = firestore.client()
    blog_db = firestore.client(database_id=BLOG_DATABASE_ID)

    src = default_db.collection("blog_posts").stream()
    copied = 0
    skipped = 0
    for doc in src:
        data = doc.to_dict() or {}
        dest = blog_db.collection("blog_posts").document(doc.id)
        if dest.get().exists:
            skipped += 1
            continue
        dest.set(data, merge=True)
        copied += 1
        print(f"  copied {doc.id}")

    print(f"Done: copied={copied} skipped_existing={skipped} target_db={BLOG_DATABASE_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
