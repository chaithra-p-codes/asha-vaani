#!/usr/bin/env python3
"""Fail if anything that looks like a credential, a .env file or real data is in the repo."""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "data"}
PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "Google/Gemini API key"),
    (re.compile(r"(?i)(gnani|gemini|api)[_-]?key\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}"), "assigned API key"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "secret key"),
    (re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"ASHA_DATA_KEY=[A-Za-z0-9+/]{40,}={0,2}"), "data encryption key"),
]
problems = []
for p in root.rglob("*"):
    if any(part in SKIP_DIRS for part in p.parts) or not p.is_file():
        continue
    if p.name == ".env" or p.name.endswith(".env") or p.suffix in (".db", ".pcm") or p.name == ".dev_data_key":
        problems.append(f"{p.relative_to(root)}: secret/data file must not be shipped")
        continue
    if p.suffix in (".png", ".jpg", ".wav", ".zip", ".pptx", ".pdf", ".ico"):
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for rx, what in PATTERNS:
        for m in rx.finditer(text):
            g = m.group(0).lower()
            if "test" in g or "your" in g or "example" in g or "not-real" in text[m.start():m.end() + 20]:
                continue
            problems.append(f"{p.relative_to(root)}: possible {what}")
print("\n".join(problems) if problems else "OK: no secrets, .env files or databases found")
sys.exit(1 if problems else 0)
