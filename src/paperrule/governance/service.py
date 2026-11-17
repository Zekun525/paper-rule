from __future__ import annotations

import difflib
import json
from uuid import uuid4

from paperrule.domain.models import (
    ApprovalEvent,
    ChangeProposal,
    ChatTurn,
    ProposalStatus,
    RuleRecord,
    RuleStatus,
    digest,
)
from paperrule.persistence.store import MemoryStore, identifier, proposal_digest
from paperrule.sync.git import GitSync


class GovernanceError(ValueError):
    pass

class ConflictError(GovernanceError):
    pass

OPERATIONS = {"create", "amend", "narrow_scope", "broaden_scope", "merge", "split",
              "deactivate", "replace", "attach_example", "one_off", "revert", "restore"}
CLOSED = {"applied", "synced", "sync_pending", "sync_conflict", "approved", "rejected"}

class Governance:
    def __init__(self, store: MemoryStore):
        self.store = store
        self.git = GitSync(store.root)

    def propose(self, rule: RuleRecord, operation: str = "create",
                feedback_ids: list[str] | None = None, additional: list[RuleRecord] | None = None) -> ChangeProposal:
        identifier(rule.id)
        if operation not in OPERATIONS:
            raise GovernanceError("Unknown proposal operation")
        with self.store.locked():
            self.git.init()
            before = self.store.rule(rule.id)
            others = additional or []
            if len({r.id for r in [rule, *others]}) != len(others) + 1:
                raise GovernanceError("A rule may only occur once in a proposal")
            proposal = ChangeProposal(
                proposal_id=f"P-{uuid4().hex[:12]}", operation=operation,
                feedback_ids=feedback_ids or rule.source_feedback_ids, before=before, after=rule,
                additional_rules=others, additional_before=[r for item in others if (r := self.store.rule(item.id))],
                recommendation="结合原始意见、既有规则和作用域审阅。相似意见只作关联候选，未被自动合并。",
                alternatives=["保留为当前论文的一次性任务", "补充证据或缩小范围后再批准", "拒绝或暂缓"],
                impact=[f"{item.id}: {', '.join(item.scope.paper_ids) or '匹配作用域的论文'}" for item in [rule, *others]],
                baseline_commit=self.git.head(), status=ProposalStatus.DISCUSSING)
            self.store.save_proposal(proposal)
            proposal.revisions.append(self._revision(proposal))
            self.store.save_proposal(proposal)
            return proposal

    def _revision(self, p: ChangeProposal) -> dict:
        return {"revision": p.revision, "hash": p.proposal_hash,
                "after": p.after.model_dump(mode="json"),
                "additional_rules": [r.model_dump(mode="json") for r in p.additional_rules]}

    def discuss(self, proposal_id: str, user_text: str, revised: RuleRecord | None = None,
                reply: str | None = None, provider: str = "manual", error: str | None = None,
                expected_hash: str | None = None) -> ChangeProposal:
        with self.store.locked():
            proposal = self.store.proposal(proposal_id)
            if proposal.status.value in CLOSED:
                raise GovernanceError("Closed proposal cannot be discussed")
            if expected_hash and expected_hash != proposal.proposal_hash:
                raise ConflictError("Proposal changed during the discussion; reload and retry")
            if revised and revised.id != proposal.after.id:
                raise GovernanceError("Discussion cannot change the rule identifier")
            updated = revised or proposal.after.model_copy(deep=True)
            proposal.revision += 1
            proposal.after = updated
            proposal.status = ProposalStatus.DISCUSSING
            self.store.save_proposal(proposal)
            proposal.chat.append(ChatTurn(
                sequence=len(proposal.chat) + 1, user_text=user_text,
                assistant_text=reply or "已保存意见。当前为人工编辑模式；请编辑完整提案或配置 AI 后继续讨论。",
                proposal=updated, proposal_hash=proposal.proposal_hash, provider=provider, error=error))
            proposal.revisions.append(self._revision(proposal))
            self.store.save_proposal(proposal)
            return proposal

    def approve(self, proposal_id: str, proposal_hash: str, actor: str = "local-user") -> tuple[ChangeProposal, str]:
        with self.store.locked():
            proposal = self.store.proposal(proposal_id)
            if proposal.approved_hash:
                if proposal.approved_hash != proposal_hash:
                    raise ConflictError("Approval hash does not match the previously approved version")
                return proposal, "already-applied"
            if proposal.status.value in CLOSED:
                raise ConflictError("Proposal is closed")
            if proposal_digest(proposal) != proposal_hash or proposal.proposal_hash != proposal_hash:
                raise ConflictError("Proposal changed since review; reload before approving")
            self.git.init()
            if proposal.baseline_commit != self.git.head():
                raise ConflictError("Memory baseline changed; review a refreshed proposal before approval")
            planned = [proposal.after, *proposal.additional_rules]
            before_map = {r.id: r for r in [proposal.before, *proposal.additional_before] if r}
            for rule in planned:
                identifier(rule.id)
                current = self.store.rule(rule.id)
                before = before_map.get(rule.id)
                if (current is None) != (before is None) or (current and before and digest(current) != digest(before)):
                    raise ConflictError(f"Base rule {rule.id} changed")
                missing = set(rule.source_feedback_ids) - {f.id for f in self.store.feedback()}
                if missing:
                    raise GovernanceError("Rule references missing feedback records")
            # Back up every authority record before changing any of them. Index/cache files are disposable.
            backup = {str(p.relative_to(self.store.root)): p.read_text(encoding="utf-8")
                      for p in self.store.root.rglob("*.json") if ".git" not in p.parts and "cache" not in p.parts}
            if self.git.run("diff", "--cached", "--name-only"):
                raise ConflictError("Memory has staged edits; finish or unstage them before approval")
            cache = self.store.root / "cache"
            cache.mkdir(exist_ok=True)
            journal = cache / "transaction.json"
            journal.write_text(json.dumps({"head": self.git.head(), "files": backup}), encoding="utf-8")
            try:
                if proposal.operation != "one_off":
                    for rule in planned:
                        active = rule.model_copy(deep=True)
                        current = before_map.get(rule.id)
                        active.version = current.version + 1 if current else 1
                        active.status = RuleStatus.DEPRECATED if proposal.operation == "deactivate" else (
                            RuleStatus.ACTIVE if active.status == RuleStatus.PROPOSED else active.status)
                        active.revision_id = proposal.proposal_id
                        self.store.save_rule(active)
                else:
                    self.store.write_json("tasks", proposal.proposal_id, proposal.after.model_dump(mode="json"))
                proposal.approved_hash = proposal_hash
                proposal.status = ProposalStatus.APPLIED
                self.store.save_proposal(proposal)
                event = ApprovalEvent(event_id=f"A-{uuid4().hex[:12]}", proposal_id=proposal_id, actor=actor,
                                      action="approve", proposal_hash=proposal_hash, revision=proposal.revision)
                self.store.save_decision(event)
                self.store.write_json("snapshots", event.event_id, {
                    "approval": event.model_dump(mode="json"),
                    "rules": [r.model_dump(mode="json") for r in self.store.rules()]})
                proposal.applied_commit = self.git.commit_approved(f"Approve {proposal_id} revision {proposal.revision}")
                journal.unlink()
            except Exception:
                for p in self.store.root.rglob("*.json"):
                    rel = str(p.relative_to(self.store.root))
                    if ".git" not in p.parts and "cache" not in p.parts and rel not in backup:
                        p.unlink()
                for rel, content in backup.items():
                    (self.store.root / rel).write_text(content, encoding="utf-8")
                self.git.run("restore", "--staged", ".", check=False)
                journal.unlink(missing_ok=True)
                raise
            sync = self.git.push()
            self.store.write_json("cache", "sync", sync)
            return proposal, "applied"

    def decide(self, proposal_id: str, action: str, reason: str = "", actor: str = "local-user") -> ChangeProposal:
        if action not in {"reject", "defer"}:
            raise GovernanceError("Invalid decision action")
        with self.store.locked():
            proposal = self.store.proposal(proposal_id)
            if proposal.status.value in CLOSED:
                raise ConflictError("Proposal is closed")
            proposal.status = ProposalStatus.REJECTED if action == "reject" else ProposalStatus.DEFERRED
            proposal.decision_reason = reason
            self.store.save_proposal(proposal)
            self.store.save_decision(ApprovalEvent(event_id=f"A-{uuid4().hex[:12]}", proposal_id=proposal_id,
                actor=actor, action=action, proposal_hash=proposal.proposal_hash, reason=reason, revision=proposal.revision))
            return proposal

    def reject(self, proposal_id: str, actor: str = "local-user") -> ChangeProposal:
        return self.decide(proposal_id, "reject", actor=actor)

    def revert(self, rule_id: str, version: int) -> ChangeProposal:
        historical = next((r for r in self.store.history(rule_id) if r.version == version), None)
        if not historical:
            raise GovernanceError("Requested rule version does not exist")
        return self.propose(historical, "revert")

    def restore_snapshots(self) -> dict:
        with self.store.locked(wait=5):
            head = self.git.head() or None
            snapshots = []
            if head:
                entries = self.git.run(
                    "log", "-n", "50", "--format=%H%x09%cI%x09%s", "--", "rules",
                )
                for entry in entries.splitlines():
                    commit, created_at, summary = entry.split(chr(9), 2)
                    snapshots.append({
                        "commit": commit, "created_at": created_at, "summary": summary,
                    })
            return {
                "available": bool(snapshots), "current_commit": head,
                "snapshots": snapshots,
                "message": "Restore requires a preview and a separately approved proposal",
            }

    def _restore_plan(self, sha: str) -> tuple[str, list[dict]]:
        sha = self.git.validate_sha(sha)
        paths = self.git.run("ls-tree", "-r", "--name-only", sha, "--", "rules").splitlines()
        rules = [RuleRecord.model_validate_json(self.git.run("show", f"{sha}:{p}")) for p in paths if p.endswith(".json")]
        current = {rule.id: rule for rule in self.store.rules()}
        historical_ids = {r.id for r in rules}
        for r in current.values():
            if r.id not in historical_ids:
                rules.append(r.model_copy(update={"status": RuleStatus.DEPRECATED}))
        changes = []
        for rule in rules:
            before = current.get(rule.id)
            if before is not None and before.model_dump(exclude={"version", "revision_id"}) == (
                rule.model_dump(exclude={"version", "revision_id"})
            ):
                continue
            changes.append({
                "rule_id": rule.id,
                "action": "deactivate" if rule.status == RuleStatus.DEPRECATED
                else "amend" if before else "create",
                "before": before.model_dump(mode="json") if before else None,
                "after": rule.model_dump(mode="json"),
            })
        return sha, changes

    def preview_restore(self, sha: str) -> dict:
        with self.store.locked(wait=5):
            commit, changes = self._restore_plan(sha)
            return {
                "target_commit": commit, "baseline_commit": self.git.head(),
                "changes": changes, "requires_approval": True,
            }

    def restore(self, sha: str, expected_baseline: str | None = None) -> ChangeProposal:
        with self.store.locked():
            if expected_baseline is not None and expected_baseline != self.git.head():
                raise ConflictError("Memory changed since the restore preview; preview it again")
            _, changes = self._restore_plan(sha)
            if not changes:
                raise GovernanceError("Snapshot has no rule changes to restore")
            rules = [RuleRecord.model_validate(change["after"]) for change in changes]
            return self.propose(rules[0], "restore", additional=rules[1:])

    def diff(self, p: ChangeProposal) -> str:
        before_map = {r.id: r for r in [p.before, *p.additional_before] if r}
        sections = []
        for rule in [p.after, *p.additional_rules]:
            original = before_map.get(rule.id)
            before = original.model_dump_json(indent=2) if original else ""
            sections.append("\n".join(difflib.unified_diff(
                before.splitlines(), rule.model_dump_json(indent=2).splitlines(),
                fromfile=f"{rule.id}/before", tofile=f"{rule.id}/proposed", lineterm="",
            )))
        return "\n\n".join(sections)
