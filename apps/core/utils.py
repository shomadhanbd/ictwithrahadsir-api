"""Shared helpers that belong to no single domain."""

import logging

DEFAULT_TRUNCATE_LIMIT = 200

#: Header names whose values must never reach a log file.
SENSITIVE_HEADERS = {'authorization', 'cookie', 'x-api-key'}


def get_logger(name: str) -> logging.Logger:
    """Module-level logger, so call sites never touch `logging` directly."""
    return logging.getLogger(name)


def truncate(value, limit: int = DEFAULT_TRUNCATE_LIMIT) -> str:
    """Shorten a value for logging.

    Request and provider payloads can be megabytes; logging them whole
    fills the rotating file with a single event.
    """
    text = value if isinstance(value, str) else repr(value)
    if len(text) <= limit:
        return text
    return f'{text[:limit]}… (+{len(text) - limit} chars)'


def scrub_headers(headers) -> dict:
    """Copy of `headers` with credential values replaced by a presence flag.

    Never log an Authorization value -- log only whether one was sent.
    """
    return {
        key: ('<set>' if str(value).strip() else '<none>') if key.lower() in SENSITIVE_HEADERS else truncate(value)
        for key, value in dict(headers).items()
    }
