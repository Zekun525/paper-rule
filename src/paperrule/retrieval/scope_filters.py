"""Match approved scope selectors without executing or guessing their contents."""

from paperrule.domain.models import PaperProfile, RuleScope

UNRESOLVED_SCOPE = "scope filters require clarification"
FIELDS = {"paper", "research_type", "venue", "article_type", "section", "task"}


def _parse(entries: list[str]) -> tuple[dict[str, set[str]], set[str], bool]:
    groups: dict[str, set[str]] = {}
    bare: set[str] = set()
    unresolved = False
    for entry in entries:
        key, separator, value = entry.strip().partition(":")
        if not separator:
            if key:
                bare.add(key)
            else:
                unresolved = True
            continue
        key, value = key.strip().casefold(), value.strip()
        if key not in FIELDS or not value:
            unresolved = True
        else:
            groups.setdefault(key, set()).add(value)
    return groups, bare, unresolved


def match_filters(
    scope: RuleScope, paper: PaperProfile, section: str, task: str,
) -> tuple[bool, str]:
    actual = {
        "paper": paper.paper_id, "research_type": paper.research_type,
        "venue": paper.venue, "article_type": paper.article_type,
        "section": section, "task": task,
    }
    include, include_ids, include_unknown = _parse(scope.include)
    if any(actual[key] not in values for key, values in include.items()):
        return False, "explicit include filter does not match"
    # Unqualified includes name papers, never sections of unrelated papers.
    if include_ids and paper.paper_id not in include_ids:
        return False, "explicit include filter does not match"
    exclude, legacy_exclusions, exclude_unknown = _parse(scope.exclude)
    if (
        any(actual[key] in values for key, values in exclude.items())
        or paper.paper_id in legacy_exclusions or section in legacy_exclusions
    ):
        return False, "explicitly excluded"
    if include_unknown or exclude_unknown:
        return False, UNRESOLVED_SCOPE
    return True, "scope matches paper, section, and task"
