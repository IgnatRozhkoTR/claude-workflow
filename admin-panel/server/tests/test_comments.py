"""Tests for comment CRUD, resolve, and list routes."""
from testing_utils import add_comment

BASE = "/api/ws/test-project/feature/test/comments"


def test_add_comment(client, workspace):
    r = client.post(BASE, json={"scope": "review", "text": "Fix this"})
    assert r.status_code == 200
    assert r.json["ok"]
    assert r.json["id"]


def test_add_comment_missing_fields(client, workspace):
    r = client.post(BASE, json={"scope": "review"})
    assert r.status_code == 400

    r = client.post(BASE, json={"text": "Some text"})
    assert r.status_code == 400


def test_add_comment_with_file_location(client, workspace):
    r = client.post(BASE, json={
        "scope": "review",
        "text": "Check this line",
        "file_path": "src/main.py",
        "line_start": 5,
        "line_end": 10,
        "line_hash": "abc123",
    })
    assert r.status_code == 200
    assert r.json["ok"]

    comment_id = r.json["id"]
    r = client.get(BASE)
    comments = r.json["comments"]
    comment = next(c for c in comments if c["id"] == comment_id)
    assert comment["file_path"] == "src/main.py"
    assert comment["line_start"] == 5
    assert comment["line_end"] == 10
    assert comment["line_hash"] == "abc123"


def test_list_comments(client, workspace):
    add_comment(workspace["id"], scope="review", text="First")
    add_comment(workspace["id"], scope="review", text="Second")

    r = client.get(BASE)
    assert r.status_code == 200
    assert len(r.json["comments"]) == 2


def test_list_comments_filter_scope(client, workspace):
    add_comment(workspace["id"], scope="review", text="Review comment")
    add_comment(workspace["id"], scope="phase", text="Phase comment")

    r = client.get(BASE, query_string={"scope": "review"})
    assert r.status_code == 200
    comments = r.json["comments"]
    assert len(comments) == 1
    assert comments[0]["scope"] == "review"


def test_list_comments_filter_resolved(client, workspace):
    resolved_id = add_comment(workspace["id"], scope="review", text="Resolved comment")
    add_comment(workspace["id"], scope="review", text="Open comment")

    client.put(f"{BASE}/{resolved_id}/resolve", json={"resolved": True})

    r = client.get(BASE, query_string={"resolved": "false"})
    assert r.status_code == 200
    comments = r.json["comments"]
    assert len(comments) == 1
    assert comments[0]["resolved"] is False


def test_resolve_comment(client, workspace):
    comment_id = add_comment(workspace["id"], scope="review", text="Needs fix")

    r = client.put(f"{BASE}/{comment_id}/resolve", json={"resolved": True})
    assert r.status_code == 200
    assert r.json["ok"]

    r = client.get(BASE)
    comment = next(c for c in r.json["comments"] if c["id"] == comment_id)
    assert comment["resolved"] is True
    assert comment["resolved_at"] is not None


def test_unresolve_comment(client, workspace):
    comment_id = add_comment(workspace["id"], scope="review", text="Needs fix")

    client.put(f"{BASE}/{comment_id}/resolve", json={"resolved": True})
    r = client.put(f"{BASE}/{comment_id}/resolve", json={"resolved": False})
    assert r.status_code == 200
    assert r.json["ok"]

    r = client.get(BASE)
    comment = next(c for c in r.json["comments"] if c["id"] == comment_id)
    assert comment["resolved"] is False
    assert comment["resolved_at"] is None


def test_resolve_comment_not_found(client, workspace):
    r = client.put(f"{BASE}/99999/resolve", json={"resolved": True})
    assert r.status_code == 404
