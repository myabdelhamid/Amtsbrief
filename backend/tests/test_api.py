"""The HTTP API with the in-memory store and a fake analyze(): no Google calls."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from icalendar import Calendar

from app import main
from app.store import MemoryStore
from pipeline.analyze import NoTextFound
from pipeline.preprocess import UnsupportedFile
from pipeline.schemas import Analysis, Cited, Claim, Extraction, RawDeadline, Transcript
from pipeline.validate import validate

TRANSCRIPT = Transcript(lines={
    "P1-L1": "Ordnungsamt Musterstadt",
    "P1-L2": "Musterstadt, den 02.10.2099",
    "P1-L3": "Bitte zahlen Sie 35,00 € innerhalb einer Woche.",
})
EXTRACTION = Extraction(
    letter_type="fine",
    sender=Cited(value="Ordnungsamt Musterstadt", quote="Ordnungsamt Musterstadt", lines=["P1-L1"]),
    letter_date=Cited(value="02.10.2099", quote="den 02.10.2099", lines=["P1-L2"]),
    amount=Cited(value="35,00 €", quote="zahlen Sie 35,00 €", lines=["P1-L3"]),
    deadlines=[RawDeadline(phrase="innerhalb einer Woche", kind="relative", amount=1, unit="weeks",
                           anchor="letter_date", summary="Pay the 35,00 € fine.", purpose="payment",
                           lines=["P1-L3"])],
    explanation=[Claim(text="You were fined 35 euros.", lines=["P1-L3"])],
)
ANALYSIS = Analysis(transcript=TRANSCRIPT, result=validate(EXTRACTION, TRANSCRIPT), pages=1)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("AMTSBRIEF_DEV_USER", "alice")
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setattr(main, "analyze", lambda client, data: ANALYSIS)
    main.app.state.store = MemoryStore()
    main.app.state.client = None
    with TestClient(main.app) as client:
        yield client
    del main.app.state.store, main.app.state.client


def upload(api, data=b"%PDF fake"):
    return api.post("/api/letters", files={"file": ("letter.pdf", data, "application/pdf")})


def test_upload_stores_and_returns_the_letter(api):
    response = upload(api)
    assert response.status_code == 200
    letter = response.json()
    assert letter["analysis"]["result"]["extraction"]["sender"]["value"] == "Ordnungsamt Musterstadt"
    assert api.get(f"/api/letters/{letter['id']}").json() == letter


def test_list_has_summaries_newest_first(api):
    first, second = upload(api).json(), upload(api).json()
    rows = api.get("/api/letters").json()
    assert [row["id"] for row in rows] == [second["id"], first["id"]]
    assert rows[0]["next_deadline"] == "2099-10-09"
    assert rows[0]["warned"] is False


def test_users_only_see_their_own_letters(api, monkeypatch):
    letter = upload(api).json()
    monkeypatch.setenv("AMTSBRIEF_DEV_USER", "bob")
    assert api.get("/api/letters").json() == []
    assert api.get(f"/api/letters/{letter['id']}").status_code == 404
    assert api.delete(f"/api/letters/{letter['id']}").status_code == 404


def test_delete(api):
    letter = upload(api).json()
    assert api.delete(f"/api/letters/{letter['id']}").status_code == 204
    assert api.get(f"/api/letters/{letter['id']}").status_code == 404


def test_without_sign_in_is_401(api, monkeypatch):
    monkeypatch.delenv("AMTSBRIEF_DEV_USER")
    assert api.get("/api/letters").status_code == 401


def test_dev_user_is_ignored_on_cloud_run(api, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "amtsbrief")
    assert api.get("/api/letters").status_code == 401


def test_daily_limit(api, monkeypatch):
    monkeypatch.setattr(main, "DAILY_LIMIT", 2)
    assert [upload(api).status_code for _ in range(3)] == [200, 200, 429]


@pytest.mark.parametrize("error, status", [(UnsupportedFile("not a PDF or photo"), 415), (NoTextFound(), 422)])
def test_unreadable_uploads(api, monkeypatch, error, status):
    def fail(client, data):
        raise error
    monkeypatch.setattr(main, "analyze", fail)
    assert upload(api).status_code == status
    assert api.get("/api/letters").json() == []  # nothing stored


def test_deadline_as_ics(api):
    letter = upload(api).json()
    response = api.get(f"/api/letters/{letter['id']}/deadlines/0.ics")
    assert response.headers["content-type"].startswith("text/calendar")
    [event] = Calendar.from_ical(response.content).walk("VEVENT")
    assert event.decoded("dtstart") == date(2099, 10, 9)
    assert str(event["summary"]) == "Payment due: Pay the 35,00 € fine."
    assert api.get(f"/api/letters/{letter['id']}/deadlines/5.ics").status_code == 404


def test_calendar_feed_needs_no_sign_in_but_a_secret(api, monkeypatch):
    upload(api)
    upload(api)
    url = api.get("/api/calendar").json()["url"]
    assert api.get("/api/calendar").json()["url"] == url  # the same token every time
    monkeypatch.delenv("AMTSBRIEF_DEV_USER")
    feed = api.get(url)
    assert feed.status_code == 200
    assert len(Calendar.from_ical(feed.content).walk("VEVENT")) == 2
    assert api.get("/api/calendar/wrong-token.ics").status_code == 404


def test_config_tells_the_frontend_about_dev_mode(api, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo")
    config = api.get("/api/config").json()
    assert config["dev"] is True
    assert config["firebase"]["projectId"] == "demo"
    assert config["firebase"]["authDomain"] == "demo.firebaseapp.com"
    monkeypatch.delenv("AMTSBRIEF_DEV_USER")
    assert api.get("/api/config").json()["dev"] is False
