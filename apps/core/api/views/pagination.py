from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class ApiPagination(PageNumberPagination):
    """`{data, meta}` pages; `?per_page=` may be raised to 200."""

    page_size = 15
    page_size_query_param = "per_page"
    max_page_size = 200

    def get_paginated_response(self, data):
        page = self.page
        return Response(
            {
                "data": data,
                "meta": {
                    "current_page": page.number,
                    "last_page": page.paginator.num_pages,
                    "per_page": self.get_page_size(self.request),
                    "total": page.paginator.count,
                    "from": page.start_index() or None,
                    "to": page.end_index() or None,
                },
            }
        )
