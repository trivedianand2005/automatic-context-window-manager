from shopapi.core.security import hash_password, verify_password


def test_password_hash_roundtrip():
    stored = hash_password("s3cret-demo")
    assert verify_password("s3cret-demo", stored)
    assert not verify_password("wrong", stored)


def test_login_returns_token(client, demo_user):
    response = client.post("/auth/login", json=demo_user)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_login_rejects_bad_password(client, demo_user):
    response = client.post("/auth/login", json={"username": "demo", "password": "nope"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
