"""
Minimal read-only .xlsx reader.

The Bank of England publishes the MPC voting history and the OIS yield curves
as Excel workbooks, so the fetcher has to read them. Everything here uses the
standard library only — the same constraint the rest of the fetcher works
under — so no new runtime dependency is introduced for two files a day.

Only what those two workbooks need is implemented: shared strings, inline
strings, and cell values by sheet name. Formulas are read as their cached
result, which is what the Bank ships in these files.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile
import xml.etree.ElementTree as ET
from typing import Iterator

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Excel's day 1 is 1900-01-01, offset by its non-existent 1900 leap day.
EXCEL_EPOCH = dt.date(1899, 12, 30)


def column_index(ref: str) -> int:
    """'A1' -> 0, 'B7' -> 1, 'AA3' -> 26."""
    total = 0
    for char in ref:
        if not char.isalpha():
            break
        total = total * 26 + (ord(char.upper()) - 64)
    return total - 1


def excel_date(serial: str | float | None) -> dt.date | None:
    """Excel serial day number -> date. Returns None for anything else."""
    if serial is None:
        return None
    try:
        days = int(float(serial))
    except (TypeError, ValueError):
        return None
    # Guard against a stray integer that is plainly not a date.
    if not 1 <= days <= 80000:
        return None
    return EXCEL_EPOCH + dt.timedelta(days=days)


class Workbook:
    """An .xlsx opened from bytes, addressable by sheet name."""

    def __init__(self, payload: bytes) -> None:
        self._zip = zipfile.ZipFile(io.BytesIO(payload))
        self._shared = self._read_shared_strings()
        self._sheets = self._read_sheet_index()

    @property
    def sheet_names(self) -> list[str]:
        return list(self._sheets)

    def _read_shared_strings(self) -> list[str]:
        try:
            raw = self._zip.read("xl/sharedStrings.xml")
        except KeyError:
            return []
        root = ET.fromstring(raw)
        return [
            "".join(node.text or "" for node in item.iter(MAIN + "t"))
            for item in root.iter(MAIN + "si")
        ]

    def _read_sheet_index(self) -> dict[str, str]:
        rels = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        targets = {node.get("Id"): node.get("Target") for node in rels}

        book = ET.fromstring(self._zip.read("xl/workbook.xml"))
        sheets: dict[str, str] = {}
        for node in book.iter(MAIN + "sheet"):
            target = targets.get(node.get(DOC_REL + "id"))
            if not target:
                continue
            path = target if target.startswith("/") else "xl/" + target.lstrip("./")
            sheets[node.get("name")] = path.lstrip("/")
        return sheets

    def rows(self, sheet_name: str) -> Iterator[dict[int, str]]:
        """
        Yield one dict per row: {zero-based column index: cell value as text}.

        Empty cells are absent rather than None, so `cells.get(4)` is the way to
        read a column. Rows are streamed, which matters because the OIS archive
        workbooks run to tens of megabytes of sheet XML.
        """
        path = self._sheets.get(sheet_name)
        if path is None:
            raise KeyError(f"{sheet_name!r} is not a sheet in this workbook "
                           f"({', '.join(self._sheets)})")

        with self._zip.open(path) as handle:
            for _, element in ET.iterparse(handle, events=("end",)):
                if element.tag != MAIN + "row":
                    continue
                cells: dict[int, str] = {}
                for cell in element.iter(MAIN + "c"):
                    value = self._cell_value(cell)
                    if value is not None:
                        cells[column_index(cell.get("r") or "")] = value
                element.clear()
                yield cells

    def _cell_value(self, cell: ET.Element) -> str | None:
        kind = cell.get("t")
        if kind == "inlineStr":
            node = cell.find(MAIN + "is")
            if node is None:
                return None
            return "".join(part.text or "" for part in node.iter(MAIN + "t"))

        node = cell.find(MAIN + "v")
        if node is None or node.text is None:
            return None
        if kind == "s":
            try:
                return self._shared[int(node.text)]
            except (ValueError, IndexError):
                return None
        return node.text
