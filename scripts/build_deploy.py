#!/usr/bin/env python3
"""Copy preview/ → deploy/public/ for Hostinger static upload."""
from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "preview"
DST = ROOT / "deploy" / "public"
SITE = "https://sattvasrsti.blog"


def write_sitemap(dest: Path) -> None:
    idx_path = SRC / "data" / "posts-index.json"
    slugs: list[str] = []
    if idx_path.exists():
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        for p in idx.get("posts") or []:
            slug = p.get("slug")
            if slug:
                slugs.append(str(slug))
    urls = [f"{SITE}/", f"{SITE}/index.html"]
    urls.extend(f"{SITE}/{escape(s, quote=True)}" for s in slugs)
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc in urls:
        body.append("  <url>")
        body.append(f"    <loc>{loc}</loc>")
        body.append("    <changefreq>weekly</changefreq>")
        body.append("  </url>")
    body.append("</urlset>")
    dest.write_text("\n".join(body) + "\n", encoding="utf-8")
    # Also keep a copy in preview so local http.server can serve it
    (SRC / "sitemap.xml").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Sitemap {len(urls)} URLs")

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
    write_sitemap(DST / "sitemap.xml")
    # Root .htaccess for Hostinger (optional pretty routing not required)
    (DST / ".htaccess").write_text(
        "Options -Indexes\n"
        "DirectoryIndex index.html\n"
        "<IfModule mod_headers.c>\n"
        "  Header set X-Content-Type-Options nosniff\n"
        "  Header set Content-Signal \"ai-train=no, search=yes, ai-input=no\"\n"
        "</IfModule>\n",
        encoding="utf-8",
    )
    print(f"Built {DST}")
    print("Deploy: npx firebase-tools deploy --only hosting:blog --project sattva-srsti")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
