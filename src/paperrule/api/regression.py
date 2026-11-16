from __future__ import annotations

import json
import re
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from paperrule.domain.models import RegressionCase
from paperrule.persistence.store import MemoryStore
from paperrule.review.regression import reports, run_stored_cases


class RegressionRunInput(BaseModel):
    paper_id: str = ""


def register_regression(app: FastAPI, store: MemoryStore) -> None:
    @app.get("/api/regression/cases")
    def cases():
        return store.regressions()

    @app.post("/api/regression/cases")
    def save_case(body: RegressionCase):
        try:
            with store.locked():
                store.save_regression(body)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return body

    @app.get("/api/regression/runs")
    def runs():
        return reports(store)

    @app.post("/api/regression/runs")
    def run(body: RegressionRunInput):
        try:
            return run_stored_cases(store, body.paper_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/regression/runs/{run_id}/report")
    def report(run_id: str, format: Literal["json", "markdown"] = "json"):
        recorded = next((item for item in reports(store) if item["run_id"] == run_id), None)
        if recorded is None:
            raise HTTPException(404, "Regression run not found")
        if format == "json":
            return JSONResponse(
                recorded,
                headers={"Content-Disposition": 'attachment; filename="paperrule-regression.json"'},
            )
        serialized = json.dumps(recorded, ensure_ascii=False, indent=2)
        longest_fence = max(
            (len(part) for part in re.findall(chr(96) + "+", serialized)), default=0,
        )
        fence = chr(96) * max(3, longest_fence + 1)
        lines = [
            "# PaperRule regression report", "",
            "- Status: " + recorded["status"],
            "- Total: " + str(recorded["total"]),
            "- Passed: " + str(recorded["passed"]),
            "- Failed: " + str(recorded["failed"]),
            "- Unavailable: " + str(recorded["unavailable"]),
            "", fence + "json", serialized, fence, "",
        ]
        return PlainTextResponse(
            chr(10).join(lines), media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="paperrule-regression.md"'},
        )
