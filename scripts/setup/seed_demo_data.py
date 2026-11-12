#!/usr/bin/env python3
"""Load the synthetic demo register (20 beneficiaries, 24 visits, follow-ups and referrals) into the
real database. Idempotent: running it twice creates nothing new. Every seeded record has
source="seed" and payload demo_data=true, so it is labelled DEMO DATA in the app and in CSV exports
and is never mixed with visits recorded through the voice flow.

  python scripts/setup/seed_demo_data.py            # add any missing seeded visits
  python scripts/setup/seed_demo_data.py --reset    # remove seeded visits only, then recreate them
                                                    # with dates relative to today

The server also seeds on start-up unless ASHA_SEED_DEMO=0."""
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))
os.environ["ASHA_NO_AUTOAPP"] = "1"
from app.config import BACKEND_DIR, get_settings  # noqa: E402
from app.storage.crypto import load_cipher  # noqa: E402
from app.storage.db import Database  # noqa: E402
from app.storage.demo_seed import seed_demo_visits  # noqa: E402

s = get_settings()
db = Database(s.db_path, load_cipher(s.data_key_b64, s.env, BACKEND_DIR / "data" / ".dev_data_key"))
db.seed_beneficiaries()
today = datetime.now(ZoneInfo(s.timezone)).date()
result = seed_demo_visits(db, today, reset="--reset" in sys.argv)
print(f"seeded demo data for {today}: {result}")
