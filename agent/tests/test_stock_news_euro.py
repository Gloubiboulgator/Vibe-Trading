"""Euro-area listings get news by company name, kept only when tied to the listing (2026-11-09).

get_stock_news answered "unsupported market" for SOI.PA and TEP.PA. Yahoo's
news search finds nothing for "SOI.PA", and the bare "SOI" is Stolt-Nielsen.
"""

from __future__ import annotations

import json

import pytest

from src.tools import stock_news_tool
from src.tools.stock_news_tool import StockNewsTool

pytestmark = pytest.mark.unit


def _news(title: str, tickers: list[str]) -> dict:
    return {"title": title, "publisher": "x", "link": "https://x", "providerPublishTime": 1794200000, "relatedTickers": tickers}


def test_a_paris_listing_is_searched_by_name_and_filtered(monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(stock_news_tool.yahoo_client, "search", lambda q: [{"symbol": "SOI.PA", "shortname": "SOITEC", "longname": "Soitec SA"}])

    def _search_news(query: str, count: int) -> list[dict]:
        seen.append(query)
        return [
            _news("Soitec wins UBS upgrade", ["SOI.PA", "SOIT"]),
            _news("Stolt-Nielsen results", ["SOIEF"]),
            _news("European shares fall", ["^STOXX", "SOI.PA"]),
        ]

    monkeypatch.setattr(stock_news_tool.yahoo_client, "search_news", _search_news)
    payload = json.loads(StockNewsTool().execute(code="SOI.PA", limit=5))
    assert payload["ok"] and payload["market"] == "eu" and seen == ["Soitec SA"]
    assert [a["title"] for a in payload["data"]["articles"]] == ["Soitec wins UBS upgrade", "European shares fall"]


def test_an_unknown_listing_returns_no_articles_rather_than_another_company(monkeypatch) -> None:
    monkeypatch.setattr(stock_news_tool.yahoo_client, "search", lambda q: [{"symbol": "SOIEF", "shortname": "Stolt"}])
    monkeypatch.setattr(stock_news_tool.yahoo_client, "search_news", lambda q, c: pytest.fail("no name, no search"))
    payload = json.loads(StockNewsTool().execute(code="SOI.PA", limit=5))
    assert payload["ok"] and payload["data"]["articles"] == []
