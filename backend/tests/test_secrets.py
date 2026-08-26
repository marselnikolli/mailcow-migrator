"""Tests for secret-at-rest encryption."""

from app.core.secrets import SecretEncryptor


def test_round_trip():
    secrets = SecretEncryptor()
    token = secrets.encrypt("NpTzUK-5Gyhng-=G8i")
    assert token != "NpTzUK-5Gyhng-=G8i"
    assert secrets.is_encrypted(token)
    assert secrets.decrypt(token) == "NpTzUK-5Gyhng-=G8i"


def test_empty_values_are_noops():
    secrets = SecretEncryptor()
    assert secrets.encrypt("") == ""
    assert secrets.decrypt("") == ""


def test_legacy_plaintext_passthrough():
    secrets = SecretEncryptor()
    assert not secrets.is_encrypted("plaintext-password")
    assert secrets.decrypt("plaintext-password") == "plaintext-password"


def test_encryption_differs_per_value():
    secrets = SecretEncryptor()
    a = secrets.encrypt("same")
    b = secrets.encrypt("same")
    # Fernet is randomized (GCM nonce), so tokens differ but both decrypt.
    assert a != b
    assert secrets.decrypt(a) == secrets.decrypt(b) == "same"


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("SECRETS_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    try:
        SecretEncryptor(key="")
        assert False, "expected RuntimeError for empty key"
    except RuntimeError:
        pass
