"""
crypto.py — Military-Grade End-to-End Encryption Engine

Uses X25519 key exchange → HKDF → AES-256-GCM for all messages.
Private keys NEVER leave the client device. Server only sees ciphertext.
"""
import os
import base64
import json
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class KeyPair:
    """Ephemeral X25519 key pair for a session."""
    def __init__(self):
        self._private = X25519PrivateKey.generate()
        self._public = self._private.public_key()

    @property
    def public_bytes(self) -> bytes:
        return self._public.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw
        )

    @property
    def public_b64(self) -> str:
        return base64.b64encode(self.public_bytes).decode()

    def derive_shared_key(self, peer_public_b64: str) -> bytes:
        """Derive a 32-byte shared secret using X25519 + HKDF."""
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
        peer_bytes = base64.b64decode(peer_public_b64)
        peer_key = X25519PublicKey.from_public_bytes(peer_bytes)
        raw_shared = self._private.exchange(peer_key)
        # HKDF to derive a proper 32-byte AES key
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'NOMAD-SecureChat-v1')
        return hkdf.derive(raw_shared)


class MessageCrypto:
    """AES-256-GCM encryption/decryption for chat messages."""

    @staticmethod
    def encrypt(key: bytes, plaintext: str) -> str:
        """Returns base64-encoded ciphertext string (nonce + tag + data)."""
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        combined = nonce + ciphertext  # nonce prepended to ciphertext
        return base64.b64encode(combined).decode()

    @staticmethod
    def decrypt(key: bytes, encrypted_b64: str) -> str:
        """Decrypt a base64 encoded ciphertext. Raises on tamper detection."""
        aesgcm = AESGCM(key)
        combined = base64.b64decode(encrypted_b64)
        nonce = combined[:12]
        ciphertext = combined[12:]
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')


class PasswordHasher:
    """Argon2-style password hashing using PBKDF2 (pure stdlib fallback)."""
    ITERATIONS = 480_000  # NIST 2023 recommended minimum
    
    @staticmethod
    def hash_password(password: str) -> str:
        import hashlib
        salt = os.urandom(32)
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PasswordHasher.ITERATIONS)
        return base64.b64encode(salt + key).decode()

    @staticmethod
    def verify_password(password: str, stored_hash: str) -> bool:
        import hashlib
        decoded = base64.b64decode(stored_hash)
        salt = decoded[:32]
        stored_key = decoded[32:]
        verify_key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PasswordHasher.ITERATIONS)
        return stored_key == verify_key
