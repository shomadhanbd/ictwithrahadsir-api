from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class LaravelStylePageNumberPagination(PageNumberPagination):
    """Laravel's `{data, links, meta}` paginator envelope, which both
    frontends parse. `per_page` may be raised to 200."""

    page_size = 15
    page_size_query_param = "per_page"
    max_page_size = 200

    #: Numbered links either side of the current page in `meta.links`, so the
    #: list stays small however many pages there are.
    page_link_window = 5

    def get_paginated_response(self, data):
        page = self.page
        current = page.number
        last = page.paginator.num_pages or 1
        prev_url = self._page_url(current - 1) if page.has_previous() else None
        next_url = self._page_url(current + 1) if page.has_next() else None

        page_links = [{"url": prev_url, "label": "&laquo; Previous", "active": False}]
        for number in self._windowed_page_numbers(current, last):
            if number is None:
                page_links.append({"url": None, "label": "...", "active": False})
            else:
                page_links.append({"url": self._page_url(number), "label": str(number), "active": number == current})
        page_links.append({"url": next_url, "label": "Next &raquo;", "active": False})

        return Response(
            {
                "data": data,
                "links": {
                    "first": self._page_url(1),
                    "last": self._page_url(last),
                    "prev": prev_url,
                    "next": next_url,
                },
                "meta": {
                    "current_page": current,
                    "from": page.start_index() or None,
                    "last_page": last,
                    "path": self.request.build_absolute_uri(self.request.path),
                    "per_page": self.get_page_size(self.request),
                    "to": page.end_index() or None,
                    "total": page.paginator.count,
                    "links": page_links,
                },
            }
        )

    def _page_url(self, number):
        query = self.request.query_params.copy()
        query[self.page_query_param] = number
        return self.request.build_absolute_uri(f"{self.request.path}?{query.urlencode()}")

    def _windowed_page_numbers(self, current, last):
        """The first and last page plus `page_link_window` either side of the
        current one, with `None` marking each gap."""
        window = self.page_link_window
        wanted = {1, last} | {p for p in range(current - window, current + window + 1) if 1 <= p <= last}

        numbers, previous = [], 0
        for number in sorted(wanted):
            if number - previous > 1:
                numbers.append(None)
            numbers.append(number)
            previous = number
        return numbers
