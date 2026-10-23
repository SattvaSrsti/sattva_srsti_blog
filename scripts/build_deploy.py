#!/usr/bin/env python3
"""Copy preview/ → deploy/public/ for Firebase Hosting; inject SEO crawl surfaces."""
from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "preview"
DST = ROOT / "deploy" / "public"
SITE = "https://sattvasrsti.blog"
POSTS_INDEX = SRC / "data" / "posts-index.json"


def load_posts() -> list[dict]:
    if not POSTS_INDEX.exists():
        return []
    idx = json.loads(POSTS_INDEX.read_text(encoding="utf-8"))
    posts = [p for p in (idx.get("posts") or []) if p.get("slug")]
    posts.sort(key=lambda p: str(p.get("title") or p.get("slug")).lower())
    return posts


def write_sitemap(dest: Path, posts: list[dict]) -> None:
    slugs = [str(p["slug"]) for p in posts]
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
    (SRC / "sitemap.xml").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Sitemap {len(urls)} URLs")


def build_seo_head(posts: list[dict]) -> str:
    item_elements = []
    for i, p in enumerate(posts, start=1):
        slug = str(p["slug"])
        item_elements.append(
            {
                "@type": "ListItem",
                "position": i,
                "url": f"{SITE}/{slug}",
                "name": str(p.get("title") or slug),
            }
        )
    item_list_json = json.dumps(item_elements, ensure_ascii=False)
    return f"""  <link rel="canonical" href="{SITE}/" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="SattvaSrsti Blog" />
  <meta property="og:title" content="SattvaSrsti Blog — cooking answers that help" />
  <meta property="og:description" content="Clear answers to real cooking problems, tied to live SattvaSrsti recipes." />
  <meta property="og:url" content="{SITE}/" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="SattvaSrsti Blog — cooking answers that help" />
  <meta name="twitter:description" content="Clear answers to real cooking problems, tied to live SattvaSrsti recipes." />
  <link rel="sitemap" type="application/xml" href="/sitemap.xml" title="Sitemap" />
  <script type="application/ld+json">{{
    "@context": "https://schema.org",
    "@type": "WebSite",
    "name": "SattvaSrsti Blog",
    "url": "{SITE}/",
    "description": "Problem-led cooking articles powered by SattvaSrsti recipes.",
    "potentialAction": {{
      "@type": "SearchAction",
      "target": "{SITE}/?q={{search_term_string}}",
      "query-input": "required name=search_term_string"
    }}
  }}</script>
  <script type="application/ld+json">{{
    "@context": "https://schema.org",
    "@type": "ItemList",
    "name": "All cooking answers",
    "numberOfItems": {len(posts)},
    "itemListElement": {item_list_json}
  }}</script>"""


def build_crawl_index(posts: list[dict]) -> str:
    lis = []
    noscript_lis = []
    for p in posts:
        slug = escape(str(p["slug"]), quote=True)
        title = escape(str(p.get("title") or p["slug"]))
        meta_bits = [escape(str(x)) for x in (p.get("cuisine"), p.get("meal")) if x]
        meta = " · ".join(meta_bits)
        meta_html = f'<span class="crawl-meta">{meta}</span>' if meta else ""
        lis.append(f'        <li><a href="/{slug}">{title}</a>{meta_html}</li>')
        noscript_lis.append(f'      <li><a href="/{slug}">{title}</a></li>')
    list_html = "\n".join(lis)
    noscript_html = "\n".join(noscript_lis)
    n = len(posts)
    return f"""      <nav class="crawl-index" id="crawl-index" aria-label="All blog articles">
        <h3>All articles ({n})</h3>
        <p class="crawl-index-note">Problem-led cooking help — full list for search and discovery. Interactive grid loads above when JavaScript is enabled.</p>
        <ul class="crawl-index-list">
{list_html}
        </ul>
      </nav>
      <noscript>
        <section class="crawl-index" aria-label="Article links">
          <h3>All articles</h3>
          <ul>
{noscript_html}
          </ul>
        </section>
      </noscript>"""


def patch_index_html(index_path: Path, posts: list[dict]) -> None:
    html = index_path.read_text(encoding="utf-8")
    seo = build_seo_head(posts)
    crawl = build_crawl_index(posts)
    if "<!-- inject:seo-head -->" not in html or "<!-- inject:crawl-index -->" not in html:
        raise RuntimeError("index.html missing SEO inject markers")
    html = html.replace("<!-- inject:seo-head -->", seo, 1)
    html = html.replace("<!-- inject:crawl-index -->", crawl, 1)
    index_path.write_text(html, encoding="utf-8")
    print(f"index.html SEO inject: {len(posts)} posts")


def write_posts_index_public(dest: Path, posts: list[dict]) -> None:
    payload = {
        "site": SITE,
        "generated_for": "crawlers_and_agents",
        "count": len(posts),
        "posts": [
            {
                "slug": p.get("slug"),
                "title": p.get("title"),
                "url": f"{SITE}/{p.get('slug')}",
                "recipe_id": p.get("recipe_id"),
                "cuisine": p.get("cuisine"),
                "meal": p.get("meal"),
            }
            for p in posts
        ],
    }
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"posts-index.json public ({len(posts)} posts)")


def write_llms_txt(dest: Path, posts: list[dict]) -> None:
    lines = [
        "# SattvaSrsti Blog",
        "",
        f"> {SITE} — problem-led cooking answers tied to SattvaSrsti recipes.",
        "",
        "## Discovery",
        f"- Sitemap: {SITE}/sitemap.xml",
        f"- Machine-readable index: {SITE}/posts-index.json",
        "",
        "## Articles",
    ]
    for p in posts:
        slug = p.get("slug")
        title = p.get("title") or slug
        lines.append(f"- [{title}]({SITE}/{slug})")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"llms.txt ({len(posts)} links)")


def main() -> int:
    posts = load_posts()
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
    write_sitemap(DST / "sitemap.xml", posts)
    patch_index_html(DST / "index.html", posts)
    write_posts_index_public(DST / "posts-index.json", posts)
    write_llms_txt(DST / "llms.txt", posts)
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
