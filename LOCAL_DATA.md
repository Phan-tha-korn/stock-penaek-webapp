# Local Data Layout

- Active local database: `storage/data/live/stock-penaek.db`
- Backup zip files from the web UI: `storage/backups/`
- Product images/media: `storage/media/`
- Logs: `storage/logs/`

Behavior:
- If `ESP_DATABASE_URL` in `.env` is empty, the backend uses the local SQLite database automatically.
- On first startup with the new layout, the app copies the old legacy database from `server/db/app.db` into `storage/data/live/stock-penaek.db` if needed.
- Backup zip files remain portable and can be uploaded back through the web backup restore screen.
