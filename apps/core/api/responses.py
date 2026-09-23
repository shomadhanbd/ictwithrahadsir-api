"""Response shapes shared across apps.

Named `responses`, not `serializers`: `apps/core/api/serializers.py`
already exists one directory down and holds core's *own* endpoint
serializers. Two files with the same name in adjacent packages, meaning
different things, is a trap for anyone reading an import line.

Several endpoints answer with a bare acknowledgement rather than a resource.
Those payloads were written as dict literals inside the handlers, which meant
the key names existed only in the code that happened to build them and were
invisible to the generated schema.

App-specific payloads belong in that app's `api/*/serializers.py`; only the
shapes more than one app returns live here.
"""

from rest_framework import serializers


class OkResponseSerializer(serializers.Serializer):
    """`{"ok": true}` -- the answer to a request whose only outcome is
    whether it happened. `ok` is not always true: the enrolment-removal
    endpoint answers `{"ok": false}` with a 200 when there was nothing to
    remove."""

    ok = serializers.BooleanField()


class MessageResponseSerializer(serializers.Serializer):
    """`{"message": "..."}`.

    Note this is the same shape the error envelope uses
    (`apps/core/api/exception_handler.py`), so a client cannot tell success
    from failure by shape alone on these endpoints -- only by status code.
    That is long-standing behaviour both frontends already rely on; it is
    recorded here rather than changed.
    """

    message = serializers.CharField()
