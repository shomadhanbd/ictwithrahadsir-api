"""Read helpers for course payloads, including one inverted dependency.

The course payload carries `has_order`, which is a fact about billing.
Computing it here meant `courses` importing `Order`, while `billing`
already holds foreign keys into `courses` -- a cycle in both directions.

Money knows about the catalogue; the catalogue must not know about money.
So `courses` declares the hole and `billing` fills it at startup (see
`apps.billing.apps.BillingConfig.ready`). If billing is ever removed the
field degrades to False rather than raising.
"""

#: Set by the app that owns orders. Signature: (user, course_ids) -> set[int]
ordered_course_ids_provider = None


def ordered_course_ids(user, course_ids):
    """Which of `course_ids` this user has ever placed an order for."""
    if ordered_course_ids_provider is None:
        return set()
    if user is None or not user.is_authenticated:
        return set()
    return ordered_course_ids_provider(user, course_ids)
