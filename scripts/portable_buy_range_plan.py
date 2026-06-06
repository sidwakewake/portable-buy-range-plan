from __future__ import annotations

import argparse
import csv
import io
import math
import urllib.request
from dataclasses import dataclass
from typing import Any


LEVERAGED_ETFS = {
    "TQQQ", "SQQQ", "UPRO", "SPXU", "SPXL", "SOXL", "SOXS", "TECL", "TECS",
    "FNGU", "FNGD", "LABU", "LABD", "WEBL", "WEBS", "UDOW", "SDOW",
}


@dataclass
class PriceHistory:
    symbol: str
    source: str
    close: list[float]
    high: list[float]
    low: list[float]
    name: str = ""
    quote_type: str = ""


def positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def mean_tail(values: list[float], count: int) -> float | None:
    usable = [v for v in values[-count:] if positive_float(v) is not None]
    return sum(usable) / len(usable) if usable else None


def max_tail(values: list[float], count: int) -> float | None:
    usable = [v for v in values[-count:] if positive_float(v) is not None]
    return max(usable) if usable else None


def realized_volatility(close: list[float], count: int = 252) -> float | None:
    sigma = daily_sigma(close, count=count)
    return sigma * math.sqrt(252) if sigma is not None else None


def daily_sigma(close: list[float], count: int = 252) -> float | None:
    series = [v for v in close[-count:] if positive_float(v) is not None]
    if len(series) < 30:
        return None
    returns = [
        cur / prev - 1.0
        for prev, cur in zip(series, series[1:])
        if prev > 0 and cur > 0
    ]
    if len(returns) < 20:
        return None
    avg = sum(returns) / len(returns)
    variance = sum((r - avg) ** 2 for r in returns) / max(len(returns) - 1, 1)
    return math.sqrt(variance)


def fetch_yfinance(symbol: str) -> PriceHistory | None:
    try:
        import yfinance as yf
    except Exception:
        return None
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y", auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 120:
            return None
        try:
            info = dict(getattr(ticker, "info", {}) or {})
        except Exception:
            info = {}
        return PriceHistory(
            symbol=symbol.upper(),
            source="Yahoo Finance via yfinance",
            close=[float(x) for x in hist["Close"].dropna().tolist()],
            high=[float(x) for x in hist["High"].dropna().tolist()],
            low=[float(x) for x in hist["Low"].dropna().tolist()],
            name=str(info.get("longName") or info.get("shortName") or ""),
            quote_type=str(info.get("quoteType") or ""),
        )
    except Exception:
        return None


def fetch_stooq(symbol: str) -> PriceHistory | None:
    for stooq_symbol in (f"{symbol.lower()}.us", symbol.lower()):
        url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                text = response.read().decode("utf-8", errors="replace")
            rows = list(csv.DictReader(io.StringIO(text)))
            rows = [r for r in rows if positive_float(r.get("Close")) is not None]
            if len(rows) < 120:
                continue
            return PriceHistory(
                symbol=symbol.upper(),
                source=f"Stooq daily CSV ({stooq_symbol})",
                close=[float(r["Close"]) for r in rows],
                high=[float(r.get("High") or r["Close"]) for r in rows],
                low=[float(r.get("Low") or r["Close"]) for r in rows],
            )
        except Exception:
            continue
    return None


def fetch_history(symbol: str) -> PriceHistory | None:
    return fetch_yfinance(symbol) or fetch_stooq(symbol)


def weighted_anchor(parts: list[tuple[float | None, float]]) -> float | None:
    usable = [(value, weight) for value, weight in parts if value is not None]
    if not usable:
        return None
    total_weight = sum(weight for _, weight in usable)
    return sum(value * weight for value, weight in usable) / total_weight


def classify_profile(symbol: str, history: PriceHistory, vol: float | None) -> str:
    text = f"{history.name} {history.quote_type}".lower()
    if symbol.upper() in LEVERAGED_ETFS or any(token in text for token in ("2x", "3x", "ultra", "leveraged")):
        return "leveraged_etf"
    if "etf" in text or "fund" in text or history.quote_type.upper() in {"ETF", "MUTUALFUND"}:
        return "broad_etf"
    if vol is not None and vol >= 0.55:
        return "volatile_stock"
    if vol is not None and vol <= 0.25:
        return "steady_stock"
    return "core_stock"


