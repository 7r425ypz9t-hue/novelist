"""«أجهزتي»: a writer sees each signed-in device and can sign any of them out; never someone else's."""

from nis.routers.auth import describe_device

MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 Edg/126.0"


def _login(client, w, ua):
    r = client.post("/v1/auth/login", json={"email": w.email, "password": "correct-horse-1"}, headers={"user-agent": ua})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_device_labels_are_readable():
    assert describe_device(MAC) == "Safari · macOS"
    assert describe_device(WIN) == "Edge · Windows"
    assert "غير معروف" in describe_device("")


def test_list_revoke_one_and_revoke_others(client, writer, other):
    laptop = _login(client, writer, MAC)
    office = _login(client, writer, WIN)
    items = client.get("/v1/auth/sessions", headers=laptop).json()["items"]
    devices = {i["device"] for i in items}
    assert {"Safari · macOS", "Edge · Windows"} <= devices and len(items) == 3
    assert [i["current"] for i in items].count(True) == 1
    assert next(i for i in items if i["current"])["device"] == "Safari · macOS"

    # someone else's device is indistinguishable from a missing one
    office_id = next(i["id"] for i in items if i["device"] == "Edge · Windows")
    assert other.delete(f"/v1/auth/sessions/{office_id}").status_code == 404
    assert client.get("/v1/auth/me", headers=office).status_code == 200

    # the laptop signs the office computer out — it stops working at once
    assert client.request("DELETE", f"/v1/auth/sessions/{office_id}", headers=laptop).status_code == 204
    assert client.get("/v1/auth/me", headers=office).status_code == 401

    # «sign out everywhere else» keeps only the device that asked
    assert client.post("/v1/auth/sessions/revoke-others", headers=laptop).json()["revoked"] == 1   # the original
    assert writer.get("/v1/auth/me").status_code == 401
    left = client.get("/v1/auth/sessions", headers=laptop).json()["items"]
    assert len(left) == 1 and left[0]["current"]
