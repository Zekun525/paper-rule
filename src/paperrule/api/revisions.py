import base64
import binascii

from fastapi import FastAPI, HTTPException
from pydantic import Field, StrictStr

from paperrule.domain.models import Record
from paperrule.ingestion.pipeline import MAX_BYTES, ingest_revision_pair, read_revision_pair
from paperrule.persistence.store import MemoryStore


class RevisionPairInput(Record):
    before_filename: StrictStr = Field(min_length=1, max_length=240)
    after_filename: StrictStr = Field(min_length=1, max_length=240)
    before_content_base64: StrictStr = Field(max_length=36_000_000)
    after_content_base64: StrictStr = Field(max_length=36_000_000)
    reviewer_id: StrictStr = Field(default='author', min_length=1, max_length=101)
    reviewer_role: StrictStr = Field(default='author', min_length=1, max_length=128)
    paper_id: StrictStr | None = Field(default=None, min_length=1, max_length=101)
    intent: StrictStr = Field(default='', max_length=4000)
    date: StrictStr = Field(default='', max_length=128)


def register_revisions(app: FastAPI, store: MemoryStore) -> None:
    @app.post('/api/revision-pairs')
    def import_pair(body: RevisionPairInput):
        try:
            before = base64.b64decode(body.before_content_base64, validate=True)
            after = base64.b64decode(body.after_content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(422, 'Invalid base64 revision content') from exc
        if max(len(before), len(after)) > MAX_BYTES:
            raise HTTPException(413, 'Each revision file must be at most 25 MiB')
        try:
            with store.locked():
                if body.paper_id is not None and not any(
                    paper.paper_id == body.paper_id for paper in store.papers()
                ):
                    raise HTTPException(404, 'Paper not found')
                return ingest_revision_pair(
                    before, after, body.before_filename, store,
                    reviewer_id=body.reviewer_id, reviewer_role=body.reviewer_role,
                    paper_id=body.paper_id, after_filename=body.after_filename,
                    intent=body.intent, date=body.date,
                )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, 'Revision files could not be saved') from exc

    @app.get('/api/revision-pairs/{source_id}')
    def revision_pair(source_id: str):
        try:
            return read_revision_pair(store, source_id)
        except LookupError as exc:
            raise HTTPException(404, 'Revision pair not found') from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(409, 'Persisted revision evidence failed validation') from exc
