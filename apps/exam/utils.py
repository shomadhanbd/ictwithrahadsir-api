import hashlib
import random
from decimal import Decimal

ZERO = Decimal("0")
SEED_MASK = (1 << 63) - 1  # `ExamAttempt.seed` is a signed bigint


def paper_seed(*, exam_id, user_id) -> int:
    """A per-student seed for one paper, stable across reloads and restarts."""
    digest = hashlib.blake2b(f"{exam_id}:{user_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") & SEED_MASK


def seeded_shuffle(items, *, seed) -> list:
    """`items` in an order fixed by `seed`."""
    items = list(items)
    random.Random(seed).shuffle(items)
    return items
