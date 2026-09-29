import logging
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import (
    ALLOWED_CONTENT_TYPES,
    DEFAULT_BG_HEX,
    DEFAULT_OUTPUT_HEIGHT,
    DEFAULT_OUTPUT_WIDTH,
    IS_PRODUCTION,
    MAX_UPLOAD_BYTES,
    RATE_LIMIT_MAX_CALLS,
    RATE_LIMIT_PERIOD_SEC,
)
from app.services.image_processor import (
    REMBG_READY,
    compose_from_cutout,
    make_cutout,
    parse_crop_adjust,
    parse_hex_color,
    parse_output_size,
    process_passport_photo,
)

STATIC_DIR = Path(__file__).parent / "static"

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("pasfoto")

_rembg_lock = threading.Lock()


class _SlidingWindowLimiter:
    """Simple in-process per-key rate limiter (1 worker assumed)."""

    def __init__(self, max_calls: int, period_sec: float):
        self.max_calls = max_calls
        self.period = period_sec
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - self.period:
                q.popleft()
            if len(q) >= self.max_calls:
                return False
            q.append(now)
            return True


_rate_limiter = _SlidingWindowLimiter(RATE_LIMIT_MAX_CALLS, RATE_LIMIT_PERIOD_SEC)

# Paths that get IP rate limiting (POST processing endpoints)
_RATE_LIMITED_PATHS = {"/api/process", "/api/cutout", "/api/compose"}


def _is_valid_upload_image(raw: bytes) -> bool:
    if raw.startswith(b"\xff\xd8"):
        return True
    return raw.startswith(_PNG_SIGNATURE)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


async def _read_and_validate_image(photo: UploadFile) -> bytes:
    raw = await photo.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum file size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    if photo.content_type not in ALLOWED_CONTENT_TYPES and not _is_valid_upload_image(
        raw
    ):
        raise HTTPException(
            status_code=400,
            detail="Only JPG/JPEG or PNG files are allowed.",
        )

    if not _is_valid_upload_image(raw):
        raise HTTPException(
            status_code=400,
            detail="File is not a valid JPEG or PNG.",
        )
    return raw


app = FastAPI(
    title="Passport Photo",
    description="Turn photos into 3×4 passport format with a custom background",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.method == "POST" and request.url.path in _RATE_LIMITED_PATHS:
        ip = _client_ip(request)
        if not _rate_limiter.allow(ip):
            logger.warning(
                "rate_limited path=%s client_ip=%s",
                request.url.path,
                ip,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        "Terlalu banyak permintaan. Maksimal "
                        f"{RATE_LIMIT_MAX_CALLS} kali per menit. Coba lagi sebentar."
                    )
                },
            )
    return await call_next(request)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "rembg": "ready" if REMBG_READY else "not_ready",
    }


@app.post("/api/cutout")
async def cutout_photo(request: Request, photo: UploadFile = File(...)):
    """Remove background; return RGBA PNG cutout for client crop preview."""
    ip = _client_ip(request)
    t0 = time.perf_counter()
    outcome = "error"
    upload_size = 0
    try:
        raw = await _read_and_validate_image(photo)
        upload_size = len(raw)

        if not _rembg_lock.acquire(blocking=False):
            outcome = "busy"
            raise HTTPException(
                status_code=429,
                detail=(
                    "Sedang memproses foto lain. VPS hanya menangani satu "
                    "pekerjaan AI sekaligus — coba lagi sebentar."
                ),
            )
        try:
            result = make_cutout(raw)
        finally:
            _rembg_lock.release()

        outcome = "ok"
        return Response(
            content=result,
            media_type="image/png",
            headers={"Content-Disposition": 'inline; filename="cutout.png"'},
        )
    except HTTPException as exc:
        if outcome != "busy":
            outcome = f"http_{exc.status_code}"
        raise
    except Exception as exc:
        outcome = "error"
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process photo: {exc}",
        ) from exc
    finally:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "cutout outcome=%s duration_ms=%d upload_bytes=%d client_ip=%s",
            outcome,
            duration_ms,
            upload_size,
            ip,
        )


