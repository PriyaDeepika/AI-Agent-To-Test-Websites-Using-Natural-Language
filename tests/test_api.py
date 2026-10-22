def test_index_and_health(client):
    assert client.get("/").status_code == 200
    h = client.get("/api/health").get_json()
    assert h["llm_planner"] is False and "chromium_installed" in h


def test_examples_flag_real_vs_local(client):
    ex = client.get("/api/examples").get_json()
    assert any(e["real"] for e in ex) and any(not e["real"] for e in ex)


def test_plan_preview_runs_no_browser(client):
    r = client.post("/api/plan", json={"instruction": "Open eBay, search for boots, add it to the cart"})
    d = r.get_json()
    assert r.status_code == 200 and [s["action"] for s in d["steps"]] == ["open", "search", "add_to_cart"]
    assert d["planner"] == "rules"


def test_plan_preview_rejects_garbage_and_empty(client):
    assert client.post("/api/plan", json={"instruction": "zzz qqq"}).status_code == 422
    assert client.post("/api/plan", json={"instruction": ""}).status_code == 400


def test_run_rejects_unsafe_url_and_empty(client):
    assert client.post("/api/runs", json={"instruction": "open it", "url": "file:///etc/passwd"}).status_code == 400
    assert client.post("/api/runs", json={"instruction": "  "}).status_code == 400
    assert client.post("/api/runs", json={"instruction": "x" * 2001}).status_code == 400


def test_unknown_run_404_and_respond_conflict(client):
    assert client.get("/api/runs/nope").status_code == 404
    assert client.post("/api/runs/nope/respond", json={}).status_code == 409
    assert client.get("/api/runs/nope/report.json").status_code == 404


def test_screenshot_path_traversal_blocked(client):
    assert client.get("/api/runs/x/screenshots/../../../etc/passwd").status_code in (400, 404)
