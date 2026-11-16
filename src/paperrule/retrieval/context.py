from paperrule.domain.models import PaperProfile, RuleRecord


def applies(rule: RuleRecord, paper: PaperProfile, section: str = "", task: str = "") -> tuple[bool, str]:
    scope = rule.scope
    if scope.paper_ids and paper.paper_id not in scope.paper_ids:
        return False, "different paper"
    if scope.research_types and paper.research_type not in scope.research_types:
        return False, "research type mismatch"
    if scope.venues and paper.venue not in scope.venues:
        return False, "publication mismatch"
    if scope.article_types and paper.article_type not in scope.article_types:
        return False, "article type mismatch"
    if scope.sections and section not in scope.sections:
        return False, "section not included"
    if scope.task_types and task not in scope.task_types:
        return False, "task not included"
    if paper.paper_id in scope.exclude or section in scope.exclude:
        return False, "explicitly excluded"
    return True, "scope matches paper, section, and task"


def build_context(rules: list[RuleRecord], paper: PaperProfile, section: str = "", task: str = "") -> dict:
    matched = []
    for rule in rules:
        if rule.status.value != "active":
            continue
        ok, reason = applies(rule, paper, section, task)
        if ok:
            matched.append({"rule": rule.model_dump(mode="json"), "why_loaded": reason})
    return {"paper_id": paper.paper_id, "section": section, "task": task, "rules": matched}
