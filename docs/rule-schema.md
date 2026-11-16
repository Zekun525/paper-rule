# Rule schema

Domain schemas are Pydantic v2 models in `src/paperrule/domain/models.py`. Rules include status, scope filters, source feedback identifiers, severity and check method. Proposal hashes are computed from canonical JSON content. Schema migration tooling is not yet implemented; the memory manifest currently records schema version 1.
