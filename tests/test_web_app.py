from owner_client import TestClient

from paperrule.api.app import create_app


def test_workbench_and_assets_are_served_alongside_the_real_api(tmp_path):
    bundle = tmp_path / "synthetic-web"
    assets = bundle / "assets"
    assets.mkdir(parents=True)
    (bundle / "index.html").write_text(
        "<!doctype html><title>Synthetic PaperRule workbench</title>",
        encoding="utf-8",
    )
    (assets / "app.js").write_text(
        "window.syntheticPaperRule = true;", encoding="utf-8",
    )
    memory = tmp_path / "private-memory"
    client = TestClient(create_app(memory, web_root=bundle))
    home = client.get("/")
    assert home.status_code == 200
    assert "Synthetic PaperRule workbench" in home.text
    assert "text/html" in home.headers["content-type"]
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert asset.text == "window.syntheticPaperRule = true;"
    assert client.get("/api/health").json()["memory_path"] == str(memory.resolve())
    assert client.get("/api/rules").json() == []
    assert client.get("/api/not-a-real-endpoint").status_code == 404


def test_web_server_does_not_expose_private_attachments(tmp_path):
    bundle = tmp_path / "synthetic-web"
    bundle.mkdir()
    (bundle / "index.html").write_text("Synthetic workbench", encoding="utf-8")
    memory = tmp_path / "private-memory"
    client = TestClient(create_app(memory, web_root=bundle))
    (memory / "attachments" / "synthetic-private.txt").write_text(
        "Synthetic private evidence, never a public web asset.", encoding="utf-8",
    )
    assert client.get("/attachments/synthetic-private.txt").status_code == 404
    assert client.get("/manifest.json").status_code == 404
    assert client.get("/../private-memory/manifest.json").status_code == 404


def test_missing_web_bundle_is_explicit_without_creating_it(tmp_path):
    missing_bundle = tmp_path / "not-built"
    client = TestClient(create_app(tmp_path / "private-memory", web_root=missing_bundle))
    response = client.get("/")
    assert response.status_code == 503
    assert "网页尚未构建" in response.text
    assert client.get("/api/health").status_code == 200
    assert not missing_bundle.exists()
