class Conflict(Exception):
    """A request that clashes with the current state; answered with 409."""
