#!/usr/bin/env python3
"""Create backend/.env from .env.example (if missing) and fill ASHA_DATA_KEY with a fresh
random AES-256 key. Never prints secrets. Re-running keeps an existing key."""
import base64
import os
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
env = root / "backend" / ".env"
if not env.exists():
    env.write_text((root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    print("created backend/.env from .env.example")
text = env.read_text(encoding="utf-8")
if re.search(r"^ASHA_DATA_KEY=\S+", text, re.M):
    print("ASHA_DATA_KEY already set (kept)")
else:
    key = base64.b64encode(os.urandom(32)).decode()
    text = re.sub(r"^ASHA_DATA_KEY=.*$", f"ASHA_DATA_KEY={key}", text, flags=re.M)
    env.write_text(text, encoding="utf-8")
    print("generated ASHA_DATA_KEY")
try:
    os.chmod(env, 0o600)
except OSError:
    pass
missing = [k for k in ("GNANI_API_KEY",) if not re.search(rf"^{k}=\S+", text, re.M)]
if missing:
    print("NEXT: open backend/.env and paste your Gnani API key into GNANI_API_KEY=")
