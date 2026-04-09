from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from server.services import sheets_snapshots


class SheetSnapshotTests(unittest.TestCase):
    def test_create_sheet_snapshot_can_skip_full_backup_for_import_tab(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_root = Path(tmpdir)

            with (
                patch("server.services.sheets_snapshots.sheet_operation_snapshots_root", return_value=snapshot_root),
                patch("server.services.sheets_snapshots.load_master_config", return_value={"google_sheets_id": "sheet-123"}),
                patch(
                    "server.services.sheets_snapshots.create_backup_archive",
                    new=AsyncMock(side_effect=AssertionError("full backup should not run")),
                ) as backup_mock,
                patch(
                    "server.services.sheets_snapshots._capture_sheet_tabs_blocking",
                    return_value=[{"title": "Product Import", "values": [["SKU"], ["SKU-001"]]}],
                ) as capture_mock,
            ):
                result = asyncio.run(
                    sheets_snapshots.create_sheet_operation_snapshot(
                        "prepare-import-tab",
                        note="before refresh import tab",
                        include_backup=False,
                        tab_titles=["Product Import"],
                    )
                )

            backup_mock.assert_not_awaited()
            capture_mock.assert_called_once_with("sheet-123", ["Product Import"])
            self.assertFalse(result["backup_exists"])
            self.assertEqual(result["backup_file_name"], "")
            self.assertEqual(result["tab_count"], 1)
            self.assertEqual(result["tab_titles"], ["Product Import"])

    def test_rollback_can_restore_sheet_only_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_root = Path(tmpdir)
            snapshot_id = "20260409-prepare-import-tab"
            archive_path = snapshot_root / f"sheet-op-{snapshot_id}.zip"
            manifest = {
                "id": snapshot_id,
                "created_at": "2026-04-09T10:05:00Z",
                "operation": "prepare-import-tab",
                "note": "before refresh import tab",
                "sheet_id": "sheet-123",
                "has_sheet_snapshot": True,
                "tab_count": 1,
                "tab_titles": ["Product Import"],
                "backup_file_name": "",
                "backup_size_bytes": 0,
            }
            tabs = [{"title": "Product Import", "values": [["SKU"], ["SKU-001"]]}]
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                zf.writestr("manifest.json", json.dumps(manifest))
                zf.writestr("sheet-values.json", json.dumps(tabs))

            with (
                patch("server.services.sheets_snapshots.sheet_operation_snapshots_root", return_value=snapshot_root),
                patch(
                    "server.services.sheets_snapshots.create_backup_archive",
                    new=AsyncMock(return_value={"file_name": "rollback-backup.zip"}),
                ) as rollback_backup_mock,
                patch(
                    "server.services.sheets_snapshots.restore_backup_archive",
                    new=AsyncMock(side_effect=AssertionError("app restore should not run for sheet-only snapshot")),
                ) as restore_backup_mock,
                patch("server.services.sheets_snapshots._restore_sheet_tabs_blocking") as restore_tabs_mock,
                patch(
                    "server.services.sheets_snapshots.sync_all_to_sheets",
                    new=AsyncMock(side_effect=AssertionError("sheet restore should not fall back to full sync")),
                ) as sync_mock,
            ):
                result = asyncio.run(sheets_snapshots.rollback_to_sheet_operation_snapshot(snapshot_id))

            rollback_backup_mock.assert_awaited_once_with("before-sheet-rollback")
            restore_backup_mock.assert_not_awaited()
            restore_tabs_mock.assert_called_once_with("sheet-123", tabs)
            sync_mock.assert_not_awaited()
            self.assertTrue(result["ok"])
            self.assertEqual(result["restored_counts"], {})
            self.assertTrue(result["sheet_restored"])
            self.assertFalse(result["sheet_resynced"])


if __name__ == "__main__":
    unittest.main()
