import json
import os
from pathlib import Path

import typer
import uvicorn
from rich import print

from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.governance.service import Governance
from paperrule.ingestion.text import ingest_file, ingest_text
from paperrule.persistence.store import MemoryStore
from paperrule.retrieval.context import build_context

app = typer.Typer(no_args_is_help=True, help="Private, auditable academic writing rules")
paper_app = typer.Typer(no_args_is_help=True)
rule_app = typer.Typer(no_args_is_help=True)
proposal_app = typer.Typer(no_args_is_help=True)
regression_app = typer.Typer(no_args_is_help=True)
sync_app = typer.Typer(no_args_is_help=True)
app.add_typer(paper_app, name="paper")
app.add_typer(rule_app, name="rules")
app.add_typer(proposal_app, name="proposal")
app.add_typer(regression_app, name="regression")
app.add_typer(sync_app, name="sync")


def get_store(root: Path | None = None) -> MemoryStore:
    store = MemoryStore(root or Path(os.environ.get("PAPERRULE_MEMORY", Path.home() / ".local/share/paperrule/memory")))
    store.initialize()
    return store


@app.command()
def doctor():
    store = get_store()
    print({"status": "ready", "python": "3.12+", "memory": str(store.root), "llm": "not configured"})


@app.command()
def init(workspace: Path = typer.Option(..., "--workspace", writable=True)):  # noqa: B008
    store = get_store(workspace)
    print(f"Initialized private memory at [bold]{store.root}[/bold]")


@paper_app.command("add")
def paper_add(id: str = typer.Option(...), path: Path = typer.Option(...),  # noqa: B008
              research_type: str = typer.Option(""), venue: str = typer.Option(""),
              article_type: str = typer.Option("")):
    p = PaperProfile(paper_id=id, research_type=research_type, venue=venue,
                     article_type=article_type, project_path=str(path.resolve()))
    get_store().save_paper(p)
    print(f"Added paper profile {id}")


@app.command("ingest")
def ingest(path: Path, paper: str | None = typer.Option(None), reviewer: str = typer.Option("author"),
           kind: str = typer.Option("text")):
    kwargs = {"reviewer_id": reviewer, "paper_id": paper, "reviewer_role": "other"}
    if path.exists():
        items = ingest_file(path, get_store(), **kwargs)
    else:
        raise typer.BadParameter("Input file does not exist")
    print(f"Imported {len(items)} feedback items; all require review before becoming rules")


@app.command("ingest-text")
def ingest_pasted(text: str = typer.Argument(...), reviewer: str = typer.Option("author")):
    items = ingest_text(text, get_store(), reviewer_id=reviewer)
    print(f"Imported {len(items)} feedback items")


@rule_app.command("search")
def rules_search(query: str):
    found = [r for r in get_store().rules() if query.casefold() in (r.short_title + " " + r.statement).casefold()]
    print(json.dumps([r.model_dump(mode="json") for r in found], ensure_ascii=False, indent=2))


@rule_app.command("history")
def rules_history(rule_id: str):
    print(json.dumps([r.model_dump(mode="json") for r in get_store().rules() if r.id == rule_id], ensure_ascii=False, indent=2))


@proposal_app.command("list")
def proposals_list(status: str = typer.Option("")):
    records = [p for p in get_store().proposals() if not status or p.status.value == status]
    print(json.dumps([p.model_dump(mode="json") for p in records], ensure_ascii=False, indent=2))


@proposal_app.command("show")
def proposal_show(id: str):
    print(get_store().proposal(id).model_dump_json(indent=2))


@proposal_app.command("draft")
def proposal_draft(rule_id: str, title: str, statement: str, scope: str = typer.Option("global")):
    rule = RuleRecord(id=rule_id, short_title=title, statement=statement,
                      scope=RuleScope(levels=[scope]))
    p = Governance(get_store()).propose(rule)
    print(f"Draft {p.proposal_id} created. Hash: {p.proposal_hash}")


@proposal_app.command("approve")
def proposal_approve(id: str, proposal_hash: str = typer.Option(..., prompt=True)):
    p, result = Governance(get_store()).approve(id, proposal_hash)
    print(f"{result}: {p.after.id} v{p.after.version}")


@app.command()
def context(paper: str, section: str = typer.Option(""), task: str = typer.Option(""), format: str = typer.Option("json")):
    profile = next((p for p in get_store().papers() if p.paper_id == paper), None)
    if profile is None:
        raise typer.BadParameter(f"Paper profile {paper!r} was not found")
    print(json.dumps(build_context(get_store().rules(), profile, section, task), ensure_ascii=False, indent=2))


@app.command()
def check(file: Path):
    from paperrule.review.check import check_text
    text = file.read_text(encoding="utf-8")
    findings = check_text(text, get_store().rules())
    print(json.dumps([f.model_dump(mode="json") for f in findings], ensure_ascii=False, indent=2))


@regression_app.command("run")
def regression_run(paper: str = typer.Option("")):
    from paperrule.review.regression import run_stored_cases
    try:
        report = run_stored_cases(get_store(), paper)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))


@regression_app.command("report")
def regression_report(latest: bool = typer.Option(False)):
    from paperrule.review.regression import reports
    recorded = reports(get_store())
    if latest:
        typer.echo(json.dumps(recorded[0] if recorded else None, ensure_ascii=False, indent=2))
    else:
        typer.echo(json.dumps(recorded, ensure_ascii=False, indent=2))


@sync_app.command("status")
def sync_status():
    print("Local-only mode; no remote configured")


@sync_app.command("push")
def sync_push():
    raise typer.BadParameter("No private Git remote configured; local approved data remains available")


@sync_app.command("pull")
def sync_pull():
    raise typer.BadParameter("No private Git remote configured")


@app.command("app")
def app_server(host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8765)):
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise typer.BadParameter("PaperRule only binds localhost in this release")
    uvicorn.run("paperrule.api.app:create_app", host=host, port=port,
                factory=True, reload=False)


@app.command("install-codex")
def install_codex(paper: Path, scope: str = typer.Option("repo")):
    from paperrule.integrations.codex.install import install
    install(paper.resolve(), scope)


@app.command("uninstall-codex")
def uninstall_codex(paper: Path):
    from paperrule.integrations.codex.install import uninstall
    uninstall(paper.resolve())

