from fastapi.testclient import TestClient
from app.main import app
from app.config import settings


def test_hosted_auth_and_origin(monkeypatch):
    monkeypatch.setattr(
        settings, "owner_password", "a-long-password-for-this-test-only"
    )
    client = TestClient(app)
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/settings", auth=("owner", "wrong")).status_code == 401
    assert (
        client.get("/api/settings", auth=("owner", settings.owner_password)).status_code
        == 200
    )
    assert (
        client.post(
            "/api/companies",
            json={"ticker": "CACI"},
            auth=("owner", settings.owner_password),
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/companies",
            json={"ticker": "CACI"},
            auth=("owner", settings.owner_password),
            headers={"Sec-Fetch-Site": "cross-site"},
        ).status_code
        == 403
    )


def test_production_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "production", True)
    monkeypatch.setattr(settings, "app_origin", "")
    monkeypatch.setattr(settings, "owner_password", "")
    assert TestClient(app).get("/api/settings").status_code == 503
