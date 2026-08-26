"""Encryption of secrets at rest (mailbox passwords, Mailcow API keys).

Secrets are stored encrypted in both the SQLite database and the Redis job
queue, and decrypted only inside the worker right before they are handed to
imapsync / the DAV sync. The key is derived from SECRET_KEY (or a dedicated
SECRETS_KEY if set) using SHA-256 so no extra secret management is required.
"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

# Fernet tokens always start with this prefix; used to distinguish ciphertext
# from legacy plaintext rows during backfill.
_FERNET_PREFIX = "gAAAAA"


class SecretEncryptor:
    def __init__(self, key: str = None):
        key = key or os.getenv("SECRETS_KEY", "") or os.getenv("SECRET_KEY", "")
        if not key:
            raise RuntimeError(
                "SECRET_KEY (or SECRETS_KEY) must be set to encrypt stored secrets"
            )
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        if not token:
            return ""
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            # Not encrypted (legacy plaintext) - return as-is.
            return token

    @staticmethod
    def is_encrypted(value: str) -> bool:
        return bool(value) and value.startswith(_FERNET_PREFIX)
