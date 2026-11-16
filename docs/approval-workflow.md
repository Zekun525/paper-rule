# Approval workflow

Create a proposal using `paperrule proposal draft`. Discussion messages are append-only within the proposal and can carry a revised full RuleRecord through the API. Each proposal version receives a content hash. Approval requires that hash and checks that the base rule version has not changed. Only then is an active rule written and an ApprovalEvent appended. Reject/defer never activate a rule.
