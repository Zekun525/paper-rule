from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def utcnow() -> datetime:
    return datetime.now(UTC)


def digest(value: Any) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


class FeedbackKind(StrEnum):
    TEXT = "text"
    ANNOTATED_PDF = "annotated_pdf"
    EXEMPLAR = "exemplar"
    DOCX = "docx"
    REVISION_PAIR = "revision_pair"
    MEETING_NOTES = "meeting_notes"


class Classification(StrEnum):
    ONE_OFF_EDIT = "one_off_edit"
    REUSABLE_RULE = "reusable_rule"
    PAPER_SPECIFIC_RULE = "paper_specific_rule"
    EXEMPLAR = "exemplar"
    NEGATIVE_EXAMPLE = "negative_example"
    RESEARCH_FACT = "research_fact"
    CLARIFICATION_NEEDED = "clarification_needed"


class RuleStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


class ProposalStatus(StrEnum):
    DRAFT = "draft"
    DISCUSSING = "discussing"
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    APPLIED = "applied"
    SYNC_PENDING = "sync_pending"
    SYNCED = "synced"
    SYNC_CONFLICT = "sync_conflict"


class ReviewerProfile(Record):
    reviewer_id: str
    display_name: str
    role: str = "other"
    tags: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)


class Location(Record):
    section: str | None = None
    page: int | None = None
    page_index: int | None = None
    bbox: list[float] | None = None
    anchor_text: str | None = None


class FeedbackItem(Record):
    id: str
    source_id: str
    source_kind: FeedbackKind = FeedbackKind.TEXT
    reviewer_id: str
    reviewer_role: str = "other"
    paper_id: str | None = None
    location: Location = Field(default_factory=Location)
    quote: str
    extraction_method: str = "manual"
    confidence: str = "high"
    classification: Classification = Classification.CLARIFICATION_NEEDED
    created_at: datetime = Field(default_factory=utcnow)
    sha256: str = ""
    corrections: list[dict[str, str]] = Field(default_factory=list)
    extraction_details: dict[str, Any] = Field(default_factory=dict)


class RuleScope(Record):
    levels: list[str] = Field(default_factory=lambda: ["global"])
    research_types: list[str] = Field(default_factory=list)
    venues: list[str] = Field(default_factory=list)
    article_types: list[str] = Field(default_factory=list)
    paper_ids: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    effective_from: datetime | None = None


class RuleRecord(Record):
    id: str
    version: int = Field(default=1, ge=1)
    status: RuleStatus = RuleStatus.PROPOSED
    short_title: str
    statement: str
    rationale: str = ""
    scope: RuleScope = Field(default_factory=RuleScope)
    severity: str = "warn"
    check_method: str = "semantic"
    source_feedback_ids: list[str] = Field(default_factory=list)
    related_rule_ids: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    test_ids: list[str] = Field(default_factory=list)
    revision_id: str | None = None
    blocking: bool = False
    relations: list[dict[str, str]] = Field(default_factory=list)
    positive_example: str = ""
    negative_example: str = ""
    not_applicable: str = ""
    pattern: str = ""


class ChatTurn(Record):
    sequence: int
    user_text: str
    assistant_text: str
    proposal: RuleRecord
    proposal_hash: str
    created_at: datetime = Field(default_factory=utcnow)
    provider: str = "manual"
    error: str | None = None


class ChangeProposal(Record):
    proposal_id: str
    operation: str = "create"
    feedback_ids: list[str] = Field(default_factory=list)
    before: RuleRecord | None = None
    after: RuleRecord
    recommendation: str = ""
    alternatives: list[str] = Field(default_factory=list)
    impact: list[str] = Field(default_factory=list)
    status: ProposalStatus = ProposalStatus.DRAFT
    baseline_commit: str | None = None
    revision: int = 1
    proposal_hash: str = ""
    chat: list[ChatTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    additional_rules: list[RuleRecord] = Field(default_factory=list)
    additional_before: list[RuleRecord] = Field(default_factory=list)
    approved_hash: str | None = None
    applied_commit: str | None = None
    decision_reason: str = ""
    revisions: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalEvent(Record):
    event_id: str
    proposal_id: str
    actor: str
    action: str
    proposal_hash: str
    created_at: datetime = Field(default_factory=utcnow)
    commit_sha: str | None = None
    sync_status: str = "local"
    revision: int = 1
    reason: str = ""


class ReviewFinding(Record):
    rule_id: str
    rule_version: int
    location: str = ""
    quote: str = ""
    description: str
    evidence: str = ""
    recommendation: str = ""
    severity: str = "warn"
    review_type: str = "deterministic"
    confidence: float | None = None
    confirmed: bool | None = None
    retest_result: str = "not_tested"


class ReviewRuleVersion(Record):
    rule_id: str
    version: int = Field(ge=1)


class ReviewInput(Record):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    diff: str = ""


class ReviewCoverage(Record):
    rule_id: str
    rule_version: int = Field(ge=1)
    status: Literal["checked", "not_reviewed", "unavailable"]
    reason: str = ""
    checked_line_count: int = Field(default=0, ge=0)


class ReviewReport(Record):
    review_id: str
    paper_id: str | None = None
    paper_commit: str | None = None
    task_summary: str = ""
    section: str = ""
    task: str = ""
    source: str = "manual"
    provider: str = "manual"
    model: str = ""
    status: str = "imported"
    memory_commit: str | None = None
    memory_rules_dirty: bool | None = None
    rule_snapshot: list[RuleRecord] = Field(default_factory=list)
    rule_snapshot_sha256: str | None = None
    rules: list[ReviewRuleVersion] = Field(default_factory=list)
    coverage: list[ReviewCoverage] = Field(default_factory=list)
    files: list[ReviewInput] = Field(default_factory=list)
    diff_mode: bool = False
    semantic_status: str = "not_reviewed"
    latex_build_status: str = "not_run"
    fixed_items: list[str] = Field(default_factory=list)
    unavailable: list[dict[str, str | int]] = Field(default_factory=list)
    findings: list[ReviewFinding] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class RegressionCase(Record):
    id: str
    rule_id: str
    input_text: str
    expected: str
    explanation: str = ""
    check_method: Literal["deterministic", "semantic"] = "deterministic"
    rule_version: int | None = None
    paper_id: str | None = None
    section: str = ""
    task: str = ""


class PaperProfile(Record):
    paper_id: str
    title: str = ""
    research_type: str = ""
    venue: str = ""
    article_type: str = ""
    sections: list[str] = Field(default_factory=list)
    project_path: str | None = None
    facts: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    citation_style: str = ""
    version: str = ""

class SourceRecord(Record):
    id: str
    filename: str
    sha256: str
    kind: FeedbackKind
    reviewer_id: str
    paper_id: str | None = None
    intent: str = ""
    date: str = ""
    attachment: str
    extraction_status: str = "ready"
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    import_version: int = 1

