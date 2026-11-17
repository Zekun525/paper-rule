from __future__ import annotations

import json
import os
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from paperrule.domain.models import (
    ApprovalEvent,
    ChangeProposal,
    FeedbackItem,
    PaperProfile,
    RegressionCase,
    ReviewerProfile,
    ReviewReport,
    RuleRecord,
    SourceRecord,
    digest,
)
from paperrule.persistence.index import SearchIndex

T = TypeVar("T", bound=BaseModel)
_LOCKS: dict[str, threading.RLock] = {}
_LOCK_STATES: dict[str, threading.local] = {}


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", value):
        raise ValueError("Invalid record identifier")
    return value


class MemoryStore:
    """JSON records in a user-selected private directory; no data defaults to the source tree."""

    folders = ("rules/global", "rules/research-type", "rules/publication", "rules/paper",
               "rules/section-task", "feedback", "sources", "proposals", "decisions",
               "examples", "papers", "regression", "snapshots", "attachments",
               "history", "reviewers", "reviews", "runs", "tasks")

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self._mutex = _LOCKS.setdefault(str(self.root), threading.RLock())
        self._lock_state = _LOCK_STATES.setdefault(str(self.root), threading.local())
        self.index = SearchIndex(self.root)

    @contextmanager
    def locked(self, *, wait: float = 0):
        self.initialize()
        with self._mutex:
            if getattr(self._lock_state, "held", False):
                yield
                return
            lock = self.root / ".transaction.lock"
            fd = None
            deadline = time.monotonic() + max(wait, 0)
            try:
                while fd is None:
                    try:
                        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    except FileExistsError as exc:
                        if time.monotonic() >= deadline:
                            raise ValueError("Memory is busy; retry after the current transaction") from exc
                        time.sleep(0.01)
                self._lock_state.held = True
                yield
            finally:
                self._lock_state.held = False
                if fd is not None:
                    os.close(fd)
                    lock.unlink(missing_ok=True)

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for folder in self.folders:
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        manifest = self.root / "manifest.json"
        if not manifest.exists():
            manifest.write_text('{"schema_version":1,"product":"PaperRule"}\n', encoding="utf-8")
        elif json.loads(manifest.read_text(encoding="utf-8")).get("schema_version") != 1:
            raise ValueError("Unsupported memory schema; export or migrate it before use")
        ignore = self.root / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*.db\n*.sqlite\n*.sqlite3\n.env\ncache/\n.transaction.lock\n*.tmp\n", encoding="utf-8")

    def _write(self, folder: str, key: str, model: BaseModel) -> None:
        self.initialize()
        safe = identifier(key)
        target = self.root / folder / f"{safe}.json"
        if not target.resolve().is_relative_to(self.root):
            raise ValueError("Path escapes memory")
        temp = target.with_suffix(".tmp")
        temp.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temp, target)

    def _all(self, folder: str, model: type[T]) -> list[T]:
        self.initialize()
        result = []
        for path in sorted((self.root / folder).glob("*.json")):
            result.append(model.model_validate_json(path.read_text(encoding="utf-8")))
        return result

    def save_feedback(self, item: FeedbackItem) -> None:
        target = self.root / "feedback" / f"{identifier(item.id)}.json"
        if target.exists():
            old = FeedbackItem.model_validate_json(target.read_text(encoding="utf-8"))
            if old.quote != item.quote or old.source_id != item.source_id:
                raise ValueError("Original feedback is immutable; append a correction instead")
        item.sha256 = digest(item.model_dump(mode="json", exclude={"sha256"}))
        self._write("feedback", item.id, item)

    def feedback(self) -> list[FeedbackItem]:
        return self._all("feedback", FeedbackItem)

    def save_rule(self, rule: RuleRecord) -> None:
        with self.locked():
            safe = identifier(rule.id)
            level = rule.scope.levels[-1] if rule.scope.levels else "global"
            folder = {"global": "rules/global", "research_type": "rules/research-type",
                      "publication": "rules/publication", "paper": "rules/paper",
                      "section_task": "rules/section-task"}.get(level, "rules/global")
            target = self.root / folder / f"{safe}.json"
            # Replace first: failed writes must not remove the previous active record.
            self._write(folder, rule.id, rule)
            for path in (self.root / "rules").glob(f"*/{safe}.json"):
                if path != target:
                    path.unlink()
            self._write("history", f"{rule.id}-v{rule.version}", rule)

    def rules(self) -> list[RuleRecord]:
        # Readers share the approval lock so a scope move cannot expose half a snapshot.
        with self.locked(wait=5):
            return [r for folder in self.folders if folder.startswith("rules/")
                    for r in self._all(folder, RuleRecord)]

    def rebuild_index(self) -> int:
        records = []
        records.extend({"kind": "rule", "record_id": r.id, "title": r.short_title,
                        "body": r.statement + " " + r.rationale} for r in self.rules())
        records.extend({"kind": "feedback", "record_id": f.id, "title": f.classification.value,
                        "body": f.quote} for f in self.feedback())
        return self.index.rebuild(records)

    def search(self, query: str, *, kind: str | None = None, limit: int = 50) -> list[dict]:
        self.rebuild_index()
        return self.index.search(query, kind=kind, limit=limit)

    def rule(self, rule_id: str) -> RuleRecord | None:
        return next((r for r in self.rules() if r.id == rule_id), None)

    def save_proposal(self, proposal: ChangeProposal) -> None:
        proposal.proposal_hash = proposal_digest(proposal)
        self._write("proposals", proposal.proposal_id, proposal)

    def proposal(self, proposal_id: str) -> ChangeProposal:
        path = self.root / "proposals" / f"{identifier(proposal_id)}.json"
        return ChangeProposal.model_validate_json(path.read_text(encoding="utf-8"))

    def proposals(self) -> list[ChangeProposal]:
        return self._all("proposals", ChangeProposal)

    def save_decision(self, event: ApprovalEvent) -> None:
        if (self.root / "decisions" / f"{identifier(event.event_id)}.json").exists():
            raise ValueError("Approval events are append-only")
        self._write("decisions", event.event_id, event)

    def save_paper(self, paper: PaperProfile) -> None:
        self._write("papers", paper.paper_id, paper)

    def papers(self) -> list[PaperProfile]:
        return self._all("papers", PaperProfile)

    def decision_count(self, proposal_id: str) -> int:
        return sum(1 for p in (self.root / "decisions").glob("*.json")
                   if json.loads(p.read_text(encoding="utf-8")).get("proposal_id") == proposal_id)

    def save_regression(self, case: RegressionCase) -> None:
        self._write("regression", case.id, case)

    def regressions(self) -> list[RegressionCase]:
        return self._all("regression", RegressionCase)

    def history(self, rule_id: str) -> list[RuleRecord]:
        identifier(rule_id)
        return sorted((r for r in self._all("history", RuleRecord) if r.id == rule_id),
                      key=lambda r: r.version)

    def save_source(self, source: SourceRecord) -> None:
        self._write("sources", source.id, source)

    def sources(self) -> list[SourceRecord]:
        return self._all("sources", SourceRecord)

    def save_reviewer(self, reviewer: ReviewerProfile) -> None:
        self._write("reviewers", reviewer.reviewer_id, reviewer)

    def reviewers(self) -> list[ReviewerProfile]:
        return self._all("reviewers", ReviewerProfile)

    def decisions(self) -> list[ApprovalEvent]:
        return self._all("decisions", ApprovalEvent)

    def save_review(self, report: ReviewReport) -> None:
        self._write("reviews", report.review_id, report)

    def reviews(self) -> list[ReviewReport]:
        return self._all("reviews", ReviewReport)

    def write_json(self, folder: str, key: str, value: dict) -> None:
        identifier(folder)
        self.initialize()
        path = self.root / folder / (identifier(key) + ".json")
        path.parent.mkdir(exist_ok=True)
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Path escapes memory")
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)

    def read_json(self, folder: str) -> list[dict]:
        identifier(folder)
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted((self.root / folder).glob("*.json"))]


def proposal_digest(proposal: ChangeProposal) -> str:
    return digest({"operation": proposal.operation, "after": proposal.after.model_dump(mode="json"),
                   "additional_rules": [r.model_dump(mode="json") for r in proposal.additional_rules],
                   "before": proposal.before.model_dump(mode="json") if proposal.before else None,
                   "additional_before": [r.model_dump(mode="json") for r in proposal.additional_before],
                   "revision": proposal.revision, "baseline_commit": proposal.baseline_commit,
                   "feedback_ids": proposal.feedback_ids})
