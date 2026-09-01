#!/usr/bin/env python3
"""
Upload deploy/public to Hostinger via FTP.

Requires .env:
  FTP_HOST=ftp.yourhost.com
  FTP_USER=...
  FTP_PASSWORD=...
  FTP_REMOTE_DIR=/public_html
"""
from __future__ import annotations

import os
import sys
from ftplib import FTP, error_perm
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def ensure_dir(ftp: FTP, path: str) -> None:
    parts = [p for p in path.strip("/").split("/") if p]
    cur = ""
    for p in parts:
        cur = f"{cur}/{p}"
        try:
            ftp.mkd(cur)
        except error_perm:
            pass


def upload_tree(ftp: FTP, local: Path, remote: str) -> int:
    count = 0
    ensure_dir(ftp, remote)
    for root, _dirs, files in os.walk(local):
        rel = Path(root).relative_to(local).as_posix()
        rdir = remote if rel == "." else f"{remote.rstrip('/')}/{rel}"
        ensure_dir(ftp, rdir)
        for name in files:
            lp = Path(root) / name
            rp = f"{rdir.rstrip('/')}/{name}"
            with lp.open("rb") as f:
                ftp.storbinary(f"STOR {rp}", f)
            print("UP", rp)
            count += 1
    return count


def main() -> int:
    load_dotenv()
    host = os.environ.get("FTP_HOST")
    user = os.environ.get("FTP_USER")
    password = os.environ.get("FTP_PASSWORD")
    remote = os.environ.get("FTP_REMOTE_DIR", "/public_html")
    if not host or not user or not password:
        print("Missing FTP_HOST / FTP_USER / FTP_PASSWORD in .env")
        print("Create .env from .env.example, then re-run.")
        return 2
    local = ROOT / "deploy" / "public"
    if not local.exists():
        print("Run scripts/build_deploy.py first")
        return 3
    ftp = FTP(host, timeout=60)
    ftp.login(user, password)
    n = upload_tree(ftp, local, remote)
    ftp.quit()
    print(f"Uploaded {n} files to {remote}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
