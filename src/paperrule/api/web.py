"""Serve the built workbench without exposing private memory files."""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles


def register_web(app: FastAPI, web_root: Path | None = None) -> None:
    if web_root is not None:
        candidates = [web_root]
    elif configured := os.environ.get("PAPERRULE_WEB_ROOT"):
        candidates = [Path(configured).expanduser()]
    else:
        source = Path(__file__).resolve()
        candidates = [
            source.parents[1] / "web",
            source.parents[3] / "frontend" / "dist",
        ]
    bundle = next(
        (candidate.resolve() for candidate in candidates if (candidate / "index.html").is_file()),
        None,
    )
    if bundle is not None:
        app.mount("/", StaticFiles(directory=bundle, html=True), name="workbench")
        return

    @app.get("/", include_in_schema=False)
    def missing_workbench():
        return HTMLResponse(
            "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<title>PaperRule 网页尚未构建</title>"
            "<h1>PaperRule 网页尚未构建</h1>"
            "<p>请按照安装指南构建网页，然后重新启动 PaperRule 服务。</p>"
            "<p>你的私有记忆不会因此被更改。</p></html>",
            status_code=503,
        )
