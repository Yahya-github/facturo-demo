"""Turn an uploaded scan (PDF or photo) into model-ready JPEG pages.

A scanned billet is almost never framed tightly: the paper ticket occupies
roughly half a letter-size scan and the rest is blank feeder background. Sending
that whole page to a vision model wastes image tokens on white space and shrinks
the handwriting, which is exactly the part the model has to read. So every page
goes through the same three steps:

  rasterize (PDF only) -> crop to the ink -> downscale to a pixel budget

Cropping typically halves the pixel count on these scans, which both speeds up
inference and raises the effective resolution of the handwriting at any given
budget.

Kept separate from ai_extract so prompt/schema work and image plumbing can
change independently.
"""

import io

import pillow_heif
from PIL import Image, ImageOps

from facturo.i18n import tr

# Ollama's vision backend only reliably decodes common formats (JPEG/PNG/GIF/
# BMP) — it hard-errors on HEIC (the default iPhone photo format) and silently
# misbehaves on WEBP. Normalizing to JPEG here means callers never have to care.
pillow_heif.register_heif_opener()

# PDFs carry no pixels, only vector/scan data at a nominal 72 dpi. 200 dpi is the
# usual scanner setting and keeps handwritten strokes separable; the crop and
# resize below bring the token cost back down.
RENDER_DPI = 200

# Longest-edge cap for what we hand the model. 1400 is empirical, not a guess:
# raising it to 1800 (native resolution for a cropped 200 dpi scan) *lowered*
# extraction accuracy 89% -> 83% and made every page ~6x slower, because the
# extra image tokens crowd the model rather than revealing detail. Lower values
# start losing the handwritten decimals. Re-measure before changing this.
MAX_EDGE = 1400

# A pixel counts as ink below this gray level; a row/column counts as content
# when at least MIN_INK_FRAC of it is ink. The fraction is what makes the crop
# survive scanner noise and the dark border strip on a skewed feed.
_INK_LEVEL = 200
_MIN_INK_FRAC = 0.012
_PAD_FRAC = 0.012          # breathing room so a crop never clips a stroke
_PROJECTION_WIDTH = 200    # crop is measured on a thumbnail — cheap, pure PIL


class ScanRenderError(Exception):
    """User-facing failure; the French message is shown as-is in the UI."""


def _crop_to_ink(im: Image.Image) -> Image.Image:
    """Trim blank scanner margin, keeping everything that holds ink.

    Works off a small thumbnail and a row/column ink projection rather than
    PIL's getbbox(), because getbbox() keys on a single dark pixel and so gives
    up entirely on scans with a noisy or shadowed edge.
    """
    gray = ImageOps.grayscale(im)
    tw = _PROJECTION_WIDTH
    th = gray.resize((tw, max(1, round(tw * gray.height / gray.width))), Image.BILINEAR)
    w, h = th.size
    px = th.load()

    rows = [
        sum(1 for x in range(w) if px[x, y] < _INK_LEVEL) / w > _MIN_INK_FRAC
        for y in range(h)
    ]
    cols = [
        sum(1 for y in range(h) if px[x, y] < _INK_LEVEL) / h > _MIN_INK_FRAC
        for x in range(w)
    ]
    if not any(rows) or not any(cols):
        return im  # blank or inverted page — leave it alone

    y0, y1 = rows.index(True), h - rows[::-1].index(True)
    x0, x1 = cols.index(True), w - cols[::-1].index(True)
    sx, sy = im.width / w, im.height / h
    pad = round(_PAD_FRAC * max(im.size))
    return im.crop((
        max(0, round(x0 * sx) - pad),
        max(0, round(y0 * sy) - pad),
        min(im.width, round(x1 * sx) + pad),
        min(im.height, round(y1 * sy) + pad),
    ))


def _to_jpeg(im: Image.Image) -> bytes:
    im = _crop_to_ink(im.convert("RGB"))
    if max(im.size) > MAX_EDGE:
        scale = MAX_EDGE / max(im.size)
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def band(jpeg_bytes: bytes, top: float, bottom: float) -> bytes:
    """Crop a horizontal band of an already-prepared page and enlarge it.

    Used for the focused second look at a single field: a plate or a date gets
    only a few dozen pixels per character in the whole-page view, which is
    where the cursive 5-vs-9 misreads come from. Zooming the band that holds it
    spends the same token budget on a fraction of the page.
    """
    try:
        with Image.open(io.BytesIO(jpeg_bytes)) as im:
            im.load()
            im = im.convert("RGB")
            y0, y1 = int(im.height * top), int(im.height * bottom)
            crop = im.crop((0, max(0, y0), im.width, min(im.height, y1)))
            if max(crop.size) < MAX_EDGE:
                scale = MAX_EDGE / max(crop.size)
                crop = crop.resize(
                    (round(crop.width * scale), round(crop.height * scale)),
                    Image.LANCZOS,
                )
            buf = io.BytesIO()
            crop.save(buf, format="JPEG", quality=92)
            return buf.getvalue()
    except Exception:
        return jpeg_bytes  # a failed zoom just means the full page is re-used


def is_pdf(raw: bytes) -> bool:
    return raw[:5] == b"%PDF-"


def image_to_jpeg(raw: bytes) -> bytes:
    """One photo (any format Pillow reads, HEIC included) -> one JPEG."""
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            return _to_jpeg(im)
    except Exception:
        raise ScanRenderError(tr("ai.image_unreadable")) from None


def pdf_to_jpegs(raw: bytes, max_pages: int = 40) -> list[bytes]:
    """A scanned PDF -> one JPEG per page.

    These PDFs are batches: the client feeds a stack of paper billets through
    the scanner, so one file holds one billet per page. Callers extract each
    page separately rather than asking the model to read a whole stack at once.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise ScanRenderError(tr("ai.pdf_support_missing")) from None
    try:
        doc = pdfium.PdfDocument(io.BytesIO(raw))
        pages = []
        for i in range(min(len(doc), max_pages)):
            pages.append(_to_jpeg(doc[i].render(scale=RENDER_DPI / 72).to_pil()))
        return pages
    except ScanRenderError:
        raise
    except Exception:
        raise ScanRenderError(tr("ai.pdf_unreadable")) from None


def to_jpegs(raw: bytes) -> list[bytes]:
    """Any supported scan -> the list of page images to run extraction on."""
    if not raw:
        raise ScanRenderError(tr("ai.file_empty"))
    return pdf_to_jpegs(raw) if is_pdf(raw) else [image_to_jpeg(raw)]
