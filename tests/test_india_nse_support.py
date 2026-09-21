# -*- coding: utf-8 -*-
"""Regression tests for Indian NSE (`.NS`) market support.

Covers the 10 test symbols:
RELIANCE.NS / TCS.NS / INFY.NS / HDFCBANK.NS / ICICIBANK.NS / SBIN.NS /
BHARTIARTL.NS / LT.NS / SUNPHARMA.NS / ITC.NS
"""

from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd

from api.v1.endpoints.stocks import _STOCK_CODE_RE
from data_provider.base import (
    _market_tag,
    DataFetcherManager,
    normalize_stock_code,
)
from data_provider.yfinance_fetcher import YfinanceFetcher
from src.core.market_profile import get_profile
from src.core.trading_calendar import (
    MARKET_EXCHANGE,
    MARKET_TIMEZONE,
    get_market_for_stock,
)
from src.data.stock_mapping import STOCK_ENGLISH_NAME_MAP, STOCK_NAME_MAP
from src.market_context import detect_market, get_market_guidelines, get_market_role
from src.services.market_symbol_utils import (
    get_suffix_market,
    is_in_suffix_symbol,
    normalize_suffix_market_symbol,
    suffix_base_lookup_allowed,
)
from src.services.stock_code_utils import (
    is_code_like,
    normalize_code,
    resolve_daily_stock_identity,
)

NSE_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "LT.NS",
    "SUNPHARMA.NS",
    "ITC.NS",
]


def test_suffix_market_detection_returns_in_for_all_nse_symbols() -> None:
    for symbol in NSE_SYMBOLS:
        assert get_suffix_market(symbol) == "in", symbol
        assert is_in_suffix_symbol(symbol) is True, symbol
        assert normalize_suffix_market_symbol(symbol.lower()) == symbol, symbol


def test_suffix_market_rejects_invalid_nse_forms() -> None:
    assert get_suffix_market("RELIANCE") is None
    assert get_suffix_market("123.NS") is None  # non-alphabetic base
    assert get_suffix_market("RELIANCE.XX") is None
    assert get_suffix_market("RELIANCE.SZ") is None


def test_bare_base_lookup_is_disabled_for_in() -> None:
    for symbol in NSE_SYMBOLS:
        assert suffix_base_lookup_allowed(symbol) is False, symbol


def test_normalization_preserves_ns_suffix() -> None:
    for symbol in NSE_SYMBOLS:
        assert normalize_stock_code(symbol) == symbol, symbol
        assert normalize_code(symbol) == symbol, symbol
        assert is_code_like(symbol) is True, symbol


def test_daily_stock_identity_resolves_to_in() -> None:
    for symbol in NSE_SYMBOLS:
        identity = resolve_daily_stock_identity(symbol)
        assert identity is not None, symbol
        assert identity.market == "in", symbol
        assert identity.normalized_code == symbol, symbol
        assert identity.refill_code == symbol, symbol
        assert symbol in identity.code_candidates, symbol


def test_market_detectors_return_in_for_all_nse_symbols() -> None:
    for symbol in NSE_SYMBOLS:
        assert detect_market(symbol) == "in", symbol
        assert get_market_for_stock(symbol) == "in", symbol
        assert _market_tag(symbol) == "in", symbol


def test_trading_calendar_registers_in_exchange_and_ist_timezone() -> None:
    assert MARKET_EXCHANGE["in"] == "XNSE"
    assert MARKET_TIMEZONE["in"] == "Asia/Kolkata"


def test_market_profile_returns_india_profile() -> None:
    profile = get_profile("in")
    assert profile.region == "in"
    assert profile.mood_index_code == "NSEI"
    assert profile.has_market_stats is False
    assert profile.has_sector_rankings is False


def test_market_context_roles_and_guidelines_for_in() -> None:
    assert get_market_role("TCS.NS") == "印度股"
    assert get_market_role("TCS.NS", "en") == "India stock"
    zh = get_market_guidelines("RELIANCE.NS")
    en = get_market_guidelines("RELIANCE.NS", "en")
    assert "印度" in zh
    assert "India NSE" in en
    # NSE guidelines must not fall back to A-share context.
    for text in (zh, en):
        assert "印度" in text or "India" in text
    assert "不要套用 A 股" in zh


