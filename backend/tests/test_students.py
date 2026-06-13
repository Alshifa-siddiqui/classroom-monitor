def test_student_crud_and_search(client, admin_headers):
    r = client.post("/students", json={"name": "Alice Carter"}, headers=admin_headers)
    assert r.status_code == 201
    alice = r.json()
    assert alice["name"] == "Alice Carter"
    assert alice["enrolled"] is False
    assert alice["embedding_count"] == 0

    # duplicate name (case-insensitive) rejected
    r = client.post("/students", json={"name": "alice carter"}, headers=admin_headers)
    assert r.status_code == 409

    r = client.post("/students", json={"name": "Bob Stone"}, headers=admin_headers)
    assert r.status_code == 201
    bob = r.json()

    # search
    r = client.get("/students?search=alice", headers=admin_headers)
    assert [s["name"] for s in r.json()] == ["Alice Carter"]

    # rename, with duplicate protection
    r = client.put(f"/students/{bob['id']}", json={"name": "Alice Carter"},
                   headers=admin_headers)
    assert r.status_code == 409
    r = client.put(f"/students/{bob['id']}", json={"name": "Robert Stone"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Robert Stone"

    # delete
    assert client.delete(f"/students/{bob['id']}",
                         headers=admin_headers).status_code == 204
    r = client.get("/students?search=Robert", headers=admin_headers)
    assert r.json() == []


def test_student_name_validation(client, admin_headers):
    r = client.post("/students", json={"name": ""}, headers=admin_headers)
    assert r.status_code == 422
    r = client.post("/students", json={"name": "<script>x</script>"},
                    headers=admin_headers)
    assert r.status_code == 422


def test_enroll_missing_student(client, admin_headers):
    assert client.post("/students/99999/enroll",
                       headers=admin_headers).status_code == 404


def test_unified_student_account_workflow(client, admin_headers):
    # 1. register with email+password -> linked account + auto student ID
    r = client.post("/students", headers=admin_headers,
                    json={"name": "Carla Reyes", "email": "carla@school.edu",
                          "password": "carlapass123"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["student_code"] and body["student_code"].startswith("STU-")
    assert body["email"] == "carla@school.edu"
    assert body["has_account"] is True
    assert body["registered_at"] is not None

    # duplicate email rejected
    r = client.post("/students", headers=admin_headers,
                    json={"name": "Carla Two", "email": "carla@school.edu",
                          "password": "carlapass123"})
    assert r.status_code == 409

    # email without password rejected
    r = client.post("/students", headers=admin_headers,
                    json={"name": "Half Account", "email": "half@school.edu"})
    assert r.status_code == 422

    # 2. student logs in with email and password
    r = client.post("/auth/login", json={"username": "carla@school.edu",
                                         "password": "carlapass123"})
    assert r.status_code == 200
    login = r.json()
    assert login["role"] == "student"
    assert login["student_id"] == body["id"]
    sh = {"Authorization": f"Bearer {login['token']}"}

    # 3. student sees own profile/history
    r = client.get("/me/student", headers=sh)
    assert r.status_code == 200
    profile = r.json()
    assert profile["student_code"] == body["student_code"]
    assert profile["email"] == "carla@school.edu"
    assert "attendance_percentage" in profile
    assert "emotion_stats" in profile

    # 4. student cannot access staff features
    assert client.get("/students", headers=sh).status_code == 403
    assert client.get("/analytics", headers=sh).status_code == 403
    assert client.get("/reports/attendance", headers=sh).status_code == 403

    # 5. teacher-level profile endpoint works
    r = client.get(f"/students/{body['id']}/profile", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Carla Reyes"

    # 6. deleting the student removes the login too
    assert client.delete(f"/students/{body['id']}",
                         headers=admin_headers).status_code == 204
    r = client.post("/auth/login", json={"username": "carla@school.edu",
                                         "password": "carlapass123"})
    assert r.status_code == 401
