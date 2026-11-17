"""Export stored review data without interpreting manuscript text as Markdown."""

import json
import re

from paperrule.domain.models import ReviewReport


def markdown_report(report: ReviewReport) -> str:
    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    longest = max((len(run) for run in re.findall(chr(96) + "+", payload)), default=0)
    fence = chr(96) * max(3, longest + 1)
    return chr(10).join([
        "# PaperRule review report", "",
        "This export preserves imported review data. Importing a report does not approve rules",
        "or establish that every applicable rule was checked.", "",
        fence + "json", payload, fence, "",
    ])
