# Declared rule conflicts

Relations are retained in the complete rule record and therefore in the proposal content reviewed before approval. A relation does not grant permission to change another rule.

An explicitly declared conflict uses these fields:

    {
      "type": "conflicts_with",
      "target_id": "R-SYNTHETIC-OTHER",
      "status": "approved"
    }

Use status candidate while the relationship is only a suggestion. A missing status is treated as candidate. The system does not infer approval from similarity, role, recency, or a discussion message. Making a relationship authoritative requires including it in a rule proposal and explicitly approving that proposal's exact content hash.

Context retrieval reports an unresolved conflict when both rules are active, match the current paper, section, and task, and at least one contains an approved conflicts_with relation to the other. Both rules remain available; retrieval does not choose a winner or change either rule. Reciprocal declarations produce one diagnostic, including both rule identifiers and their versions.

Conflict detection precedes the context budget. Omitting a conflicting rule because of a size limit does not hide the conflict or make the bundle complete. A conflicting rule belonging to another paper does not create a conflict for the current paper, and its text is not included in the diagnostic.

An approved conflict targeting a missing rule, or the rule itself, produces a relation issue requiring review. The bundle's complete field is false if mandatory rules were omitted, unresolved conflicts exist, or these relation issues exist. It does not certify that a manuscript passed review.

Other relation types remain stored in rule records. This diagnostic does not supply their inheritance, exception, or replacement behavior. Those behaviors and natural-language scope exceptions need separate interpretation and verification.
