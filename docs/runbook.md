# Operating runbook

## Daily

1. Import new statement exports or sync the configured read-only source.
2. Run all six skills.
3. Review new opportunities against source evidence.
4. Approve or reject each side effect independently.
5. Execute approved connector actions.
6. Generate the 21:00 report from persisted outcomes.

## APR sequence

1. Fill the issuer's verified secure-message or retention address.
2. Approve and send stage 1.
3. Store the issuer reply and reference number as evidence.
4. If no complete review occurred, create and approve stage 2.
5. Before accepting a rate, use stage 3 to capture every term in writing.
6. Update `current_balance_cents` and `apr_basis_points` only from verified statements or
   written issuer confirmation.

## Balance transfer

Update offers from current written terms. Run the skill, inspect the calculation, and
verify eligibility, credit limit, post-promo APR, fee, deadline, and issuer restrictions.
A transfer is never submitted from an analysis result alone.

## Dispute

Duplicate detection creates a candidate. Confirm the charge with receipts and the merchant,
attach evidence, choose the truthful dispute reason, and then approve submission.

## Asset listing

The operator selects the asset. Verify ownership, condition, photos, price, shipping,
returns, and payout account. Add public image URLs and seller policy IDs, approve the exact
payload, then publish.

## Incident response

If a connector times out, inspect the external service before retrying. Record whether the
side effect occurred. Do not approve a duplicate action until the original action's
external state is known.

