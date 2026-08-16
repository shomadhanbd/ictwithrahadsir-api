"""Enumerate every URL this project serves, as a stable sorted list.

Both frontends call this API by literal path (21 call sites in the client,
~40 in the admin panel) and the paths are a deliberate drop-in replacement
for a legacy Laravel contract. Any refactor that moves modules around must
leave the emitted paths untouched, so `tests.py` snapshots this list and
fails if a single path appears, disappears or changes shape.

Route *names* are deliberately excluded: they are internal, and the
restructure is expected to add and re-namespace them.
"""

from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver

#: Regenerate with `python manage.py dump_url_contract`.
SNAPSHOT_PATH = 'apps/core/url_contract.txt'

#: Only the API surface is a contract. Django's own admin routes are
#: excluded because they change with the Django version rather than with
#: anything we control, and the DEBUG-only media route is excluded because
#: it is absent whenever DEBUG is off (including under the test runner).
CONTRACT_PREFIX = 'api/'


def iter_url_paths(resolver=None, prefix=''):
    """Yield the full path expression of every leaf route."""
    if resolver is None:
        resolver = get_resolver()

    for entry in resolver.url_patterns:
        pattern = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from iter_url_paths(entry, pattern)
        elif isinstance(entry, URLPattern):
            yield pattern


def current_url_contract():
    """The sorted, de-duplicated set of served API paths."""
    return sorted({p for p in iter_url_paths() if p.startswith(CONTRACT_PREFIX)})
