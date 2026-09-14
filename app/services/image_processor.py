import io
import re

from PIL import Image, ImageOps
from rembg import new_session, remove

# Lighter model + single session — important on ~1 GB RAM VPS
_REMBG_SESSION = new_session("u2netp")
_MAX_REMBG_SIDE = 800

from app.config import (
    DEFAULT_OUTPUT_HEIGHT,
    DEFAULT_OUTPUT_WIDTH,
    MAX_OUTPUT_SIZE,
    MIN_OUTPUT_SIZE,
)

HEX_PATTERN = re.compile(r"^#?([0-9A-Fa-f]{6})$")


def parse_hex_color(hex_color: str) -> tuple[int, int, int]:
    match = HEX_PATTERN.match(hex_color.strip())
    if not match:
        raise ValueError("Invalid hex color. Use format #RRGGBB.")
    value = match.group(1)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def parse_output_size(width: int, height: int) -> tuple[int, int]:
    if width < MIN_OUTPUT_SIZE or width > MAX_OUTPUT_SIZE:
        raise ValueError(
            f"Width must be between {MIN_OUTPUT_SIZE}–{MAX_OUTPUT_SIZE} px."
        )
    if height < MIN_OUTPUT_SIZE or height > MAX_OUTPUT_SIZE:
        raise ValueError(
            f"Height must be between {MIN_OUTPUT_SIZE}–{MAX_OUTPUT_SIZE} px."
        )
    return width, height


def _subject_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox is None:
        return (0, 0, img.width, img.height)
    return bbox


def _crop_box_for_aspect(
    bbox: tuple[int, int, int, int],
    img_size: tuple[int, int],
    target_aspect: float,
    padding_ratio: float = 0.12,
) -> tuple[int, int, int, int]:
    img_w, img_h = img_size
    x0, y0, x1, y1 = bbox
    bw = x1 - x0
    bh = y1 - y0
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2

    bw *= 1 + padding_ratio * 2
    bh *= 1 + padding_ratio * 2

    current_aspect = bw / bh if bh else target_aspect

    if current_aspect > target_aspect:
        bh = bw / target_aspect
    else:
        bw = bh * target_aspect

    left = cx - bw / 2
    top = cy - bh / 2
    right = cx + bw / 2
    bottom = cy + bh / 2

    if left < 0:
        right -= left
        left = 0
    if top < 0:
        bottom -= top
        top = 0
    if right > img_w:
        left -= right - img_w
        right = img_w
    if bottom > img_h:
        top -= bottom - img_h
        bottom = img_h

    left = max(0, int(left))
    top = max(0, int(top))
    right = min(img_w, int(right))
    bottom = min(img_h, int(bottom))

    crop_w = right - left
    crop_h = bottom - top
    current_crop_aspect = crop_w / crop_h if crop_h else target_aspect
    if abs(current_crop_aspect - target_aspect) > 0.01:
        if current_crop_aspect > target_aspect:
            new_h = crop_w / target_aspect
            top = max(0, min(top, img_h - int(new_h)))
            bottom = min(img_h, top + int(new_h))
        else:
            new_w = crop_h * target_aspect
            left = max(0, min(left, img_w - int(new_w)))
            right = min(img_w, left + int(new_w))

    return (left, top, right, bottom)


def _bytes_for_rembg(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    w, h = img.size
    longest = max(w, h)
    if longest > _MAX_REMBG_SIDE:
        scale = _MAX_REMBG_SIDE / longest
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


def process_passport_photo(
    image_bytes: bytes,
    bg_hex: str,
    width: int = DEFAULT_OUTPUT_WIDTH,
    height: int = DEFAULT_OUTPUT_HEIGHT,
) -> bytes:
    width, height = parse_output_size(width, height)
    bg_rgb = parse_hex_color(bg_hex)
    target_aspect = width / height

    rembg_input = _bytes_for_rembg(image_bytes)
    cutout_bytes = remove(rembg_input, session=_REMBG_SESSION)
    img = Image.open(io.BytesIO(cutout_bytes)).convert("RGBA")

    bbox = _subject_bbox(img)
    crop_box = _crop_box_for_aspect(bbox, img.size, target_aspect)
    cropped = img.crop(crop_box)

    resized = cropped.resize((width, height), Image.Resampling.LANCZOS)

    background = Image.new("RGB", (width, height), bg_rgb)
    background.paste(resized, (0, 0), resized)

    output = io.BytesIO()
    background.save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()
