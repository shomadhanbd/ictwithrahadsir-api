class MethodOverrideMiddleware:
    """Treat `POST ...?_method=PUT|PATCH|DELETE` as that method.

    The admin panel sends multipart updates this way. Only the query string
    is read, so the body is left for normal parsing.
    """

    OVERRIDABLE = {"PUT", "PATCH", "DELETE"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST":
            override = request.GET.get("_method", "").upper()
            if override in self.OVERRIDABLE:
                request.method = override
        return self.get_response(request)
