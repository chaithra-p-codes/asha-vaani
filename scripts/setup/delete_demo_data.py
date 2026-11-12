#!/usr/bin/env python3
"""Delete all visits, follow-ups, sessions, audit events, metrics and usage rows, plus the
TTS prompt cache. Run after judging (DPDP: demo transcripts must be deleted)."""
import os
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))
os.environ["ASHA_NO_AUTOAPP"] = "1"
from app.config import BACKEND_DIR, get_settings  # noqa: E402
from app.storage.crypto import load_cipher  # noqa: E402
from app.storage.db import Database  # noqa: E402

if "--yes" not in sys.argv:
    sys.exit("This permanently deletes demo data. Re-run with --yes to confirm.")
s = get_settings()
db = Database(s.db_path, load_cipher(s.data_key_b64, s.env, BACKEND_DIR / "data" / ".dev_data_key"))
print("deleted:", db.delete_all_demo_data())
if Path(s.tts_cache_dir).exists():
    shutil.rmtree(s.tts_cache_dir)
    print("deleted TTS cache")