def test_api_stock_code_regex_accepts_all_nse_symbols() -> None:
    for symbol in NSE_SYMBOLS:
        assert _STOCK_CODE_RE.match(symbol) is not None, symbol
    assert _STOCK_CODE_RE.match("RELIANCE") is None
    assert _STOCK_CODE_RE.match("123.NS") is None
    assert _STOCK_CODE_RE.match("RELIANCE.SZ") is None
    # LT.NS (2-letter base) must not be mis-validated as a bare US ticker shape.
    assert _STOCK_CODE_RE.match("LT.NS") is not None
    # A plain US ticker must still be accepted.
    assert _STOCK_CODE_RE.match("AAPL") is not None
    assert _STOCK_CODE_RE.match("TSLA") is not None


def test_stock_name_maps_cover_all_nse_symbols() -> None:
    for symbol in NSE_SYMBOLS:
        assert STOCK_NAME_MAP[symbol], symbol
        assert STOCK_ENGLISH_NAME_MAP[symbol], symbol


def test_yfinance_converts_ns_codes_verbatim() -> None:
    fetcher = YfinanceFetcher()
    for symbol in NSE_SYMBOLS:
        # Must pass through the `.NS` suffix unchanged (never `.SZ`).
        assert fetcher._convert_stock_code(symbol) == symbol, symbol


class _FakeFastInfo:
    lastPrice = 2500.0
    previousClose = 2400.0
    open = 2420.0
    dayHigh = 2520.0
    dayLow = 2410.0
    lastVolume = 1000000
    marketCap = 1500000000000.0


def test_yfinance_realtime_quote_returns_in_market_and_inr_currency() -> None:
    fetcher = YfinanceFetcher()
    fake_ticker = MagicMock()
    type(fake_ticker).fast_info = PropertyMock(return_value=_FakeFastInfo())
    fake_ticker.info = {
        "shortName": "Reliance Industries Ltd.",
        "longName": "Reliance Industries Limited",
        "trailingPE": 22.0,
        "priceToBook": 1.5,
        "currency": "INR",
    }

    with patch("yfinance.Ticker", return_value=fake_ticker):
        quote = fetcher.get_realtime_quote("RELIANCE.NS")

    assert quote is not None
    assert quote.market == "in"
    assert quote.currency == "INR"
    assert quote.code == "RELIANCE.NS"
    assert quote.price == 2500.0
    assert quote.name == "Reliance Industries Ltd."


def test_yfinance_realtime_quote_rejects_unsupported_nse_bare_codes() -> None:
    fetcher = YfinanceFetcher()
    with patch("yfinance.Ticker") as mock_ticker:
        quote = fetcher.get_realtime_quote("RELIANCE")
        mock_ticker.assert_not_called()
    assert quote is None


def test_yfinance_in_main_indices_use_nse_and_bse_yahoo_symbols() -> None:
    fetcher = YfinanceFetcher()
    captured = []

    def fake_fetch(_yf, yf_code, name, return_code):
        captured.append((yf_code, name, return_code))
        return {"code": return_code, "name": name, "current": 1.0}

    fetcher._fetch_yf_ticker_data = fake_fetch  # type: ignore[method-assign]

    in_indices = fetcher.get_main_indices("in") or []
    assert {item["code"] for item in in_indices} == {"NSEI", "BSESN"}
    assert ("^NSEI", "Nifty 50", "NSEI") in captured
    assert ("^BSESN", "SENSEX", "BSESN") in captured


class _FakeFetcher:
    """Minimal fetcher stub to exercise daily-market routing for ``in``."""

    def __init__(self, name: str):
        self.name = name
        self.priority = 0 if name != "YfinanceFetcher" else 4
        self.calls = []

    def get_daily_data(self, stock_code, start_date=None, end_date=None, days=30):
        self.calls.append(stock_code)
        return pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-09-18")],
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [100],
                "amount": [100.0],
                "pct_chg": [0.0],
            }
        )

    def is_available_for_request(self, capability: str = "") -> bool:
        return True


def test_data_fetcher_manager_routes_in_daily_only_to_yfinance() -> None:
    efinance = _FakeFetcher("EfinanceFetcher")
    akshare = _FakeFetcher("AkshareFetcher")
    yfinance = _FakeFetcher("YfinanceFetcher")
    manager = DataFetcherManager(fetchers=[efinance, akshare, yfinance])

    with patch("data_provider.base.record_provider_run_started"), patch("data_provider.base.record_provider_run"):
        in_df, in_source = manager.get_daily_data("RELIANCE.NS")

    assert in_source == "YfinanceFetcher"
    assert not in_df.empty
    assert efinance.calls == []
    assert akshare.calls == []
    assert yfinance.calls == ["RELIANCE.NS"]