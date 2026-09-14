from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import (
    ALLOWED_CONTENT_TYPES,
    DEFAULT_BG_HEX,
    DEFAULT_OUTPUT_HEIGHT,
    DEFAULT_OUTPUT_WIDTH,
    IS_PRODUCTION,
    MAX_UPLOAD_BYTES,
)
from app.services.image_processor import (
    parse_hex_color,
    parse_output_size,
    process_passport_photo,
)

STATIC_DIR = Path(__file__).parent / "static"

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _is_valid_upload_image(raw: bytes) -> bool:
    if raw.startswith(b"\xff\xd8"):
        return True
    return raw.startswith(_PNG_SIGNATURE)


app = FastAPI(
    title="Passport Photo",
    description="Turn photos into 3×4 passport format with a custom background",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/process")
async def process_photo(
    photo: UploadFile = File(...),
    bg_color: str = Form(default=DEFAULT_BG_HEX),
    width: int = Form(default=DEFAULT_OUTPUT_WIDTH),
    height: int = Form(default=DEFAULT_OUTPUT_HEIGHT),
):
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

    try:
        parse_hex_color(bg_color)
        width, height = parse_output_size(width, height)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = process_passport_photo(raw, bg_color, width, height)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process photo: {exc}",
        ) from exc

    filename = f"pasfoto-{width}x{height}.jpg"
    return Response(
        content=result,
        media_type="image/jpeg",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
