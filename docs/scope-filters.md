# Explicit scope filters

Approved rules can narrow their existing paper, research type, venue, article type,
section and task fields with include and exclude lists. Matching never executes
filter text or treats it as a command.

Use a prefix followed by an exact value:

| Prefix | Compared value | Synthetic example |
| --- | --- | --- |
| paper | PaperProfile.paper_id | paper:SYNTHETIC-A |
| research_type | PaperProfile.research_type | research_type:theory |
| venue | PaperProfile.venue | venue:SYNTHETIC-TIT |
| article_type | PaperProfile.article_type | article_type:full |
| section | Selected section | section:Proof |
| task | Selected task | task:proof_rewrite |

Prefixes ignore case and surrounding whitespace. Values are trimmed and compared
exactly, including case. No wildcard, regular-expression or script syntax is
evaluated.

Within include, alternatives for the same prefix are joined with OR; different
prefixes are joined with AND. Existing scope fields also remain required.
For example, paper:SYNTHETIC-A together with section:Proof loads the rule only for
that paper's Proof section. Multiple venue selectors permit several venues.
Unqualified include entries are exact paper IDs.

Any matching exclude entry excludes the rule. Unqualified exclusions preserve the
earlier paper-ID-or-section-name behavior. New conditions should use prefixes.

Unknown prefixes and empty prefixed values require clarification. If the known
scope otherwise matches, the rule is withheld, context.scope_issues explains why,
and context.complete is false. Unrelated paper filters are applied first. Diagnostic
metadata does not include the withheld rule's text. Manuscript checks record an
unavailable condition rather than claiming that rule was checked. Regression
cases using explicit filters require a paper profile.

These selectors do not interpret natural-language exceptions. Exceptions remain
part of the approved rule and require a separate semantic evaluation workflow;
complete acceptance of that workflow is still outstanding. Tests of synthetic
selector matching do not establish model quality or full product acceptance.
