import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# isolate the test run: temp database, known secrets, high rate limits
_tmp = tempfile.mkdtemp(prefix="cm_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["API_KEY"] = "test-api-key"
os.environ["JWT_SECRET"] = "test-jwt-secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin-test-pass"
os.environ["RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["PRODUCTION"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_headers(client):
    r = client.post("/auth/login",
                    json={"username": "admin", "password": "admin-test-pass"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _make_user(client, admin_headers, username, role):
    r = client.post("/auth/users", headers=admin_headers,
                    json={"username": username, "password": "password123",
                          "role": role})
    assert r.status_code in (201, 409), r.text
    r = client.post("/auth/login",
                    json={"username": username, "password": "password123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def teacher_headers(client, admin_headers):
    return _make_user(client, admin_headers, "teacher1", "teacher")


@pytest.fixture(scope="session")
def viewer_headers(client, admin_headers):
    return _make_user(client, admin_headers, "viewer1", "viewer")