def base_ladder(profile: str) -> dict[str, tuple[float, float, float, str]]:
    ladders = {
        "broad_etf": {
            "aggressive": (0.03, 0.06, 0.25, "small starter on a normal ETF pullback"),
            "standard": (0.06, 0.10, 0.40, "main add zone for a broad ETF"),
            "conservative": (0.10, 0.16, 0.35, "reserve zone for a deeper market dip"),
        },
        "steady_stock": {
            "aggressive": (0.05, 0.09, 0.25, "small starter on a mild pullback"),
            "standard": (0.09, 0.14, 0.40, "main add zone"),
            "conservative": (0.14, 0.22, 0.35, "reserve zone for a deeper pullback"),
        },
        "core_stock": {
            "aggressive": (0.01, 0.04, 0.30, "starter only on a pullback toward the technical anchor; do not chase above it"),
            "standard": (0.04, 0.075, 0.40, "main add zone below the anchor"),
            "conservative": (0.075, 0.30, 0.30, "deep reserve zone; require stabilization first"),
        },
        "volatile_stock": {
            "aggressive": (-0.03, 0.00, 0.30, "starter only near the technical anchor; do not chase far above it"),
            "standard": (0.00, 0.17, 0.40, "main add zone after a real pullback to the anchor area"),
            "conservative": (0.17, 0.37, 0.30, "deep reserve zone; require stabilization first"),
        },
        "leveraged_etf": {
            "aggressive": (-0.02, 0.06, 0.25, "starter only near the technical anchor; path decay makes chasing dangerous"),
            "standard": (0.06, 0.16, 0.40, "main tactical add zone below the anchor"),
            "conservative": (0.16, 0.30, 0.35, "deep reserve zone; use only after stabilization"),
        },
    }
    return ladders[profile]


def market_mood() -> dict[str, Any]:
    benchmark = fetch_history("SPY")
    if benchmark is None:
        return {"label": "neutral", "multiplier": 1.0, "reason": "benchmark data unavailable"}
    close = benchmark.close
    current = close[-1]
    ma200 = mean_tail(close, 200)
    ret20 = current / close[-21] - 1.0 if len(close) >= 21 and close[-21] > 0 else 0.0
    if ma200 and (current < ma200 or ret20 <= -0.06):
        return {"label": "defensive", "multiplier": 1.10, "reason": "market is weak, so buy zones are slightly deeper"}
    if ma200 and current > ma200 and ret20 >= 0.06:
        return {"label": "heated", "multiplier": 0.95, "reason": "market is strong, so buy zones are slightly tighter"}
    return {"label": "neutral", "multiplier": 1.0, "reason": "market backdrop is not extreme"}


def price_zone(current: float, zones: dict[str, dict[str, Any]]) -> str:
    aggressive = zones["aggressive"]
    standard = zones["standard"]
    conservative = zones["conservative"]
    if current > aggressive["price_high"]:
        return "above buy range"
    if aggressive["price_low"] <= current <= aggressive["price_high"]:
        return "starter area"
    if standard["price_low"] <= current <= standard["price_high"]:
        return "main add area"
    if conservative["price_low"] <= current <= conservative["price_high"]:
        return "reserve area"
    if current < conservative["price_low"]:
        return "below plan"
    return "between zones"


