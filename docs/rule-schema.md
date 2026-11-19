# Rule schema

Domain schemas are Pydantic v2 models in `src/paperrule/domain/models.py`. Rules include status, scope filters, source feedback identifiers, severity and check method. Proposal hashes are computed from canonical JSON content. Schema migration tooling is not yet implemented; the memory manifest currently records schema version 1.

AI discussion replies must explicitly name at least one supported scope level: `global`, `research_type`, `publication`, `paper` or `section_task`. Empty or unknown levels reject the model revision and retain the previous draft together with the user message and a safe validation diagnostic. Concrete paper, section and task filters continue to determine applicability; a scope level alone does not supply a missing filter.

This validation applies to incoming AI discussion replies. It does not rewrite historical rules, proposals or approval hashes, and it does not introduce a memory migration. Older records with empty scope levels still require explicit review through a new proposal.
