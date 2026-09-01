#!/usr/bin/env python3
"""One slim humanize call for Aloo Paratha blog. Reads OPENAI_API_KEY from env."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CTX_PATH = ROOT / "preview" / "data" / "aloo-paratha.llm-context.json"
OUT_PATH = ROOT / "preview" / "data" / "aloo-paratha.humanized.json"
REPORT_PATH = ROOT / "preview" / "data" / "aloo-paratha.api-report.json"

SYSTEM = """You write a short human blog story for SattvaSrsti home cooks.

You receive: recipe title, meal filters, ONE primary_question, candidate_questions, mistake_warnings, and optional sensory_cues.

RULES:
1. Write only human prose. Do not invent ingredient amounts, base ratios, full recipes, or cooking steps.
2. Center the primary_question. Use mistake_warnings as the real causes/fixes.
3. Produce 5 common_questions from candidate_questions + warnings; answers must stay faithful to the warnings/cues given.
4. Keep voice specific and plain. No purple prose. No SEO stuffing.
5. Optionally, once, say that SattvaSrsti AI can help customize ingredients and steps — natural, not salesy.
6. Do not output ingredients lists, base_ratio / quantity dumps, hashtags, or full cooking methods.
7. Output VALID JSON only with keys:
primary_question, hook, story (array of 2-3 short strings), useful_answer (string),
common_questions (array of {q,a} length 5), customize_mention (string|null),
emotional_ending (string), meta_description (string max 155 chars).
"""


def main() -> int:
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_KEY")
    if not key:
        print("NO_API_KEY", file=sys.stderr)
        return 2

    ctx = json.loads(CTX_PATH.read_text(encoding="utf-8"))
    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": json.dumps(ctx, ensure_ascii=False),
            },
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        REPORT_PATH.write_text(
            json.dumps({"ok": False, "status": e.code, "error": err[:2000]}, indent=2),
            encoding="utf-8",
        )
        print(f"HTTP_ERROR {e.code}", file=sys.stderr)
        return 1

    usage = raw.get("usage") or {}
    content = raw["choices"][0]["message"]["content"]
    humanized = json.loads(content)
    OUT_PATH.write_text(json.dumps(humanized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = {
        "ok": True,
        "model": body["model"],
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "context_path": str(CTX_PATH),
        "output_path": str(OUT_PATH),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
