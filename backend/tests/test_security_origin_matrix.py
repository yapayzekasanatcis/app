"""Independent CORS origin matrix regression checks."""
import os

import requests
from dotenv import load_dotenv


load_dotenv("/app/backend/.env")


def _base_url() -> str:
    with open("/app/frontend/.env", encoding="utf-8") as frontend_env:
        for line in frontend_env:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _base_url()
ALLOWED_ORIGINS = [
    "https://asistan-nova.preview.emergentagent.com",
    "https://novaasistan.com",
    "https://www.novaasistan.com",
]


def test_cors_allowed_origins_reflect_exact_with_credentials():
    for origin in ALLOWED_ORIGINS:
        response = requests.get(f"{BASE_URL}/api/", headers={"Origin": origin}, timeout=30)
        assert response.status_code == 200
        assert response.headers.get("Access-Control-Allow-Origin") == origin
        assert response.headers.get("Access-Control-Allow-Credentials") == "true"
        assert response.headers.get("Access-Control-Allow-Origin") != "*"


def test_cors_unexpected_origin_get_denied_without_credentials_reflection():
    evil_origin = "https://evil.example"
    response = requests.get(f"{BASE_URL}/api/", headers={"Origin": evil_origin}, timeout=30)
    assert response.status_code == 403
    assert response.headers.get("Access-Control-Allow-Origin") != evil_origin
    assert response.headers.get("Access-Control-Allow-Credentials") != "true"


def test_cors_unexpected_origin_preflight_effective_browser_denial():
    evil_origin = "https://evil.example"
    response = requests.options(
        f"{BASE_URL}/api/notes",
        headers={
            "Origin": evil_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
        timeout=30,
    )
    acao = response.headers.get("Access-Control-Allow-Origin")
    acac = response.headers.get("Access-Control-Allow-Credentials")

    assert acao != evil_origin
    assert acac != "true"


def test_api_without_origin_uses_primary_frontend_origin_header():
    response = requests.get(f"{BASE_URL}/api/", timeout=30)
    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == os.environ["FRONTEND_URL"]
