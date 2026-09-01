# Architecture

Reaper separates evidence, reasoning, permission, and execution into different layers.

## Data plane

Statement parsers normalize CSV, OFX/QFX, and text PDF rows into `Transaction` objects.
Each object has a SHA-256 fingerprint over date, description, amount, and account suffix.
SQLite uses that fingerprint as the primary key, so repeated imports do not duplicate data.

## Skill plane

Six deterministic skills read normalized transactions and typed operator inputs. A skill
can emit:

- `Opportunity`: a quantified candidate with confidence and evidence;
- `ProposedAction`: an exact external operation payload;
- notes: human-readable run facts.

The skills do not call connectors directly.

## Model plane

`GrokDraftingClient` uses xAI's OpenAI-compatible endpoint. It receives an objective,
facts, constraints, and an optional template, and must return typed JSON. The model is not
used for arithmetic, recurring-charge detection, permissions, or state transitions.

## Control plane

`ApprovalPolicy` evaluates every proposed action. The database stores action status,
idempotency key, approval actor, reason, timestamps, result, and error. The engine refuses
to execute an action outside the `approved` state.

## Execution plane

Registered connectors currently cover Gmail, Telegram, and eBay. Bank and merchant
operations without a stable public API are exported as action packages for completion in
the correct issuer channel.

## Failure semantics

Execution follows `approved → executing → succeeded|failed`. A connector exception is
persisted on the action and appended to the event log. A failed action is never retried
implicitly because many financial endpoints are not safely repeatable.

