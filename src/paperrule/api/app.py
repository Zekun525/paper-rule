import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from paperrule.api.security import register_owner_security
from paperrule.domain.models import PaperProfile, RuleRecord
from paperrule.governance.discussion import discuss_with_provider
from paperrule.governance.service import ConflictError, Governance, GovernanceError
from paperrule.persistence.store import MemoryStore
from paperrule.retrieval.context import build_context


def create_app(root: Path | None = None, web_root: Path | None = None,
               *, owner_token: str | None = None) -> FastAPI:
    store = MemoryStore(root or Path(os.environ.get("PAPERRULE_MEMORY", Path.home() / ".local/share/paperrule/memory")))
    store.initialize()
    gov = Governance(store)
    app = FastAPI(title="PaperRule", version="0.1.0", description="Local-first approved writing rules")
    register_owner_security(app, owner_token)

    @app.get("/healthz", include_in_schema=False)
    def readiness():
        return {"status": "ok"}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "memory_path": str(store.root)}

    @app.get("/api/diagnostics")
    def diagnostics():
        from paperrule.providers import CodexCLIProvider, OpenAIAPIProvider

        name = os.environ.get("PAPERRULE_PROVIDER", "manual").casefold()
        factories = {
            "openai": OpenAIAPIProvider, "openai_api": OpenAIAPIProvider,
            "codex": CodexCLIProvider, "codex_cli": CodexCLIProvider,
        }
        factory = factories.get(name)
        configured = bool(factory and factory().configured)
        return {
            "status": "ok",
            "version": app.version,
            "memory_path": str(store.root),
            "provider": {
                "name": name,
                "configured": configured,
                "connection": "not_checked",
                "message": (
                    "已检测到配置；尚未验证登录、网络连接或模型回复。"
                    if configured else
                    "当前为人工编辑模式，未连接可用的 AI 服务。"
                    if name == "manual" else
                    "未检测到可用配置，请按照安装指南配置 AI 服务后重试。"
                ),
            },
            "counts": {
                "sources": len(store.sources()),
                "feedback": len(store.feedback()),
                "rules": len(store.rules()),
                "proposals": len(store.proposals()),
                "papers": len(store.papers()),
            },
        }

    @app.get("/api/sources")
    def sources():
        return store.sources()

    @app.get("/api/feedback")
    def feedback():
        return store.feedback()

    @app.get("/api/reviewers")
    def reviewers():
        return sorted({f.reviewer_id: {"reviewer_id": f.reviewer_id, "role": f.reviewer_role}
                       for f in store.feedback()}.values(), key=lambda x: x["reviewer_id"])

    @app.get("/api/papers")
    def papers():
        return store.papers()

    @app.post("/api/papers")
    def add_paper(paper: PaperProfile):
        try:
            with store.locked():
                store.save_paper(paper)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return paper

    @app.get("/api/rules")
    def rules():
        return store.rules()

    @app.get("/api/rules/{rule_id}/history")
    def history(rule_id: str):
        rule = store.rule(rule_id)
        if rule is None:
            raise HTTPException(404, "Rule not found")
        return store.history(rule_id)

    @app.get("/api/proposals")
    def proposals():
        return store.proposals()

    @app.get("/api/proposals/{proposal_id}")
    def proposal(proposal_id: str):
        try:
            return store.proposal(proposal_id)
        except (OSError, ValueError):
            raise HTTPException(404, "Proposal not found")

    class ChatInput(BaseModel):
        message: str
        revised: RuleRecord | None = None

    class ApprovalInput(BaseModel):
        proposal_hash: str

    class DecisionInput(BaseModel):
        reason: str = Field(default="", max_length=10000)

    @app.post("/api/proposals/{proposal_id}/chat")
    def chat(proposal_id: str, body: ChatInput):
        try:
            return discuss_with_provider(gov, proposal_id, body.message, body.revised)
        except GovernanceError as exc:
            raise HTTPException(409, str(exc))
        except (OSError, ValueError) as exc:
            raise HTTPException(404, "Proposal not found") from exc

    @app.post("/api/proposals/{proposal_id}/approve")
    def approve(proposal_id: str, body: ApprovalInput):
        try:
            return gov.approve(proposal_id, body.proposal_hash)
        except ConflictError as exc:
            raise HTTPException(409, str(exc))
        except GovernanceError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/proposals/{proposal_id}/reject")
    def reject(proposal_id: str, body: DecisionInput | None = None):
        try:
            return gov.decide(proposal_id, "reject", reason=body.reason if body else "")
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except GovernanceError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(404, "Proposal not found") from exc

    @app.post("/api/proposals/{proposal_id}/defer")
    def defer(proposal_id: str, body: DecisionInput | None = None):
        try:
            return gov.decide(proposal_id, "defer", reason=body.reason if body else "")
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except GovernanceError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(404, "Proposal not found") from exc

    class ContextInput(BaseModel):
        paper_id: str
        section: str = ""
        task: str = ""

    @app.post("/api/context")
    def context(body: ContextInput):
        paper = next((p for p in store.papers() if p.paper_id == body.paper_id), None)
        if paper is None:
            raise HTTPException(404, "Paper not found")
        bundle = build_context(store.rules(), paper, body.section, body.task)
        bundle["memory_commit"] = gov.git.head() or None
        return bundle

    @app.get("/api/regression")
    def regression():
        from paperrule.review.regression import run_cases
        return run_cases(store.regressions(), store.rules())

    @app.get("/api/sync")
    def sync_status():
        return gov.git.status()

    @app.get("/api/restore")
    def restore_info():
        return gov.restore_snapshots()

    from paperrule.api.operations import register_operations
    register_operations(app, store, gov)
    from paperrule.api.regression import register_regression
    register_regression(app, store)
    from paperrule.api.web import register_web
    register_web(app, web_root)
    return app


