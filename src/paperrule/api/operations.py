from __future__ import annotations

import base64
import binascii
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from paperrule.domain.models import ReviewerProfile, ReviewReport, RuleRecord
from paperrule.governance.service import ConflictError, Governance
from paperrule.ingestion.pipeline import MAX_BYTES, ingest_bytes
from paperrule.persistence.store import MemoryStore
from paperrule.sync.git import SyncError


class SourceInput(BaseModel):
    filename: str
    content_base64: str = Field(max_length=36_000_000)
    reviewer_id: str = 'author'
    reviewer_role: str = 'author'
    paper_id: str | None = None
    kind: str = 'text'
    intent: str = ''


class ProposalInput(BaseModel):
    rule: RuleRecord
    operation: str = 'create'
    feedback_ids: list[str] = Field(default_factory=list)
    additional_rules: list[RuleRecord] = Field(default_factory=list)


class RestoreInput(BaseModel):
    commit: str
    baseline_commit: str | None = None


class RevertInput(BaseModel):
    version: int = Field(ge=1)


def register_operations(app: FastAPI, store: MemoryStore, gov: Governance) -> None:
    @app.get('/api/reviews')
    def reviews():
        return store.reviews()

    @app.get('/api/reviews/{review_id}/report')
    def review_report(review_id: str, format: Literal["json", "markdown"] = "json"):
        from paperrule.review.exporting import markdown_report
        report = next((item for item in store.reviews() if item.review_id == review_id), None)
        if report is None:
            raise HTTPException(404, "Review report not found")
        if format == "json":
            return JSONResponse(
                report.model_dump(mode="json"),
                headers={"Content-Disposition": 'attachment; filename="paperrule-review.json"'},
            )
        return PlainTextResponse(
            markdown_report(report), media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="paperrule-review.md"'},
        )

    @app.post('/api/reviews/import')
    def import_review(body: ReviewReport):
        from paperrule.review.importing import import_report
        try:
            return import_report(store, body)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    @app.post('/api/sources')
    def import_source(body: SourceInput):
        try:
            data = base64.b64decode(body.content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(422, 'Invalid base64 file content') from exc
        if len(data) > MAX_BYTES:
            raise HTTPException(413, 'File exceeds the 25 MiB limit')
        try:
            with store.locked():
                source, items = ingest_bytes(
                    data, body.filename, store, reviewer_id=body.reviewer_id,
                    reviewer_role=body.reviewer_role, paper_id=body.paper_id,
                    source_kind=body.kind, intent=body.intent,
                )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {'source': source, 'feedback': items}

    @app.get('/api/sources/{source_id}/preview/{page_index}')
    def source_preview(source_id: str, page_index: int):
        source = next((s for s in store.sources() if s.id == source_id), None)
        if not source or not source.filename.lower().endswith('.pdf'):
            raise HTTPException(404, 'PDF source not found')
        path = (store.root / source.attachment).resolve()
        if not path.is_relative_to(store.root):
            raise HTTPException(400, 'Invalid attachment location')
        import pymupdf
        with pymupdf.open(path) as document:
            if page_index not in range(len(document)):
                raise HTTPException(404, 'PDF page not found')
            pixmap = document[page_index].get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25))
            return Response(pixmap.tobytes('png'), media_type='image/png')

    @app.post('/api/proposals')
    def create_proposal(body: ProposalInput):
        try:
            return gov.propose(body.rule, body.operation, body.feedback_ids, body.additional_rules)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get('/api/proposals/{proposal_id}/diff')
    def proposal_diff(proposal_id: str):
        try:
            return {'diff': gov.diff(store.proposal(proposal_id))}
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(404, 'Proposal not found') from exc

    @app.post('/api/rules/{rule_id}/revert')
    def revert_rule(rule_id: str, body: RevertInput):
        try:
            return gov.revert(rule_id, body.version)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post('/api/restore/preview')
    def preview_restore(body: RestoreInput):
        try:
            return gov.preview_restore(body.commit)
        except (ValueError, SyncError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post('/api/restore')
    def restore_memory(body: RestoreInput):
        try:
            return gov.restore(body.commit, body.baseline_commit)
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, SyncError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post('/api/reviewers')
    def add_reviewer(body: ReviewerProfile):
        try:
            with store.locked():
                store.save_reviewer(body)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return body

    @app.post('/api/sync/push')
    def push_memory():
        with store.locked():
            result = gov.git.push()
            store.write_json('cache', 'sync', result)
        return result

    @app.post('/api/sync/pull')
    def pull_memory():
        with store.locked():
            result = gov.git.pull()
            store.write_json('cache', 'sync', result)
        return result

    @app.get('/api/sync/differences')
    def sync_differences():
        return {'diff': gov.git.differences()}
