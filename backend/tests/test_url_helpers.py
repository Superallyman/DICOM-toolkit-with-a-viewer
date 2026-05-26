from app.utilities.url_helpers import public_api_base_url, public_api_v1_base_url, public_ohif_base_url


class DummyRequest:
    base_url = "http://internal-api:8000/"


def test_public_api_urls_use_base_url_env(monkeypatch):
    monkeypatch.setenv("BASE_URL", "http://localhost:8080/api")
    monkeypatch.setenv("OHIF_PUBLIC_URL", "http://localhost:8080/viewer")

    assert public_api_base_url(DummyRequest()) == "http://localhost:8080/api"
    assert public_api_v1_base_url(DummyRequest()) == "http://localhost:8080/api/v1"
    assert public_ohif_base_url(DummyRequest()) == "http://localhost:8080/viewer"


def test_public_ohif_url_defaults_to_api_viewer(monkeypatch):
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")
    monkeypatch.delenv("OHIF_PUBLIC_URL", raising=False)

    assert public_ohif_base_url(DummyRequest()) == "http://localhost:8000/v1/viewer"
