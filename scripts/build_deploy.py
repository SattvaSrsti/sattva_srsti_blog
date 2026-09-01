#!/usr/bin/env python3
"""Copy preview/ → deploy/public/ for Hostinger static upload."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "preview"
DST = ROOT / "deploy" / "public"


def main() -> int:
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(
        SRC,
        DST,
        ignore=shutil.ignore_patterns(
            "data",
            "*-report.json",
            "last-pipeline-run.json",
            "batch-*.json",
            "*.llm-context.json",
            "*.api-report.json",
            "*.live.json",
        ),
    )
    # Root .htaccess for Hostinger (optional pretty routing not required)
    (DST / ".htaccess").write_text(
        "Options -Indexes\n"
        "DirectoryIndex index.html\n"
        "<IfModule mod_headers.c>\n"
        "  Header set X-Content-Type-Options nosniff\n"
        "</IfModule>\n",
        encoding="utf-8",
    )
    print(f"Built {DST}")
    print("Deploy: npx firebase-tools deploy --only hosting:blog --project sattva-srsti")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
