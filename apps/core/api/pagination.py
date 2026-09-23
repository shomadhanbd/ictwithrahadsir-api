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

    #: Numbered links kept either side of the current page. Laravel's own
    #: paginator emits one entry per page in the table, which is fine for a
    #: blog and not for an admin list: 50,000 students at the default page
    #: size is 3,300 link objects, each holding a full absolute URL, built
    #: and serialized on every single request -- several hundred KB of JSON
    #: to render at most a dozen buttons. Neither frontend reads `meta.links`
    #: (both paginate off `meta.last_page`), so this window keeps the field's
    #: shape and its usefulness while bounding its size.
    page_link_window = 5

    def get_paginated_response(self, data):
        paginator = self.page.paginator
        current_page = self.page.number
        last_page = paginator.num_pages or 1
        request = self.request
        base_url = request.build_absolute_uri(request.path)

        def page_url(page_number):
            if page_number is None:
                return None
            return self.request.build_absolute_uri(f"{request.path}?{self._replace_page_param(page_number)}")

        page_links = [
            {
                "url": page_url(current_page - 1) if self.page.has_previous() else None,
                "label": "&laquo; Previous",
                "active": False,
            }
        ]
        for page_number in self._windowed_page_numbers(current_page, last_page):
            if page_number is None:
                # Laravel renders the gap between windows as a disabled
                # ellipsis entry; keeping it means a client that does render
                # `meta.links` still gets a correct-looking control.
                page_links.append({"url": None, "label": "...", "active": False})
                continue
            page_links.append(
                {
                    "url": page_url(page_number),
                    "label": str(page_number),
                    "active": page_number == current_page,
                }
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
                                    page_url(current_page - 1) if self.page.has_previous() else None,
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

    def _windowed_page_numbers(self, current_page, last_page):
        """Page numbers to emit, with `None` marking an elided run.

        Always includes the first and last page plus `page_link_window`
        either side of the current one, so the control keeps its endpoints
        however deep into the table the caller is.
        """
        window = self.page_link_window
        wanted = {1, last_page}
        wanted.update(
            page for page in range(current_page - window, current_page + window + 1) if 1 <= page <= last_page
        )

        numbers, previous = [], 0
        for page in sorted(wanted):
            if page - previous > 1:
                numbers.append(None)
            numbers.append(page)
            previous = page
        return numbers

    def _replace_page_param(self, page_number):
        query = self.request.query_params.copy()
        query[self.page_query_param] = page_number
        return query.urlencode()
