# Connectors

## Gmail

1. Create a Google OAuth desktop client and download its client secret JSON.
2. Set `GMAIL_CLIENT_SECRET_FILE` to its absolute path.
3. Enable `connectors.gmail.enabled` in `reaper.yaml`.
4. Run `uv run reaper gmail-auth`.

The OAuth token is stored at the configured ignored path with file mode `0600`. Gmail
messages are created from an approved payload; the engine does not alter recipient,
subject, or body after approval.

## Telegram

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, then enable
`connectors.telegram.enabled`. Test with:

```bash
uv run reaper report --send
```

The persistent scheduler sends at `owner.report_hour` in `owner.timezone`.

## eBay

Set `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, and `EBAY_REFRESH_TOKEN`. Configure the
marketplace and add public image URLs plus the seller's fulfillment, payment, return, and
location policy IDs to the action package before approval.

The connector creates an inventory item, creates one fixed-price offer, and publishes that
offer. Publication requires an approved `publish_listing` action.

## Issuer and merchant channels

Card issuers and subscription merchants do not expose one universal API. Reaper exports a
complete JSON action package with evidence and language. The operator completes it in the
issuer's authenticated portal, secure message center, or phone channel.

