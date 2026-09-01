# Security policy

## Supported versions

Security fixes are applied to the latest release on `main`.

## Report a vulnerability

Open a private GitHub security advisory for vulnerabilities. Do not put OAuth tokens,
statement data, card numbers, email contents, or exploit details in a public issue.

## Local data

Reaper keeps statements, SQLite data, evidence, OAuth tokens, logs, keys, and session files
in ignored paths. Never commit a runtime directory. Gmail tokens are written with mode
`0600`.

## Threat model

Primary risks are malicious statement text, prompt injection inside emails/documents,
connector credential theft, replayed side effects, wrong-recipient actions, and changed
payloads after approval. Controls include deterministic parsers, a fact-only model prompt,
connector isolation, idempotency keys, immutable approval payloads, and a persistent event
log.

