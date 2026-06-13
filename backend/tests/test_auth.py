def test_health_unauthenticated(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_login_wrong_password(client):
    r = client.post("/auth/login",
                    json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_success_and_me(client, admin_headers):
    r = client.get("/auth/me", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"username": "admin", "role": "admin", "student_id": None}


def test_no_token_rejected(client):
    assert client.get("/students").status_code == 401


def test_garbage_token_rejected(client):
    r = client.get("/students", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_legacy_api_key_still_works(client):
    r = client.get("/students", headers={"X-API-Key": "test-api-key"})
    assert r.status_code == 200


def test_viewer_dashboard_only(client, viewer_headers):
    assert client.get("/analytics", headers=viewer_headers).status_code == 200
    assert client.get("/students", headers=viewer_headers).status_code == 403
    assert client.get("/attendance", headers=viewer_headers).status_code == 403
    assert client.get("/reports/attendance", headers=viewer_headers).status_code == 403
    assert client.post("/start-session", json={"name": "x"},
                       headers=viewer_headers).status_code == 403


def test_teacher_views_but_cannot_manage(client, teacher_headers):
    assert client.get("/students", headers=teacher_headers).status_code == 200
    assert client.get("/attendance", headers=teacher_headers).status_code == 200
    assert client.get("/analytics", headers=teacher_headers).status_code == 200
    assert client.post("/students", json={"name": "Nope"},
                       headers=teacher_headers).status_code == 403
    assert client.post("/start-session", json={"name": "x"},
                       headers=teacher_headers).status_code == 403
    assert client.get("/auth/users", headers=teacher_headers).status_code == 403


def test_signup_creates_viewer(client, admin_headers):
    r = client.post("/auth/signup",
                    json={"username": "newkid@example.com",
                          "password": "password123"})
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "viewer"
    headers = {"Authorization": f"Bearer {body['token']}"}
    # viewer permissions immediately
    assert client.get("/analytics", headers=headers).status_code == 200
    assert client.get("/students", headers=headers).status_code == 403
    # duplicate signup rejected
    r = client.post("/auth/signup",
                    json={"username": "NewKid@Example.com",
                          "password": "password123"})
    assert r.status_code == 409
    # case-insensitive login works
    r = client.post("/auth/login",
                    json={"username": "NEWKID@example.com",
                          "password": "password123"})
    assert r.status_code == 200


def test_role_promotion(client, admin_headers):
    r = client.post("/auth/signup",
                    json={"username": "promote.me", "password": "password123"})
    assert r.status_code == 201
    users = client.get("/auth/users", headers=admin_headers).json()
    uid = next(u["id"] for u in users if u["username"] == "promote.me")
    r = client.put(f"/auth/users/{uid}", headers=admin_headers,
                   json={"role": "teacher"})
    assert r.status_code == 200 and r.json()["role"] == "teacher"
    # promoted permissions apply on next login
    token = client.post("/auth/login", json={
        "username": "promote.me", "password": "password123"}).json()["token"]
    r = client.get("/students", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # invalid role rejected
    r = client.put(f"/auth/users/{uid}", headers=admin_headers,
                   json={"role": "superuser"})
    assert r.status_code == 422


def test_user_management(client, admin_headers):
    r = client.post("/auth/users", headers=admin_headers,
                    json={"username": "tempuser", "password": "password123",
                          "role": "viewer"})
    assert r.status_code == 201
    uid = r.json()["id"]
    # duplicate username rejected
    r = client.post("/auth/users", headers=admin_headers,
                    json={"username": "tempuser", "password": "password123",
                          "role": "viewer"})
    assert r.status_code == 409
    # weak password rejected by validation
    r = client.post("/auth/users", headers=admin_headers,
                    json={"username": "weak", "password": "short", "role": "viewer"})
    assert r.status_code == 422
    assert client.delete(f"/auth/users/{uid}", headers=admin_headers).status_code == 204
