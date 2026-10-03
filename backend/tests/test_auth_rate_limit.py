"""Password guessing is slowed down per e-mail address; a blocked address learns nothing from the answer."""

import os
import uuid

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _register():
    email = f"rl_{uuid.uuid4().hex[:10]}@test.example"
    password = uuid.uuid4().hex
    resp = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "full_name": "RL", "organization_name": f"RL {email}"},
    )
    assert resp.status_code == 200, resp.text
    return email, password


def _login(email, password):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": password})


def test_ten_failures_lock_the_address_even_for_the_right_password():
    email, password = _register()
    for _ in range(10):
        assert _login(email, "wrong-password").status_code == 401
    blocked = _login(email, "wrong-password")
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    assert _login(email, password).status_code == 429  # the right password is not confirmed while blocked


def test_other_addresses_and_successful_logins_are_not_affected():
    email, password = _register()
    other, other_password = _register()
    for _ in range(5):
        assert _login(email, "nope").status_code == 401
    assert _login(email, password).status_code == 200  # a success resets the counter
    for _ in range(9):
        assert _login(email, "nope").status_code == 401
    assert _login(email, password).status_code == 200
    assert _login(other, other_password).status_code == 200
