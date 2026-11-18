from fastapi import FastAPI, HTTPException

from paperrule.governance.service import ConflictError
from paperrule.ingestion.corrections import (
    CorrectionInput,
    EvidenceNotFound,
    TranscriptionInput,
    append_correction,
    transcribe,
)
from paperrule.persistence.store import MemoryStore


def register_feedback(app: FastAPI, store: MemoryStore) -> None:
    @app.post("/api/sources/{source_id}/transcriptions")
    def source_transcription(source_id: str, body: TranscriptionInput):
        try:
            return transcribe(store, source_id, body)
        except EvidenceNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/feedback/{feedback_id}/corrections")
    def feedback_correction(feedback_id: str, body: CorrectionInput):
        try:
            return append_correction(store, feedback_id, body)
        except EvidenceNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
