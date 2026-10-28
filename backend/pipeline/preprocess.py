"""Turn an uploaded file into page images for the transcribe step.

Accepted: PDFs (digital or scanned), JPEG, PNG, WebP and HEIC (iPhone photos).
Every page comes out as a JPEG, so the transcribe step only ever sees one format.

- The file type is read from the file's first bytes, not its name: a renamed or
  mislabelled upload still works, and a non-image can't sneak in as "letter.jpg".
- PDFs are rendered page by page, so a scanned PDF (pages that are only images)
  and a digital one go through the same vision model. We don't use a PDF's text
  layer: it can differ from what is printed, and the transcript must match the page.
- Photos are turned upright using their EXIF orientation (phones store a rotation
  flag instead of rotating the pixels), shrunk to MAX_SIDE, and re-encoded. The
  re-encoded JPEG has no EXIF, so the GPS location and camera data never leave here.
- Anything unreadable, too large or too long raises UnsupportedFile with a message
  that can be shown to the user.
"""
from __future__ import annotations

import io

import pillow_heif
import pypdfium2 as pdfium
from PIL import Image, ImageOps, UnidentifiedImageError

pillow_heif.register_heif_opener()  # lets Image.open read HEIC/HEIF

DPI = 200  # PDF render resolution: sharp enough for 7.5 pt footers, small enough to keep requests cheap
MAX_SIDE = 2400  # longest side of a photo in pixels; a phone photo is often 4000+
MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 10
JPEG_QUALITY = 90


class UnsupportedFile(ValueError):
    """The upload can't be turned into page images. The message is safe to show the user."""


def detect_type(data: bytes) -> str:
    """'pdf', 'jpeg', 'png', 'webp' or 'heic', from the file's magic bytes."""
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    # HEIC: bytes 4-8 are 'ftyp', then a brand such as 'heic' or 'mif1'.
    if data[4:8] == b"ftyp" and data[8:12] in {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}:
        return "heic"
    raise UnsupportedFile("This file type isn't supported. Upload a PDF or a photo (JPEG, PNG, WebP or HEIC).")


def load_pages(data: bytes) -> list[bytes]:
    """One JPEG per page, in page order: every page of a PDF, or the one photo."""
    if not data:
        raise UnsupportedFile("The file is empty.")
    if len(data) > MAX_BYTES:
        raise UnsupportedFile(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if detect_type(data) == "pdf":
        return pdf_to_images(data)
    return [photo_to_jpeg(data)]


def pdf_to_images(pdf_bytes: bytes, dpi: int = DPI) -> list[bytes]:
    """Render each PDF page to a JPEG. Works the same for scanned and digital PDFs."""
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
    except pdfium.PdfiumError as error:
        # Raised for damaged files and for password-protected ones.
        raise UnsupportedFile("This PDF can't be opened. It may be damaged or password-protected.") from error
    try:
        if len(pdf) == 0:
            raise UnsupportedFile("This PDF has no pages.")
        if len(pdf) > MAX_PAGES:
            raise UnsupportedFile(f"This PDF has {len(pdf)} pages; the limit is {MAX_PAGES}.")
        images = []
        for page in pdf:
            # PDF units are points (1/72 inch), so scale = dpi / 72. pdfium applies the
            # page's /Rotate flag, so sideways scans come out the way a viewer shows them.
            bitmap = page.render(scale=dpi / 72)
            images.append(_to_jpeg(bitmap.to_pil()))
        return images
    finally:
        pdf.close()


def photo_to_jpeg(data: bytes) -> bytes:
    """An upright, at most MAX_SIDE pixels, metadata-free JPEG of a photo."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as error:
        raise UnsupportedFile("This image can't be read. It may be damaged.") from error
    image = ImageOps.exif_transpose(image)
    image.thumbnail((MAX_SIDE, MAX_SIDE))  # shrinks in place, keeps the aspect ratio, never enlarges
    return _to_jpeg(image)


def _to_jpeg(image: Image.Image) -> bytes:
    """Encode as RGB JPEG. No exif= argument, so no metadata is written.

    Transparent pixels (a PNG screenshot) go on white paper, not black.
    """
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        image = Image.new("RGB", rgba.size, "white")
        image.paste(rgba, mask=rgba.getchannel("A"))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()
