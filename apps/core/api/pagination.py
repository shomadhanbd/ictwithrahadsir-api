from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class LaravelStylePageNumberPagination(PageNumberPagination):
    """
    Reproduces Laravel's default API-Resource paginator envelope exactly,
    since both existing frontends already parse `{data, links, meta}`.
    """

    page_size = 15
    page_size_query_param = "per_page"
    max_page_size = 200
    page_query_param = "page"

    def get_paginated_response(self, data):
        paginator = self.page.paginator
        current_page = self.page.number
        last_page = paginator.num_pages or 1
        request = self.request
        base_url = request.build_absolute_uri(request.path)

        def page_url(page_number):
            if page_number is None:
                return None
            return self.request.build_absolute_uri(
                f"{request.path}?{self._replace_page_param(page_number)}"
            )

        page_links = []
        for page_number in range(1, last_page + 1):
            page_links.append(
                {
                    "url": page_url(page_number),
                    "label": str(page_number),
                    "active": page_number == current_page,
                }
            )
        page_links.insert(
            0,
            {
                "url": page_url(current_page - 1) if self.page.has_previous() else None,
                "label": "&laquo; Previous",
                "active": False,
            },
        )
        page_links.append(
            {
                "url": page_url(current_page + 1) if self.page.has_next() else None,
                "label": "Next &raquo;",
                "active": False,
            }
        )

        return Response(
            OrderedDict(
                [
                    ("data", data),
                    (
                        "links",
                        OrderedDict(
                            [
                                ("first", page_url(1)),
                                ("last", page_url(last_page)),
                                (
                                    "prev",
                                    page_url(current_page - 1)
                                    if self.page.has_previous()
                                    else None,
                                ),
                                (
                                    "next",
                                    page_url(current_page + 1) if self.page.has_next() else None,
                                ),
                            ]
                        ),
                    ),
                    (
                        "meta",
                        OrderedDict(
                            [
                                ("current_page", current_page),
                                ("from", self.page.start_index() or None),
                                ("last_page", last_page),
                                ("path", base_url),
                                ("per_page", self.get_page_size(request)),
                                ("to", self.page.end_index() or None),
                                ("total", paginator.count),
                                ("links", page_links),
                            ]
                        ),
                    ),
                ]
            )
        )

    def _replace_page_param(self, page_number):
        query = self.request.query_params.copy()
        query[self.page_query_param] = page_number
        return query.urlencode()
