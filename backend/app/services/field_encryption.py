"""
Field-level encryption for sensitive data at rest.

When DATA_ENCRYPTION_KEY is set (a valid Fernet key), sensitive fields
are encrypted before writing to the DB and decrypted when reading.
Do not log keys or plaintext.
"""

import json
from typing import Any, Dict, Optional

from app.config import get_settings


def _get_fernet():
    """Return Fernet instance if encryption key is configured, else None."""
    key = get_settings().data_encryption_key
    if not key or not key.strip():
        return None
    try:
        from cryptography.fernet import Fernet, InvalidToken
        return Fernet(key.strip().encode() if isinstance(key, str) else key)
    except Exception:
        return None


def encrypt_str(plain: str) -> str:
    """Encrypt a string; returns base64 ciphertext or original if encryption disabled."""
    f = _get_fernet()
    if f is None:
        return plain
    if not plain:
        return plain
    try:
        return f.encrypt(plain.encode("utf-8")).decode("ascii")
    except Exception:
        return plain


def decrypt_str(cipher: str) -> str:
    """Decrypt a string; returns plaintext or original if not encrypted / encryption disabled."""
    f = _get_fernet()
    if f is None or not cipher:
        return cipher
    try:
        return f.decrypt(cipher.encode("ascii")).decode("utf-8")
    except Exception:
        # Not encrypted or wrong key - return as-is for backward compatibility
        return cipher


# Wrapper key for encrypted JSONB payloads (so we can detect encrypted vs plain)
_ENCRYPTED_KEY = "_encrypted"


def encrypt_sensitive_fields(entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Encrypt sensitive fields in `data` for the given entity type.
    Returns a copy with encrypted values. Used before writing to DB.
    For block_entry.data (JSONB) we store {"_encrypted": "<ciphertext>"}.
    """
    out = dict(data)
    if entity_type == "block_content":
        if "content" in out and out["content"]:
            out["content"] = encrypt_str(str(out["content"]))
        if "title" in out and out["title"]:
            out["title"] = encrypt_str(str(out["title"]))
    elif entity_type == "block_entry":
        if "data" in out and out["data"] is not None:
            raw = json.dumps(out["data"]) if isinstance(out["data"], dict) else str(out["data"])
            out["data"] = {_ENCRYPTED_KEY: encrypt_str(raw)}
    return out


def decrypt_sensitive_fields(entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decrypt sensitive fields in `data` for the given entity type.
    Used when serializing for sync/API so clients receive plaintext.
    """
    out = dict(data)
    if entity_type == "block_content":
        if "content" in out and out["content"]:
            out["content"] = decrypt_str(str(out["content"]))
        if "title" in out and out["title"]:
            out["title"] = decrypt_str(str(out["title"]))
    elif entity_type == "block_entry":
        if "data" in out and isinstance(out["data"], dict) and _ENCRYPTED_KEY in out["data"]:
            try:
                dec = decrypt_str(out["data"][_ENCRYPTED_KEY])
                out["data"] = json.loads(dec)
            except Exception:
                pass
        elif "data" in out and isinstance(out["data"], str):
            try:
                out["data"] = json.loads(decrypt_str(out["data"]))
            except Exception:
                pass
    return out