def compute_range(symbol: str, price_override: float | None = None, demo: bool = False) -> dict[str, Any]:
    history = demo_history(symbol) if demo else fetch_history(symbol)
    if history is None:
        return {"symbol": symbol.upper(), "status": "unavailable", "reason": "not enough free price history"}
    if len(history.close) < 120:
        return {"symbol": symbol.upper(), "status": "unavailable", "reason": "less than 120 trading days of history"}

    current = price_override or history.close[-1]
    ma50 = mean_tail(history.close, 50)
    ma120 = mean_tail(history.close, 120)
    ma200 = mean_tail(history.close, 200)
    high90 = max_tail(history.high, 90)
    high52 = max_tail(history.high, 252)
    vol = realized_volatility(history.close)
    sigma = daily_sigma(history.close)
    anchor_raw = weighted_anchor([(ma50, 0.30), (ma120, 0.30), (ma200, 0.25), (high90, 0.15)])
    if anchor_raw is None:
        return {"symbol": symbol.upper(), "status": "unavailable", "reason": "could not compute technical anchor"}

    downtrend_capped = bool(ma50 and ma200 and current < ma200 and ma50 < ma200)
    anchor = min(anchor_raw, current) if downtrend_capped else anchor_raw
    mood = {"label": "neutral", "multiplier": 1.0, "reason": "demo mode"} if demo else market_mood()
    profile = classify_profile(symbol, history, vol)
    ladder = base_ladder(profile)

    zones = {}
    for tier, (shallow, deep, size, note) in ladder.items():
        shallow *= mood["multiplier"]
        deep *= mood["multiplier"]
        zones[tier] = {
            "price_low": max(0.01, anchor * (1.0 - deep)),
            "price_high": max(0.01, anchor * (1.0 - shallow)),
            "size": size,
            "note": note,
        }

    return {
        "symbol": symbol.upper(),
        "status": "ok",
        "data_source": history.source,
        "price_source": "user price" if price_override else "latest free-data close",
        "current_price": current,
        "profile": profile,
        "realized_volatility": vol,
        "daily_sigma": sigma,
        "technical_anchor": anchor,
        "raw_anchor": anchor_raw,
        "downtrend_capped": downtrend_capped,
        "high90": high90,
        "high52": high52,
        "market_mood": mood,
        "zones": zones,
        "current_zone": price_zone(current, zones),
        "plan": build_plan(current, high90, high52, zones, downtrend_capped, profile, sigma),
    }


def build_plan(
    current: float,
    high90: float | None,
    high52: float | None,
    zones: dict[str, dict[str, Any]],
    downtrend_capped: bool,
    profile: str,
    sigma: float | None,
) -> dict[str, Any]:
    resistance_candidates = [v for v in (high90, high52) if v and v > current]
    if profile == "leveraged_etf" and resistance_candidates:
        first_trim = min(min(resistance_candidates), current * 1.12)
        second_trim = max(first_trim * 1.06, min(max(resistance_candidates), current * 1.22))
    elif resistance_candidates:
        first_trim = min(resistance_candidates)
        second_trim = max(resistance_candidates)
    else:
        first_trim = current * 1.08
        second_trim = current * 1.15
    if second_trim <= first_trim:
        second_trim = first_trim * 1.06

    def trim_action(label: str, zone: float, base_action: str) -> str:
        if zone / current >= 1.60:
            return (
                f"{base_action}; this is a far historical resistance reference, "
                "not a near-term target"
            )
        if zone / current >= 1.30:
            return f"{base_action}; treat this as an upper resistance reference"
        return base_action

    cautions = []
    if downtrend_capped:
        cautions.append("Downtrend cap is active: treat the first zone as a test, not a strong buy signal.")
    if profile == "leveraged_etf":
        cautions.append("Leveraged ETF: suitable only for short tactical holding periods; do not average down blindly.")
    if profile == "volatile_stock":
        cautions.append("Volatile stock: ranges are wide and can be invalidated by earnings, sector news, liquidity, or company-specific shocks.")
    cautions.append("If bad company news caused the drop, pause and re-check the thesis before buying.")

    entries = []
    for label, key in (("Step 1 starter", "aggressive"), ("Step 2 main add", "standard"), ("Step 3 reserve", "conservative")):
        zone = zones[key]
        if current > zone["price_high"]:
            trigger = "wait for price to pull back into this zone"
        elif (
            zone["price_low"] <= current <= zone["price_high"]
            if key == "aggressive"
            else zone["price_low"] <= current < zone["price_high"]
        ):
            trigger = "price is already in this zone; use only the planned step size"
        elif current < zone["price_low"]:
            trigger = "price is already below this zone; wait for stabilization or reclaim"
        else:
            trigger = "watch this zone"
        entries.append({**zone, "label": label, "trigger": trigger})

    return {
        "entries": entries,
        "take_profit": [
            {
                "label": "TP1",
                "zone": first_trim,
                "trim": 0.40,
                "action": trim_action("TP1", first_trim, "trim part of the tactical position"),
            },
            {
                "label": "TP2",
                "zone": second_trim,
                "trim": 0.60,
                "action": trim_action(
                    "TP2",
                    second_trim,
                    "take most remaining tactical profit; keep a runner only if trend is strong",
                ),
            },
        ],
        "invalidation": {
            "level": (
                zones["standard"]["price_high"] * 0.97
                if profile == "leveraged_etf"
                else zones["conservative"]["price_low"] * 0.97
            ),
            "action": "exit any remaining tactical position, cancel unfilled add orders, and reassess before a new plan",
        },
        "stress_scenarios": build_stress_scenarios(current, sigma, horizon_days=14 if profile == "leveraged_etf" else 20),
        "cautions": cautions,
    }


