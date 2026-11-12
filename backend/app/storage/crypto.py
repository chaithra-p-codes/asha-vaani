"""AES-256-GCM encryption for sensitive payloads at rest (visit records, transcripts,
follow-up text, session drafts). The key comes from ASHA_DATA_KEY (base64, 32 bytes) and
is kept outside the database. In ASHA_ENV=dev without a key, a local dev key file is
generated (and the app logs a warning) so a stranger can run the demo immediately."""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger("asha.crypto")


class Cipher:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("ASHA_DATA_KEY must decode to exactly 32 bytes")
        self._aead = AESGCM(key)

    def encrypt(self, obj, aad: bytes = b"asha-vaani-v1") -> bytes:
        nonce = os.urandom(12)
        data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return b"v1" + nonce + self._aead.encrypt(nonce, data, aad)

    def decrypt(self, blob: bytes, aad: bytes = b"asha-vaani-v1"):
        if not blob or blob[:2] != b"v1":
            raise ValueError("unknown ciphertext version")
        nonce, ct = blob[2:14], blob[14:]
        return json.loads(self._aead.decrypt(nonce, ct, aad).decode("utf-8"))


def load_cipher(key_b64: str, env: str, dev_key_path: Path) -> Cipher:
    if key_b64:
        return Cipher(base64.b64decode(key_b64))
    if env not in ("dev", "test"):
        raise RuntimeError("ASHA_DATA_KEY is required outside dev/test. Run scripts/setup/generate_keys.py")
    dev_key_path.parent.mkdir(parents=True, exist_ok=True)
    if dev_key_path.exists():
        key = base64.b64decode(dev_key_path.read_text().strip())
    else:
        key = AESGCM.generate_key(bit_length=256)
        dev_key_path.write_text(base64.b64encode(key).decode())
        try:
            os.chmod(dev_key_path, 0o600)
        except OSError:
            pass
        log.warning("ASHA_DATA_KEY not set: generated a DEV key at %s (do not use for real data)", dev_key_path)
    return Cipher(key)
