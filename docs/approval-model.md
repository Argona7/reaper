# Approval model

An approval binds to one action ID and one deterministic idempotency key.

## State machine

```text
proposed ──approve──> approved ──execute──> executing ──> succeeded
    │                                             └────> failed
    └──reject──────> rejected
```

Only `proposed` actions can be approved or rejected. Only `approved` actions can execute.
Changing the action payload changes the idempotency key, so the engine creates a new
approval request instead of reusing the old decision.

## Default policy

Automatic: read, analyze, calculate, draft, report.

Approval required: send email, cancel service, submit dispute, transfer balance, make
payment, publish/edit/delete listing, and spend.

Unknown verbs fail closed and require approval.

## Approval review checklist

Before approving, verify:

1. the correct account/merchant and recipient;
2. the exact amount, terms, deadline, and fees;
3. every claim in the outbound language;
4. attachments and evidence paths;
5. the connector destination and any irreversible consequence.