def build_stress_scenarios(current: float, sigma: float | None, horizon_days: int = 20) -> list[dict[str, Any]]:
    if sigma is None:
        return []
    one_sd_move = current * sigma * math.sqrt(horizon_days)
    return [
        {
            "label": "2SD stress scenario",
            "horizon_days": horizon_days,
            "downside": max(0.01, current - one_sd_move * 2),
            "upside": current + one_sd_move * 2,
            "downside_action": "observe first; use reserve cash only after price stabilizes or reclaims a key level",
            "upside_action": "trim tactical risk and avoid chasing",
        },
        {
            "label": "3SD extreme scenario",
            "horizon_days": horizon_days,
            "downside": max(0.01, current - one_sd_move * 3),
            "upside": current + one_sd_move * 3,
            "downside_action": "pause and re-check news, liquidity, and trend before considering any tiny rescue buy",
            "upside_action": "take most tactical profit; keep only a small runner if trend remains strong",
        },
    ]


def money(value: Any) -> str:
    number = positive_float(value)
    return "-" if number is None else f"${number:,.2f}"


def pct(value: Any) -> str:
    number = positive_float(value)
    return "-" if number is None else f"{number * 100:.1f}%"


def render_buy_range_only(result: dict[str, Any]) -> str:
    symbol = result["symbol"]
    if result.get("status") != "ok":
        return f"## {symbol} Buy Range\n\nBuy range unavailable: {result.get('reason', 'missing data')}\n"

    lines = [
        f"## {symbol} Buy Range",
        "",
        f"- Current price: {money(result['current_price'])} ({result['price_source']})",
        f"- Data source: {result['data_source']}",
        f"- Current zone: **{result['current_zone']}**",
        f"- Profile: {result['profile'].replace('_', ' ')}; recent volatility: {pct(result.get('realized_volatility'))}",
    ]
    if result.get("downtrend_capped"):
        lines.append("- Caution: downtrend cap is active, so the starter zone is only a small test area.")

    lines += [
        "",
        "| Zone | Buy range | Planned size | Plain-English meaning |",
        "| --- | ---: | ---: | --- |",
    ]
    for key, label in (("aggressive", "Starter"), ("standard", "Main add"), ("conservative", "Reserve")):
        zone = result["zones"][key]
        lines.append(
            f"| {label} | {money(zone['price_low'])} - {money(zone['price_high'])} | "
            f"{zone['size'] * 100:.0f}% | {zone['note']} |"
        )

    current = result["current_price"]
    zones = result["zones"]
    lines += ["", "### Quick Read"]
    if current > zones["aggressive"]["price_high"]:
        lines.append(f"- Current price is above the starter zone; do not chase. Wait for a pullback below {money(zones['aggressive']['price_high'])}.")
    elif zones["aggressive"]["price_low"] <= current <= zones["aggressive"]["price_high"]:
        lines.append("- Current price is inside the starter zone. If acting, keep it small.")
    elif zones["standard"]["price_low"] <= current < zones["aggressive"]["price_low"]:
        lines.append("- Current price is around the main add zone. Check news and trend before adding.")
    elif zones["conservative"]["price_low"] <= current < zones["standard"]["price_low"]:
        lines.append("- Current price is around the reserve zone. Use only after stabilization.")
    else:
        lines.append("- Current price is outside the normal range structure. Re-check news and trend before acting.")
    lines.append("- This is a technical buy-range reference, not a full operation plan and not a prediction.")
    return "\n".join(lines) + "\n"


