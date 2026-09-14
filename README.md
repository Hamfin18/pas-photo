# Pas Foto 3×4

A simple web app that turns everyday photos into **print-ready ID/passport photos**: the background is removed automatically, replaced with a solid color, then cropped and resized to your chosen dimensions (e.g. 300×400 px for a 3×4 ratio).

---

## What it does

| Feature | Description |
|---------|-------------|
| **Background removal** | Uses AI (`rembg`) to separate the subject from the original background |
| **Custom background** | Fills empty areas with a solid color (hex format, e.g. `#FFFFFF` white, `#0033A0` blue) |
| **Crop & aspect ratio** | Crops around the face/body with padding, matching your output width × height |
| **Output size** | Width and height in pixels (50–4000 px); default 300×400 (3×4 ratio) |
| **JPG export** | High-quality JPEG output, ready to download or print |

Useful for ID cards, visas, job applications, or studio prints—without manual editing in Photoshop.

**Processing pipeline (short):**

1. Upload a JPG or PNG → validate type & size (max 5 MB)
2. `rembg` produces an image with an alpha channel (no background)
3. Detect subject bounds → crop to target aspect ratio + padding
4. Resize to chosen dimensions → composite onto the background color
5. Download `pasfoto-{width}x{height}.jpg`

---

## How to use

### Requirements

- **Windows** (`.bat` scripts provided)
- **Python 3.10+** installed and on PATH ([python.org](https://www.python.org/downloads/))
- **Internet** on first run (the `rembg` AI model is downloaded once, ~170 MB)

### Running the app

| Mode | File | When to use |
|------|------|-------------|
| **Development** | `run.bat` | Local development and testing |
| **Production** | `run-prod.bat` | LAN access or a small VPS |

**Development (`run.bat`)**

1. Double-click `run.bat` in the project folder.
2. On first run, `ensure-venv.bat` creates a virtual environment (`.venv`) and installs dependencies from `requirements.txt`.
3. The server runs at **http://localhost:8000**; the browser opens automatically.
4. Auto-reload is on—Python code changes restart the server.
5. Close the terminal window to stop the server.

**Production (`run-prod.bat`)**

1. Double-click `run-prod.bat`.
2. The server listens on **0.0.0.0:8000** (reachable from other devices on the same network).
3. API docs (`/docs`, `/redoc`) are disabled.
4. For public deployment, put **Nginx** (or another reverse proxy) + **HTTPS** in front of this app.

### Web UI steps

1. Open the home page (opens automatically with `run.bat`, or go to `http://localhost:8000`).
2. **Output size** — enter width & height (px), or click a preset: `300×400`, `354×472`, `600×800`.
3. **Photo** — choose a **JPG/JPEG or PNG** file (max 5 MB).
4. **Background color** — use the color picker or type a hex value (e.g. `#FFFFFF`).
5. Click **Buat pas foto** (Create passport photo) — wait a few seconds for AI processing.
6. Preview the result, then click **Unduh JPG** (Download JPG).

Your last used dimensions are saved in the browser’s `localStorage` so presets persist after refresh.

### Manual run (without `.bat`)

```bash
cd path/to/pas-foto
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set APP_ENV=development
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On Linux/macOS, activate the venv with `source .venv/bin/activate` and use `export APP_ENV=development` instead of `set`.

---

## Tech stack

### Backend

| Technology | Role |
|------------|------|
| **[Python](https://www.python.org/)** | Main language |
| **[FastAPI](https://fastapi.tiangolo.com/)** | Web framework: REST API, request validation, static files |
| **[Uvicorn](https://www.uvicorn.org/)** | ASGI server |
| **[python-multipart](https://github.com/Kludex/python-multipart)** | File upload parsing (`multipart/form-data`) |
| **[rembg](https://github.com/danielgatis/rembg)** | AI background removal (ONNX model) |
| **[ONNX Runtime](https://onnxruntime.ai/)** | AI inference runtime |
| **[Pillow (PIL)](https://pillow.readthedocs.io/)** | Crop, resize, compositing, JPEG export |

### Frontend

| Technology | Role |
|------------|------|
| **HTML / CSS / JavaScript (vanilla)** | UI without a framework; upload form, size presets, preview & download |
| **Fetch API** | Calls `POST /api/process` from the browser |

### Local tooling

- **Virtual environment** (`.venv`) — isolated Python dependencies
- **Batch scripts** (`ensure-venv.bat`, `run.bat`, `run-prod.bat`) — setup and run the server on Windows

### Dependencies (`requirements.txt`)

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
python-multipart>=0.0.12
rembg>=2.0.57
pillow>=11.0.0
onnxruntime>=1.19.0
```

---

## Project structure

```
pas-foto/
├── app/
│   ├── main.py              # FastAPI entry, routes / and /api/process
│   ├── config.py            # Constants (sizes, upload limits, prod/dev mode)
│   ├── services/
│   │   └── image_processor.py   # rembg, crop, composite, export logic
│   └── static/
│       ├── index.html       # Main page
│       ├── style.css
│       └── app.js           # Form, validation, preview, download
├── ensure-venv.bat          # Create venv & pip install (first run)
├── run.bat                  # Dev server
├── run-prod.bat             # Production server
├── requirements.txt
└── README.md
```

---

## API

For programmatic integration or testing (development mode: interactive docs at **http://localhost:8000/docs**).

### `POST /api/process`

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `photo` | file | Yes | JPG/JPEG or PNG, max 5 MB |
| `bg_color` | string | No | Hex `#RRGGBB` (default `#FFFFFF`) |
| `width` | int | No | Output width 50–4000 px (default `300`) |
| `height` | int | No | Output height 50–4000 px (default `400`) |

**Success response:** `image/jpeg` with header `Content-Disposition: attachment; filename="pasfoto-{width}x{height}.jpg"`

**Example with curl (Windows):**

```bash
curl -X POST "http://localhost:8000/api/process" ^
  -F "photo=@photo.jpg" ^
  -F "bg_color=#FFFFFF" ^
  -F "width=300" ^
  -F "height=400" ^
  --output result.jpg
```

**Example with curl (Linux/macOS):**

```bash
curl -X POST "http://localhost:8000/api/process" \
  -F "photo=@photo.jpg" \
  -F "bg_color=#FFFFFF" \
  -F "width=300" \
  -F "height=400" \
  --output result.jpg
```

---

## Tips & notes

- **First run is slower** — the AI model must load (and download if missing).
- **Best photos:** clear face, good contrast with the original background, even lighting; avoid hair/background colors too close to skin tone.
- **Crop quality** follows subject detection from the alpha channel; complex shots (fine hair, shadows) may need a retry or a new photo.
- **Input:** JPG or PNG — output is always JPG for print.
- **Privacy:** photos are processed on your local server; nothing is sent to third-party services except the one-time `rembg` model download.

---

## License & contribution

Local/internal utility project. Add a license if you plan to distribute it publicly.
