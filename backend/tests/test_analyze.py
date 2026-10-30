"""analyze() with a fake model: checks the wiring, not the model."""
import io

import pytest
from PIL import Image

from pipeline import analyze as analyze_module
from pipeline.analyze import NoTextFound, analyze
from pipeline.preprocess import UnsupportedFile
from pipeline.schemas import ValidatedResult


def pdf(pages: int) -> bytes:
    """A scanned-style PDF; each page a different grey, so the fake can tell them apart."""
    images = [Image.new("RGB", (200, 100), (40 * n, 40 * n, 40 * n)) for n in range(pages)]
    buffer = io.BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


@pytest.fixture
def fake_model(monkeypatch):
    """Transcribes each page as 'L1: page <brightness>' and records what extraction saw."""
    seen = {}

    def fake_transcribe(client, image_bytes):
        brightness = Image.open(io.BytesIO(image_bytes)).convert("L").getpixel((5, 5))
        return f"L1: page {brightness // 40}\nL2: Bitte zahlen Sie 35,00 €."

    def fake_extract_and_validate(client, transcript):
        seen["transcript"] = transcript
        return ValidatedResult.model_construct(unsure=[], deadlines=[], suspicious=[])

    monkeypatch.setattr(analyze_module, "transcribe", fake_transcribe)
    monkeypatch.setattr(analyze_module, "extract_and_validate", fake_extract_and_validate)
    return seen


def test_pages_are_joined_in_order(fake_model):
    analysis = analyze(None, pdf(4))
    assert analysis.pages == 4
    assert [line for line_id, line in analysis.transcript.lines.items() if line_id.endswith("-L1")] == [
        "page 0", "page 1", "page 2", "page 3"]
    assert list(analysis.transcript.lines)[:3] == ["P1-L1", "P1-L2", "P2-L1"]


def test_extraction_gets_the_joined_transcript(fake_model):
    analysis = analyze(None, pdf(2))
    assert fake_model["transcript"] == analysis.transcript


def test_blank_pages_raise_no_text_found(monkeypatch, fake_model):
    monkeypatch.setattr(analyze_module, "transcribe", lambda client, image: "```\n```")
    with pytest.raises(NoTextFound):
        analyze(None, pdf(1))


def test_unreadable_file_is_rejected_before_any_model_call(fake_model):
    with pytest.raises(UnsupportedFile):
        analyze(None, b"not a letter")
    assert "transcript" not in fake_model