def render_plan(result: dict[str, Any]) -> str:
    symbol = result["symbol"]
    if result.get("status") != "ok":
        return f"## {symbol}\n\nBuy range unavailable: {result.get('reason', 'missing data')}\n"

    lines = [
        f"## {symbol}",
        "",
        f"- Current price: {money(result['current_price'])} ({result['price_source']})",
        f"- Data source: {result['data_source']}",
        f"- Technical anchor: {money(result['technical_anchor'])}; current zone: **{result['current_zone']}**",
        f"- Recent volatility: {pct(result.get('realized_volatility'))}; profile: {result['profile'].replace('_', ' ')}",
        "",
        "| Zone | Buy range | Planned size | Plain-English use |",
        "| --- | ---: | ---: | --- |",
    ]
    for key, label in (("aggressive", "Starter"), ("standard", "Main add"), ("conservative", "Reserve")):
        zone = result["zones"][key]
        lines.append(
            f"| {label} | {money(zone['price_low'])} - {money(zone['price_high'])} | "
            f"{zone['size'] * 100:.0f}% | {zone['note']} |"
        )

    lines += ["", "### Beginner Operation Plan"]
    for entry in result["plan"]["entries"]:
        lines.append(
            f"- {entry['label']}: {money(entry['price_low'])} - {money(entry['price_high'])}; "
            f"use {entry['size'] * 100:.0f}% of the planned position; {entry['trigger']}."
        )
    lines.append("")
    for tp in result["plan"]["take_profit"]:
        lines.append(f"- {tp['label']}: around {money(tp['zone'])}; trim {tp['trim'] * 100:.0f}% of the planned position; {tp['action']}.")

    lines += [
        "",
        "### Stress Scenarios",
        "These are risk references, not predictions and not extra buy orders.",
        "",
        "| Scenario | Downside reference | Downside action | Upside reference | Upside action |",
        "| --- | ---: | --- | ---: | --- |",
    ]
    for scenario in result["plan"]["stress_scenarios"]:
        lines.append(
            f"| {scenario['label']} ({scenario['horizon_days']} trading days) | "
            f"{money(scenario['downside'])} | {scenario['downside_action']} | "
            f"{money(scenario['upside'])} | {scenario['upside_action']} |"
        )
    inv = result["plan"]["invalidation"]
    lines += ["", f"- Invalidation: around {money(inv['level'])}; {inv['action']}."]
    for caution in result["plan"]["cautions"]:
        lines.append(f"- Reminder: {caution}")
    return "\n".join(lines) + "\n"


def parse_price_overrides(items: list[str]) -> dict[str, float]:
    out = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"invalid --price value {item!r}; expected TICKER=PRICE")
        sym, raw = item.split("=", 1)
        sym = sym.strip().upper()
        value = positive_float(raw)
        if not sym:
            raise ValueError(f"invalid --price value {item!r}; ticker is empty")
        if value is None:
            raise ValueError(f"invalid --price value {item!r}; price must be a positive number")
        out[sym] = value
    return out


def demo_history(symbol: str) -> PriceHistory:
    close = [
        100, 102, 101, 103, 105, 104, 106, 108, 107, 110, 112, 111, 113, 115, 114,
        116, 118, 117, 119, 121, 120, 122, 124, 123, 125, 127, 126, 128, 130, 129,
    ]
    close = (close * 9)[-252:]
    return PriceHistory(
        symbol=symbol.upper(),
        source="demo data",
        close=close,
        high=[x * 1.015 for x in close],
        low=[x * 0.985 for x in close],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Portable technical buy range, with optional beginner operation plan")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols, e.g. NVDA TQQQ")
    parser.add_argument("--price", action="append", default=[], help="Optional current price override, e.g. NVDA=125.50")
    parser.add_argument("--range-only", action="store_true", help="Print only the buy range. This is the default.")
    parser.add_argument("--plan", action="store_true", help="Print the expanded operation plan. Use only when explicitly requested.")
    parser.add_argument("--demo", action="store_true", help="Run with built-in demo data")
    args = parser.parse_args()

    tickers = [t.upper() for t in args.tickers]
    if args.demo and not tickers:
        tickers = ["DEMO"]
    if not tickers:
        print("Provide at least one ticker, for example: python portable_buy_range_plan.py NVDA")
        return 2

    try:
        overrides = parse_price_overrides(args.price)
    except ValueError as exc:
        parser.error(str(exc))
    if args.plan:
        print("# Technical Buy Range and Beginner Operation Plan\n")
        print("This is a price-structure plan, not a prediction. Use it to plan entries, adds, trims, and invalidation before acting.\n")
    else:
        print("# Technical Buy Range\n")
        print("This is a price-structure reference, not a prediction or a standalone buy recommendation.\n")
    for ticker in tickers:
        result = compute_range(ticker, price_override=overrides.get(ticker), demo=args.demo)
        print(render_plan(result) if args.plan else render_buy_range_only(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
