import csv

from django.http import HttpResponse
from django.utils import timezone


def csv_response(filename, header, rows) -> HttpResponse:
    """A CSV download, with a BOM so spreadsheet apps read Bangla text."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows([safe_cell(value) for value in row] for row in rows)
    return response


# A cell starting with one of these is run as a formula by spreadsheet apps.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    """Text a spreadsheet shows as text: a leading quote keeps a student's "=HYPERLINK(...)" name inert.

    Numbers are left alone, so a negative score stays a number.
    """
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


def local_stamp(value) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M") if value else ""


def clock(seconds) -> str:
    return "" if seconds is None else f"{seconds // 60}:{seconds % 60:02d}"
