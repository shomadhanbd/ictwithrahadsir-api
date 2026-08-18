"""Reading uploaded .xlsx workbooks.

Two admin screens import a spreadsheet -- students, and course enrolments --
and each had grown its own copy of "open the workbook, normalise the header
row, zip each row into a dict". The copies had already drifted: one guarded
the upload's size and extension, the other accepted any file at all.

`read_records` is that parsing, written once. `openpyxl` is imported lazily
because it is only ever needed by these two endpoints and pulling it in at
module scope would cost every request.
"""

from rest_framework import serializers


def read_records(file) -> list[dict]:
    """Rows of a workbook as dicts keyed by its normalised header row.

    Header cells are lowercased and stripped so `Phone`, `phone ` and `PHONE`
    all address the same column. A row with fewer cells than the header
    simply lacks those keys rather than raising.
    """
    import openpyxl

    workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
    rows = list(workbook.active.iter_rows(values_only=True))
    if not rows:
        raise serializers.ValidationError({'file': ['The file is empty.']})

    header = [str(cell).strip().lower() if cell else '' for cell in rows[0]]
    return [dict(zip(header, row, strict=False)) for row in rows[1:]]


def text(record: dict, key: str) -> str:
    """A trimmed string for `key`, empty when the cell is blank."""
    return str(record.get(key) or '').strip()


class SpreadsheetField(serializers.FileField):
    """An uploaded workbook, size- and extension-checked.

    Both importers parse the upload straight into memory, so the ceiling is
    the thing standing between an admin endpoint and a trivially large file.
    """

    MAX_BYTES = 5 * 1024 * 1024
    EXTENSIONS = ('.xlsx', '.xlsm')

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not value.name.lower().endswith(self.EXTENSIONS):
            raise serializers.ValidationError('Upload an .xlsx or .xlsm workbook.')
        if value.size > self.MAX_BYTES:
            raise serializers.ValidationError('The file may not be larger than 5 MB.')
        return value
