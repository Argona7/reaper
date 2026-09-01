from __future__ import annotations

import base64
import os
from typing import Any

import httpx


class EbayConnector:
    """eBay Sell Inventory API connector with refresh-token authentication."""

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        marketplace_id: str | None = None,
        environment: str = "production",
    ) -> None:
        self.client_id = client_id or os.environ.get("EBAY_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("EBAY_CLIENT_SECRET", "")
        self.refresh_token = refresh_token or os.environ.get("EBAY_REFRESH_TOKEN", "")
        self.marketplace_id = marketplace_id or os.environ.get("EBAY_MARKETPLACE_ID", "EBAY_US")
        if not self.client_id or not self.client_secret or not self.refresh_token:
            raise RuntimeError(
                "EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, and EBAY_REFRESH_TOKEN are required"
            )
        host = "api.ebay.com" if environment == "production" else "api.sandbox.ebay.com"
        self.base_url = f"https://{host}"

    def _access_token(self) -> str:
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{self.base_url}/identity/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "scope": "https://api.ebay.com/oauth/api_scope/sell.inventory",
                },
            )
            response.raise_for_status()
            return str(response.json()["access_token"])

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
            "Content-Language": "en-US",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
        }

    def publish_listing(self, payload: dict[str, Any]) -> dict[str, Any]:
        sku = str(payload["sku"])
        currency = str(payload.get("currency", "USD"))
        amount = f"{int(payload['price_cents']) / 100:.2f}"
        image_urls = payload.get("image_urls", [])
        if not image_urls:
            raise ValueError(
                "eBay requires public image_urls; local photo_paths must be uploaded first"
            )
        inventory = {
            "availability": {
                "shipToLocationAvailability": {"quantity": int(payload.get("quantity", 1))}
            },
            "condition": payload["condition"],
            "product": {
                "title": payload["title"],
                "description": payload["description"],
                "imageUrls": image_urls,
            },
        }
        headers = self._headers()
        with httpx.Client(timeout=30) as client:
            item_response = client.put(
                f"{self.base_url}/sell/inventory/v1/inventory_item/{sku}",
                headers=headers,
                json=inventory,
            )
            item_response.raise_for_status()
            offer_response = client.post(
                f"{self.base_url}/sell/inventory/v1/offer",
                headers=headers,
                json={
                    "sku": sku,
                    "marketplaceId": self.marketplace_id,
                    "format": "FIXED_PRICE",
                    "categoryId": payload["category_id"],
                    "listingDescription": payload["description"],
                    "pricingSummary": {"price": {"currency": currency, "value": amount}},
                    "merchantLocationKey": payload["merchant_location_key"],
                    "listingPolicies": {
                        "fulfillmentPolicyId": payload["fulfillment_policy_id"],
                        "paymentPolicyId": payload["payment_policy_id"],
                        "returnPolicyId": payload["return_policy_id"],
                    },
                },
            )
            offer_response.raise_for_status()
            offer_id = str(offer_response.json()["offerId"])
            publish_response = client.post(
                f"{self.base_url}/sell/inventory/v1/offer/{offer_id}/publish",
                headers=headers,
            )
            publish_response.raise_for_status()
            published = publish_response.json()
        return {
            "sku": sku,
            "offer_id": offer_id,
            "listing_id": published.get("listingId"),
            "marketplace_id": self.marketplace_id,
        }
