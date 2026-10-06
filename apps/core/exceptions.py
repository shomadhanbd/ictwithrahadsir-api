class Conflict(Exception):
    """A request that clashes with the current state; answered with 409."""


class ServiceUnavailable(Exception):
    """An outside service (the SMS gateway, ...) failed; answered with 503 and `default_message`."""

    default_message = "A service is unavailable. Please try again shortly."
