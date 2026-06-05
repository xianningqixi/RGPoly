from __future__ import annotations

import json
from typing import Any

import httpx

from .models import ActivityTrade, MarketToken, OrderBook, fnum


DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


def parse_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def token_for_outcome(market: dict[str, Any], outcome: str) -> MarketToken | None:
    outcomes = parse_json_list(market.get("outcomes"))
    token_ids = parse_json_list(market.get("clobTokenIds") or market.get("clob_token_ids"))
    target = outcome.lower().strip()
    for idx, name in enumerate(outcomes):
        if str(name).lower().strip() == target and idx < len(token_ids):
            return MarketToken(token_id=str(token_ids[idx]), outcome=str(name))
    tokens = market.get("tokens")
    if isinstance(tokens, list):
        for token in tokens:
            if str(token.get("outcome") or "").lower().strip() == target:
                token_id = str(token.get("token_id") or token.get("tokenId") or "")
                if token_id:
                    return MarketToken(token_id=token_id, outcome=str(token.get("outcome") or outcome))
    return None


class PolymarketClient:
    def __init__(self, timeout_sec: float = 4.0):
        timeout = httpx.Timeout(timeout_sec)
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": "rgpoly/0.2", "Accept": "application/json"},
            http2=True,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch_activity(self, wallet_alias: str, wallet_address: str, limit: int) -> list[ActivityTrade]:
        response = await self.client.get(
            f"{DATA_API}/activity",
            params={"user": wallet_address, "limit": limit, "offset": 0},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return []
        return [ActivityTrade.from_api(wallet_alias, wallet_address, row) for row in payload if isinstance(row, dict)]

    async def market_by_slug(self, slug: str) -> dict[str, Any] | None:
        if not slug:
            return None
        response = await self.client.get(f"{GAMMA_API}/markets", params={"slug": slug})
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload:
            return payload[0]

        response = await self.client.get(f"{GAMMA_API}/events", params={"slug": slug})
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload:
            markets = payload[0].get("markets") or []
            for market in markets:
                if isinstance(market, dict) and market.get("slug") == slug:
                    return market
        return None

    async def token_for_trade(self, trade: ActivityTrade) -> MarketToken | None:
        if trade.asset:
            return MarketToken(token_id=trade.asset, outcome=trade.outcome)
        market = await self.market_by_slug(trade.slug)
        if not market:
            return None
        return token_for_outcome(market, trade.outcome)

    async def order_book(self, token_id: str) -> OrderBook | None:
        if not token_id:
            return None
        response = await self.client.get(f"{CLOB_API}/book", params={"token_id": token_id})
        response.raise_for_status()
        book = response.json()
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        best_bid = max((fnum(row.get("price")) for row in bids if isinstance(row, dict)), default=0.0)
        best_ask = min((fnum(row.get("price")) for row in asks if isinstance(row, dict)), default=0.0)
        ask_depth = sum(fnum(row.get("price")) * fnum(row.get("size")) for row in asks if isinstance(row, dict))
        bid_depth = sum(fnum(row.get("price")) * fnum(row.get("size")) for row in bids if isinstance(row, dict))
        return OrderBook(
            token_id=token_id,
            best_bid=best_bid,
            best_ask=best_ask,
            ask_depth_usdc=ask_depth,
            bid_depth_usdc=bid_depth,
            raw=book if isinstance(book, dict) else {},
        )

