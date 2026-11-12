#!/usr/bin/env python3
"""Build ASHA_VAANI_HACKATHON_READY.zip from this repo, excluding secrets, databases,
virtualenvs, node_modules and caches. Usage: python scripts/package_zip.py [output.zip]"""
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1]) if len(sys.argv) > 1 else root.parent / "ASHA_VAANI_HACKATHON_READY.zip"
EXCLUDE_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".git", "data"}
EXCLUDE_FILES = {".env", ".dev_data_key", "out_timbre.wav"}
n = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in EXCLUDE_DIRS for part in rel.parts) or not p.is_file():
            continue
        if p.name in EXCLUDE_FILES or p.suffix in (".db", ".pyc", ".pcm") or p.name.startswith("results_live"):
            continue
        z.write(p, Path("asha-vaani") / rel)
        n += 1
print(f"wrote {out} ({n} files, {out.stat().st_size / 1e6:.1f} MB)")