@app.post("/api/compose")
async def compose_photo(
    request: Request,
    cutout: UploadFile = File(...),
    bg_color: str = Form(default=DEFAULT_BG_HEX),
    width: int = Form(default=DEFAULT_OUTPUT_WIDTH),
    height: int = Form(default=DEFAULT_OUTPUT_HEIGHT),
    offset_x: float = Form(default=0.0),
    offset_y: float = Form(default=0.0),
    zoom: float = Form(default=1.0),
):
    """Compose final JPEG from a cutout PNG + crop adjust (no rembg)."""
    ip = _client_ip(request)
    t0 = time.perf_counter()
    outcome = "error"
    upload_size = 0
    out_w = width
    out_h = height
    try:
        raw = await cutout.read()
        upload_size = len(raw) if raw else 0
        if not raw:
            raise HTTPException(status_code=400, detail="File is empty.")
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum file size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            )
        if not raw.startswith(_PNG_SIGNATURE):
            raise HTTPException(
                status_code=400,
                detail="Cutout must be a PNG (RGBA) from /api/cutout.",
            )

        try:
            parse_hex_color(bg_color)
            out_w, out_h = parse_output_size(width, height)
            parse_crop_adjust(offset_x, offset_y, zoom)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        result = compose_from_cutout(
            raw, bg_color, out_w, out_h, offset_x, offset_y, zoom
        )
        outcome = "ok"
        filename = f"pasfoto-{out_w}x{out_h}.jpg"
        return Response(
            content=result,
            media_type="image/jpeg",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException as exc:
        outcome = f"http_{exc.status_code}"
        raise
    except Exception as exc:
        outcome = "error"
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compose photo: {exc}",
        ) from exc
    finally:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "compose outcome=%s duration_ms=%d size=%dx%d upload_bytes=%d client_ip=%s",
            outcome,
            duration_ms,
            out_w,
            out_h,
            upload_size,
            ip,
        )


@app.post("/api/process")
async def process_photo(
    request: Request,
    photo: UploadFile = File(...),
    bg_color: str = Form(default=DEFAULT_BG_HEX),
    width: int = Form(default=DEFAULT_OUTPUT_WIDTH),
    height: int = Form(default=DEFAULT_OUTPUT_HEIGHT),
    offset_x: float = Form(default=0.0),
    offset_y: float = Form(default=0.0),
    zoom: float = Form(default=1.0),
):
    """One-shot rembg + compose (optional crop adjust)."""
    ip = _client_ip(request)
    t0 = time.perf_counter()
    outcome = "error"
    upload_size = 0
    out_w = width
    out_h = height
    try:
        raw = await _read_and_validate_image(photo)
        upload_size = len(raw)

        try:
            parse_hex_color(bg_color)
            out_w, out_h = parse_output_size(width, height)
            parse_crop_adjust(offset_x, offset_y, zoom)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not _rembg_lock.acquire(blocking=False):
            outcome = "busy"
            raise HTTPException(
                status_code=429,
                detail=(
                    "Sedang memproses foto lain. VPS hanya menangani satu "
                    "pekerjaan AI sekaligus — coba lagi sebentar."
                ),
            )
        try:
            result = process_passport_photo(
                raw, bg_color, out_w, out_h, offset_x, offset_y, zoom
            )
        finally:
            _rembg_lock.release()

        outcome = "ok"
        filename = f"pasfoto-{out_w}x{out_h}.jpg"
        return Response(
            content=result,
            media_type="image/jpeg",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException as exc:
        if outcome != "busy":
            outcome = f"http_{exc.status_code}"
        raise
    except Exception as exc:
        outcome = "error"
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process photo: {exc}",
        ) from exc
    finally:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "process outcome=%s duration_ms=%d size=%dx%d upload_bytes=%d client_ip=%s",
            outcome,
            duration_ms,
            out_w,
            out_h,
            upload_size,
            ip,
        )
