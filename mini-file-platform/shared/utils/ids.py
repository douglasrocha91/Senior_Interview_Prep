import os
import time

# Crockford's Base32 — no I, L, O, U to avoid ambiguity
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def generate_ulid() -> str:
    """Return a 26-character ULID (timestamp + random, lexicographically sortable)."""
    timestamp_ms = int(time.time() * 1000)
    random_bits = int.from_bytes(os.urandom(10), "big")
    return _encode(timestamp_ms, 10) + _encode(random_bits, 16)
