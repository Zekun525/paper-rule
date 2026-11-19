"""Validate internal evidence bindings without certifying external manuscript content."""

from paperrule.domain.models import ReviewReport, digest
from paperrule.review.manuscript_semantic import ManuscriptJudgment


def validate_semantic_evidence(report: ReviewReport) -> None:
    if not report.semantic_evidence:
        return
    snapshots = {rule.id: rule for rule in report.rule_snapshot}
    files = {item.path: item for item in report.files}
    if len(files) != len(report.files):
        raise ValueError("Semantic evidence requires unambiguous input file paths")
    if not snapshots or report.rule_snapshot_sha256 is None:
        raise ValueError("Semantic evidence requires a hashed rule snapshot")
    seen = set()
    for item in report.semantic_evidence:
        identity = (item.rule_id, item.file_path)
        if identity in seen:
            raise ValueError("Duplicate semantic evidence for the same rule and file")
        seen.add(identity)
        rule = snapshots.get(item.rule_id)
        if (rule is None or rule.version != item.rule_version
                or digest(rule) != item.rule_sha256):
            raise ValueError("Semantic evidence does not match its rule snapshot")
        document = files.get(item.file_path)
        if document is None or document.sha256 != item.file_sha256:
            raise ValueError("Semantic evidence does not match its input file record")
        expected_mode = "changed_lines" if report.diff_mode else "full_text"
        if item.selection.get("mode") != expected_mode:
            raise ValueError("Semantic evidence selection does not match the review mode")
        completed = item.status in {"checked", "findings"}
        if not completed and item.checked_line_count:
            raise ValueError("Incomplete semantic evidence cannot claim checked lines")
        if completed:
            numbers = item.selection.get("line_numbers")
            if (not isinstance(numbers, list) or not numbers
                    or any(type(number) is not int or number <= 0 for number in numbers)
                    or len(set(numbers)) != len(numbers)
                    or item.checked_line_count != len(numbers)):
                raise ValueError("Semantic checked lines do not match the recorded selection")
            if (not item.provider.strip() or item.provider in {"fake", "manual"}
                    or not item.model.strip() or not item.prompt_version.strip()
                    or item.error is not None):
                raise ValueError("Completed semantic evidence requires valid provider metadata")
        judgment = None
        if item.judgment:
            judgment = ManuscriptJudgment.model_validate(item.judgment)
            if (judgment.rule_id != item.rule_id
                    or judgment.rule_version != item.rule_version):
                raise ValueError("Semantic judgment references a different rule version")
            if (not judgment.explanation.strip()
                    or any(not question.strip() or len(question) > 2000
                           for question in judgment.unresolved)
                    or (judgment.verdict == "violation") != bool(judgment.findings)):
                raise ValueError("Semantic judgment contains inconsistent findings or reasoning")
            expected_status = (
                "not_reviewed" if judgment.verdict == "uncertain"
                else "incomplete" if judgment.unresolved
                else "findings" if judgment.findings else "checked"
            )
            if item.status != expected_status:
                raise ValueError("Semantic status contradicts its original judgment")
            if len(judgment.findings) != len(item.findings):
                raise ValueError("Semantic evidence omits or adds original findings")
        elif item.status != "unavailable" or item.findings:
            raise ValueError("Semantic result requires its original judgment")
        if item.status == "checked" and item.findings:
            raise ValueError("Compliant semantic evidence cannot contain findings")
        if item.status == "findings" and not item.findings:
            raise ValueError("Semantic findings status requires findings")
        for index, finding in enumerate(item.findings):
            if (finding.rule_id != item.rule_id
                    or finding.rule_version != item.rule_version
                    or finding.review_type != "semantic"
                    or not finding.location.startswith(item.file_path + ":")
                    or finding not in report.findings):
                raise ValueError("Semantic finding is inconsistent with its report evidence")
            original = judgment.findings[index]
            last_line = original.line + len(original.quote.splitlines()) - 1
            location = item.file_path + ":" + str(original.line)
            if last_line != original.line:
                location += "-" + str(last_line)
            if (not original.quote.strip() or not original.explanation.strip()
                    or not original.recommendation.strip()
                    or finding.location != location or finding.quote != original.quote
                    or finding.evidence != original.explanation
                    or finding.recommendation != original.recommendation):
                raise ValueError("Semantic finding differs from its original quoted judgment")
    if report.semantic_status == "reviewed" and any(
        item.status not in {"checked", "findings"} for item in report.semantic_evidence
    ):
        raise ValueError("Incomplete semantic evidence cannot claim completed semantic review")
