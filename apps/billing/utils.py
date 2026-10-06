import random
import string


def generate_transaction_id(product_id: int) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"shc_{product_id:03d}_{suffix}"
