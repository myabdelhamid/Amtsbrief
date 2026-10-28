"""Turn an uploaded file into page images for the transcribe step.

PDFs are rendered page by page, so a scanned PDF and a digital one go through
the same vision model. We don't use a PDF's text layer: it can differ from what
is printed on the page, and the transcript must match what the user sees.
"""
from __future__ import annotations

import io

import pypdfium2 as pdfium

DPI = 200  # sharp enough for 7.5 pt footers, small enough to keep requests cheap


def pdf_to_images(pdf_bytes: bytes, dpi: int = DPI) -> list[bytes]:
    """One JPEG per page, in page order."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    images = []
    try:
        for page in pdf:
            # PDF units are points (1/72 inch), so scale = dpi / 72.
            bitmap = page.render(scale=dpi / 72)
            buffer = io.BytesIO()
            bitmap.to_pil().convert("RGB").save(buffer, format="JPEG", quality=90)
            images.append(buffer.getvalue())
    finally:
        pdf.close()
    return images
