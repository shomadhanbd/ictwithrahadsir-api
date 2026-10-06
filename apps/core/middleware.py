class MethodOverrideMiddleware:
    """Treats `POST ...?_method=PUT|PATCH|DELETE` as that method; the admin panel sends multipart updates so."""

    OVERRIDABLE = {"PUT", "PATCH", "DELETE"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST":
            override = request.GET.get("_method", "").upper()
            if override in self.OVERRIDABLE:
                request.method = override
        return self.get_response(request)
