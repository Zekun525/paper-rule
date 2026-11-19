"""Explicit, owner-authenticated manuscript review requests."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import Field, model_validator

from paperrule.domain.models import Record
from paperrule.persistence.store import MemoryStore
from paperrule.review.files import TEXT_SUFFIXES, changed_documents, check_documents


class ManuscriptReviewInput(Record):
    paper_id: str = Field(min_length=1, max_length=101)
    mode: Literal["text", "diff"] = "text"
    filename: str = Field(default="manuscript.tex", min_length=1, max_length=240)
    text: str = Field(default="", max_length=100000)
    section: str = Field(default="", max_length=500)
    task: str = Field(default="", max_length=2000)
    semantic: bool = Field(default=False, strict=True)
    send_to_provider: bool = Field(default=False, strict=True)
    max_semantic_calls: int = Field(default=8, ge=1, le=32, strict=True)

    @model_validator(mode="after")
    def validate_request(self):
        if self.semantic and not self.send_to_provider:
            raise ValueError("AI review requires explicit consent to send manuscript context to the configured provider")
        if self.mode == "diff":
            if self.text:
                raise ValueError("Diff review reads the saved paper project; omit pasted text")
        else:
            if not self.text.strip():
                raise ValueError("Provide manuscript text for review")
            if (any(character in self.filename for character in ("/", chr(92), chr(0), ":"))
                    or self.filename in {".", ".."}
                    or Path(self.filename).suffix.lower() not in TEXT_SUFFIXES):
                raise ValueError("Use a plain .tex, .bib, .md or .txt document name")
        return self


def register_manuscript(app: FastAPI, store: MemoryStore) -> None:
    @app.post("/api/reviews/check")
    def check_manuscript(body: ManuscriptReviewInput):
        with store.locked(wait=5):
            profile = next((paper for paper in store.papers()
                            if paper.paper_id == body.paper_id), None)
        if profile is None:
            raise HTTPException(404, "Paper profile was not found")
        paper_commit = None
        try:
            if body.mode == "diff":
                if not profile.project_path:
                    raise HTTPException(400, "Save the paper project path before reviewing Git changes")
                documents, paper_commit = changed_documents(Path(profile.project_path))
            else:
                documents = [{
                    "path": body.filename, "text": body.text,
                    "sha256": sha256(body.text.encode("utf-8")).hexdigest(),
                }]
            return check_documents(
                store, documents, profile, section=body.section, task=body.task,
                paper_commit=paper_commit, diff_mode=body.mode == "diff",
                semantic=body.semantic, max_semantic_calls=body.max_semantic_calls,
            )
        except (OSError, ValueError) as error:
            raise HTTPException(400, "Review could not run; check the saved paper project and input limits") from error
