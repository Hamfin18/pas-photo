# AGENTS.md

## Cursor Cloud specific instructions

This is **Pas Foto**, a single FastAPI web app that turns a JPG into a print-ready passport photo (AI background removal via `rembg`, then crop/resize/composite). There is one service, no database, and no automated test or lint suite in the repo.

### Service: web app (FastAPI + Uvicorn)
- The `.bat` scripts (`run.bat`, `run-prod.bat`, `ensure-venv.bat`) are Windows-only. On Linux, run via the venv directly.
- Run the dev server (auto-reload):
  - `APP_ENV=development .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- App is served at `http://localhost:8000`; interactive API docs at `/docs` (disabled when `APP_ENV=production`).
- Core API: `POST /api/process` (multipart form: `photo` JPG/JPEG ≤5MB, optional `bg_color` hex, `width`, `height`).

### Non-obvious caveats
- The Python venv lives at `.venv/` (gitignored). Use `.venv/bin/python` / `.venv/bin/uvicorn`, not the system Python.
- On first photo processing, `rembg` downloads the `u2net.onnx` model (~176 MB) to `~/.u2net/`. This needs internet and makes the first request slow; later requests are fast. The model cache is outside the repo and is not recreated by the update script.
- `python3-venv` (system package) is required to create the venv; it is installed during environment setup, not by the update script.
- No lint or test commands exist in this repo. To sanity-check, hit `GET /` (expect 200) or `POST /api/process` with a JPEG.
