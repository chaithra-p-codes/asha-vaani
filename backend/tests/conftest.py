import asyncio
import base64
import os
import sys
from pathlib import Path

import pytest

os.environ["ASHA_NO_AUTOAPP"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import reset_settings_for_tests  # noqa: E402
from app.main import create_app  # noqa: E402
from fakes import FakePrisma, FakeTimbre  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    return reset_settings_for_tests(
        env="test", db_path=str(tmp_path / "test.db"), tts_cache_dir=str(tmp_path / "tts"),
        gnani_api_key="test-primary-key-not-real", gemini_api_key="", llm_provider="none",
        data_key_b64=base64.b64encode(b"k" * 32).decode(),
        endpoint_silence_dictation_ms=250, endpoint_silence_short_ms=200, listen_idle_timeout_s=3.0,
        ack_filler=False, frontend_dist=str(tmp_path / "nofrontend"), seed_demo=False)


def make_app(settings, prisma=None, timbre=None):
    prisma = prisma or FakePrisma()
    timbre = timbre or FakeTimbre()
    app = create_app(settings, stt_connect=prisma.connect, tts_connect=timbre.connect)
    return app, prisma, timbre


def run(coro):
    return asyncio.run(coro)
