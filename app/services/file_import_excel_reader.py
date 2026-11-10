"""Workbook opening policy for legacy financial XLSX uploads."""

import io
from collections.abc import Iterator
from contextlib import contextmanager, suppress

import openpyxl
from openpyxl.workbook import Workbook


@contextmanager
def open_import_workbook(content: bytes) -> Iterator[Workbook]:
    """Keep the workbook and its input stream open while the caller reads rows."""
    for opts in (
        {"read_only": True, "data_only": True},
        {"read_only": True, "data_only": False},
        {"data_only": True},
        {},
    ):
        with io.BytesIO(content) as stream:
            try:
                workbook = openpyxl.load_workbook(stream, **opts)
            except Exception:
                continue
            if workbook is None:
                break

            try:
                yield workbook
            except BaseException:
                # Preserve the original read error if cleanup also fails.
                with suppress(Exception):
                    workbook.close()
                raise
            else:
                workbook.close()
            return

    raise ValueError("엑셀 파일을 열 수 없습니다. 파일 손상 여부를 확인하세요.")
