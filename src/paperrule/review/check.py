from paperrule.domain.models import ReviewFinding, RuleRecord


def check_text(text: str, rules: list[RuleRecord]) -> list[ReviewFinding]:
    findings = []
    lowered = text.casefold()
    for rule in rules:
        if rule.status.value != "active" or rule.check_method != "deterministic":
            continue
        # Deterministic rules use a small explicit marker convention: statement begins "avoid: ".
        if rule.statement.casefold().startswith("avoid: "):
            phrase = rule.statement[7:].strip()
            if phrase and phrase.casefold() in lowered:
                findings.append(ReviewFinding(rule_id=rule.id, rule_version=rule.version,
                                              quote=phrase, description=rule.short_title,
                                              evidence=f"Exact phrase found: {phrase}",
                                              recommendation="Review this occurrence against the approved rule.",
                                              severity=rule.severity))
    return findings
