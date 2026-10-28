"""preprocess.load_pages, with files built in memory: no real letters needed.

A "scanned PDF" here is what a scanner app makes: pages that are only images,
with no text layer. Pillow writes exactly that with save(format="PDF").
"""
import io

import pytest
from PIL import Image

from pipeline import preprocess
from pipeline.preprocess import UnsupportedFile


def encode(image: Image.Image, fmt: str, **kw) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **kw)
    return buffer.getvalue()


def decode(jpeg: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(jpeg))
    assert image.format == "JPEG"
    return image


def page(width=200, height=100, color="white") -> Image.Image:
    return Image.new("RGB", (width, height), color)


def scanned_pdf(pages: int) -> bytes:
    images = [page(color=c) for c in ["white", "gray", "black"] * pages][:pages]
    return encode(images[0], "PDF", save_all=True, append_images=images[1:], resolution=72)


# ---------- file type ----------

@pytest.mark.parametrize("fmt, expected", [("JPEG", "jpeg"), ("PNG", "png"), ("WEBP", "webp"), ("HEIF", "heic"),
                                           ("PDF", "pdf")])
def test_detects_type_from_content(fmt, expected):
    assert preprocess.detect_type(encode(page(), fmt)) == expected


def test_rejects_unknown_files():
    with pytest.raises(UnsupportedFile):
        preprocess.load_pages(b"PK\x03\x04 this is a zip file")


def test_rejects_empty_file():
    with pytest.raises(UnsupportedFile):
        preprocess.load_pages(b"")


def test_rejects_too_large_file(monkeypatch):
    monkeypatch.setattr(preprocess, "MAX_BYTES", 100)
    with pytest.raises(UnsupportedFile):
        preprocess.load_pages(encode(page(), "PNG"))


# ---------- PDFs ----------

def test_scanned_pdf_gives_one_jpeg_per_page_in_order():
    pages = preprocess.load_pages(scanned_pdf(3))
    assert len(pages) == 3
    # page 1 white, page 2 gray, page 3 black: the order survives
    brightness = [decode(p).convert("L").getpixel((10, 10)) for p in pages]
    assert brightness[0] > brightness[1] > brightness[2]


def test_pdf_is_rendered_at_the_set_dpi():
    # A 200 x 100 pt page at 200 DPI is 200/72 times larger in pixels.
    [jpeg] = preprocess.load_pages(scanned_pdf(1))
    assert decode(jpeg).size == (round(200 * 200 / 72), round(100 * 200 / 72))


def test_too_many_pages_is_rejected(monkeypatch):
    monkeypatch.setattr(preprocess, "MAX_PAGES", 2)
    with pytest.raises(UnsupportedFile, match="3 pages"):
        preprocess.load_pages(scanned_pdf(3))


def test_damaged_pdf_is_rejected():
    with pytest.raises(UnsupportedFile):
        preprocess.load_pages(scanned_pdf(1)[:200])


# ---------- photos ----------

@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP", "HEIF"])
def test_every_photo_format_becomes_one_jpeg(fmt):
    [jpeg] = preprocess.load_pages(encode(page(), fmt))
    assert decode(jpeg).size == (200, 100)


def test_photo_is_turned_upright_from_its_exif_flag():
    # Orientation 6 = "rotate 90° clockwise to view": a phone held upright stores it this way.
    exif = Image.Exif()
    exif[0x0112] = 6
    [jpeg] = preprocess.load_pages(encode(page(200, 100), "JPEG", exif=exif))
    assert decode(jpeg).size == (100, 200)


def test_metadata_like_gps_is_removed():
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # camera make
    exif[0x8825] = {1: "N", 2: (52.0, 31.0, 0.0)}  # GPS info: Berlin
    [jpeg] = preprocess.load_pages(encode(page(), "JPEG", exif=exif))
    assert dict(decode(jpeg).getexif()) == {}


def test_large_photo_is_shrunk_keeping_its_shape():
    [jpeg] = preprocess.load_pages(encode(page(4800, 3600), "JPEG"))
    assert decode(jpeg).size == (preprocess.MAX_SIDE, preprocess.MAX_SIDE * 3 // 4)


def test_small_photo_is_not_enlarged():
    [jpeg] = preprocess.load_pages(encode(page(300, 400), "JPEG"))
    assert decode(jpeg).size == (300, 400)


def test_transparent_png_goes_on_white():
    [jpeg] = preprocess.load_pages(encode(Image.new("RGBA", (50, 50), (0, 0, 0, 0)), "PNG"))
    assert decode(jpeg).convert("L").getpixel((25, 25)) > 245


def test_damaged_photo_is_rejected():
    with pytest.raises(UnsupportedFile):
        preprocess.load_pages(encode(page(), "JPEG")[:50])
