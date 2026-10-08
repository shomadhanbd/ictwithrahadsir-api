import random
import string


def generate_transaction_id(product_id: int | None) -> str:
    """`shc_<package>_<random>`; a payment without a package (a book order) is `shc_bk_<random>`."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    tag = f"{product_id:03d}" if product_id else "bk"
    return f"shc_{tag}_{suffix}"
