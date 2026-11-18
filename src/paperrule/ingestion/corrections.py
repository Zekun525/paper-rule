"""Append manual evidence without replacing imported originals or active rules."""
from __future__ import annotations

from hashlib import sha256

from pydantic import Field

from paperrule.domain.models import (
    Classification,
    FeedbackItem,
    Location,
    Record,
    digest,
    utcnow,
)
from paperrule.governance.service import ConflictError
from paperrule.persistence.store import MemoryStore, identifier


class EvidenceNotFound(LookupError):
    pass


class TranscriptionInput(Record):
    request_id: str = Field(pattern="^[A-Za-z0-9][A-Za-z0-9_-]{0,100}$")
    text: str = Field(min_length=1, max_length=100000)
    reason: str = Field(min_length=1, max_length=2000)
    reviewer_role: str = Field(min_length=1, max_length=100)
    classification: Classification = Classification.CLARIFICATION_NEEDED
    page: int | None = Field(default=None, ge=1)
    section: str = Field(default="", max_length=300)


class CorrectionInput(Record):
    request_id: str = Field(pattern="^[A-Za-z0-9][A-Za-z0-9_-]{0,100}$")
    expected_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    text: str = Field(min_length=1, max_length=100000)
    reason: str = Field(min_length=1, max_length=2000)
    classification: Classification | None = None


def transcribe(store: MemoryStore, source_id: str, body: TranscriptionInput) -> FeedbackItem:
    identifier(source_id)
    if not body.text.strip() or not body.reason.strip() or not body.reviewer_role.strip():
        raise ValueError("Text, reason and confirmed reviewer role must not be blank")
    with store.locked():
        source = next((item for item in store.sources() if item.id == source_id), None)
        if source is None:
            raise EvidenceNotFound("Source not found")
        request_hash = digest({"source_id": source_id, **body.model_dump(mode="json")})
        item_id = "F-MANUAL-" + digest([source_id, body.request_id])[:24]
        existing = next((item for item in store.feedback() if item.id == item_id), None)
        if existing is not None:
            if existing.extraction_details.get("request_sha256") != request_hash:
                raise ConflictError("This request identifier already names different content")
            return existing
        attachment = (store.root / source.attachment).resolve()
        if not attachment.is_relative_to(store.root) or not attachment.is_file():
            raise ValueError("Original source attachment is not available within private memory")
        if sha256(attachment.read_bytes()).hexdigest() != source.sha256:
            raise ValueError("Original source attachment does not match its recorded hash")
        is_pdf = source.filename.lower().endswith(".pdf")
        if body.page is not None:
            if not is_pdf:
                raise ValueError("Page numbers currently require a PDF source")
            import pymupdf

            try:
                with pymupdf.open(attachment) as document:
                    if document.needs_pass or body.page > len(document):
                        raise ValueError("Page is unavailable in the original PDF")
            except (RuntimeError, OSError) as exc:
                raise ValueError("PDF page cannot be verified; omit the page if unknown") from exc
        item = FeedbackItem(
            id=item_id, source_id=source.id, source_kind=source.kind,
            reviewer_id=source.reviewer_id, reviewer_role=body.reviewer_role,
            paper_id=source.paper_id, quote=body.text,
            location=Location(page=body.page, page_index=body.page - 1 if body.page else None,
                              section=body.section or None),
            classification=body.classification, extraction_method="manual_transcription",
            confidence="user_supplied",
            extraction_details={
                "request_id": body.request_id, "request_sha256": request_hash,
                "source_sha256": source.sha256, "manual_reason": body.reason,
            },
        )
        store.save_feedback(item)
        return item


def append_correction(store: MemoryStore, feedback_id: str, body: CorrectionInput) -> FeedbackItem:
    identifier(feedback_id)
    if not body.text.strip() or not body.reason.strip():
        raise ValueError("Correction and reason must not be blank")
    with store.locked():
        item = next((record for record in store.feedback() if record.id == feedback_id), None)
        if item is None:
            raise EvidenceNotFound("Feedback not found")
        request_hash = digest({"feedback_id": feedback_id, **body.model_dump(mode="json")})
        previous = next((entry for entry in item.corrections
                         if entry.get("request_id") == body.request_id), None)
        if previous is not None:
            if previous.get("request_sha256") != request_hash:
                raise ConflictError("This request identifier already names different content")
            return item
        if item.sha256 != body.expected_sha256:
            raise ConflictError("Feedback changed; reload its evidence before correcting it")
        item.corrections.append({
            "request_id": body.request_id, "request_sha256": request_hash,
            "previous_sha256": item.sha256, "text": body.text, "reason": body.reason,
            "classification": body.classification.value if body.classification else "",
            "created_at": utcnow().isoformat(),
        })
        store.save_feedback(item)
        return item
