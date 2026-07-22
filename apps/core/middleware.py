class MethodOverrideMiddleware:
    """The admin panel sends multipart update requests as
    `POST /admin/<resource>/{id}?_method=PUT` (a Laravel convention, since
    PHP can't parse multipart bodies on PUT/PATCH). Rewriting
    `request.method` here -- before DRF's dispatch() picks a handler --
    lets the same DRF ModelViewSet routes serve both a real PUT/PATCH and
    this override style with no extra view code.

    Only reads the query string, never the request body, so it can't
    interfere with downstream multipart parsing."""

    OVERRIDABLE = {"PUT", "PATCH", "DELETE"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST":
            override = request.GET.get("_method", "").upper()
            if override in self.OVERRIDABLE:
                request.method = override
        return self.get_response(request)
