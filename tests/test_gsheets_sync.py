from __future__ import annotations

import unittest

from server.services.gsheets import HEADERS, TAB_PRODUCT_IMPORT, TAB_STOCK, _build_import_template_rows, _sync_stock_sheet


class _FakeWorksheet:
    def __init__(self, values: list[list[str]]):
        self._values = [row[:] for row in values]

    def get_all_values(self):
        return [row[:] for row in self._values]

    def clear(self):
        self._values = []

    def update(self, _range_or_values, values=None):
        if values is None:
            self._values = [row[:] for row in _range_or_values]
        else:
            self._values = [row[:] for row in values]


class GSheetsSyncTests(unittest.TestCase):
    def test_sync_stock_sheet_replaces_stale_rows(self) -> None:
        header = HEADERS[TAB_STOCK]
        ws = _FakeWorksheet(
            [
                header,
                ["STALE-SKU", "Old Product"] + [""] * (len(header) - 2),
                ["SKU-0001", "Previous Name"] + [""] * (len(header) - 2),
            ]
        )

        _sync_stock_sheet(
            ws,
            [
                {
                    "sku": "SKU-0001",
                    "name_th": "Current Product",
                    "category": "General",
                    "unit": "pcs",
                    "stock_qty": 5,
                    "max_stock": 10,
                    "cost_price": 12,
                    "selling_price": 15,
                    "status": "NORMAL",
                    "updated_at": "2026-04-02T12:00:00",
                }
            ],
        )

        values = ws.get_all_values()
        self.assertEqual(len(values), 2)
        self.assertEqual(values[1][0], "SKU-0001")
        self.assertEqual(values[1][1], "Current Product")

    def test_build_import_template_rows_includes_latest_products_and_threshold(self) -> None:
        rows = _build_import_template_rows(
            [
                {
                    "sku": "SKU-1000",
                    "name_th": "Template Product",
                    "category": "General",
                    "unit": "pcs",
                    "stock_qty": 12,
                    "min_stock": 3,
                    "max_stock": 15,
                    "selling_price": 49,
                    "status": "NORMAL",
                    "updated_at": "2026-04-09T09:30:00",
                }
            ]
        )

        self.assertEqual(rows[0], HEADERS[TAB_PRODUCT_IMPORT])
        self.assertEqual(rows[1][0], "SKU-1000")
        self.assertEqual(rows[1][1], "Template Product")
        self.assertEqual(rows[1][4], "12")
        self.assertEqual(rows[1][5], "15")
        self.assertEqual(rows[1][6], "49")
        self.assertEqual(rows[1][7], "20")


if __name__ == "__main__":
    unittest.main()
