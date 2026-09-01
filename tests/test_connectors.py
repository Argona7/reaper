from __future__ import annotations

import base64

import pytest
import respx
from httpx import Response

from reaper.connectors.ebay import EbayConnector
from reaper.connectors.gmail import GmailConnector
from reaper.connectors.telegram import TelegramConnector


@respx.mock
def test_telegram_connector_sends_message() -> None:
    route = respx.post("https://api.telegram.org/bottoken/sendMessage").mock(
        return_value=Response(200, json={"ok": True, "result": {"message_id": 17}})
    )
    result = TelegramConnector(bot_token="token", chat_id="42").send("report")
    assert route.called
    assert result == {"message_id": 17, "chat_id": "42"}


def test_gmail_raw_message_contains_headers() -> None:
    raw = GmailConnector._raw_message("bank@example.com", "APR review", "Hello")
    decoded = base64.urlsafe_b64decode(raw).decode()
    assert "To: bank@example.com" in decoded
    assert "Subject: APR review" in decoded


def test_gmail_create_draft_and_send(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls: list[tuple[str, dict]] = []

    class Request:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def execute(self) -> dict:
            return self.payload

    class Drafts:
        def create(self, **kwargs):
            calls.append(("draft", kwargs))
            return Request({"id": "draft-1", "message": {"id": "message-1"}})

    class Messages:
        def send(self, **kwargs):
            calls.append(("send", kwargs))
            return Request({"id": "message-2", "threadId": "thread-1"})

    class Users:
        def drafts(self):
            return Drafts()

        def messages(self):
            return Messages()

    class Service:
        def users(self):
            return Users()

    connector = GmailConnector(tmp_path / "token.json")
    monkeypatch.setattr(connector, "_service", lambda: Service())
    draft = connector.create_draft(to="bank@example.com", subject="APR", body="Hello")
    sent = connector.send(to="bank@example.com", subject="APR", body="Hello")
    assert draft["draft_id"] == "draft-1"
    assert sent["thread_id"] == "thread-1"
    assert [name for name, _ in calls] == ["draft", "send"]
    with pytest.raises(ValueError, match="Recipient"):
        connector.send(to="", subject="APR", body="Hello")


@respx.mock
def test_ebay_publish_listing_runs_inventory_offer_publish() -> None:
    token_route = respx.post("https://api.sandbox.ebay.com/identity/v1/oauth2/token").mock(
        return_value=Response(200, json={"access_token": "access"})
    )
    item_route = respx.put(
        "https://api.sandbox.ebay.com/sell/inventory/v1/inventory_item/ps5"
    ).mock(return_value=Response(204))
    offer_route = respx.post("https://api.sandbox.ebay.com/sell/inventory/v1/offer").mock(
        return_value=Response(201, json={"offerId": "offer-1"})
    )
    publish_route = respx.post(
        "https://api.sandbox.ebay.com/sell/inventory/v1/offer/offer-1/publish"
    ).mock(return_value=Response(200, json={"listingId": "listing-1"}))
    connector = EbayConnector(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        environment="sandbox",
    )
    result = connector.publish_listing(
        {
            "sku": "ps5",
            "title": "PlayStation 5",
            "description": "Tested",
            "condition": "USED_EXCELLENT",
            "price_cents": 38_900,
            "quantity": 1,
            "category_id": "139971",
            "image_urls": ["https://example.com/front.jpg"],
            "merchant_location_key": "home",
            "fulfillment_policy_id": "f1",
            "payment_policy_id": "p1",
            "return_policy_id": "r1",
        }
    )
    assert token_route.call_count == 1
    assert item_route.called and offer_route.called and publish_route.called
    assert result["listing_id"] == "listing-1"


def test_ebay_requires_public_images() -> None:
    connector = EbayConnector(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        environment="sandbox",
    )
    with pytest.raises(ValueError, match="public image_urls"):
        connector.publish_listing({"sku": "x", "price_cents": 100})
