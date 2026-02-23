"""
Page 4 — AI Recommendations
AI-powered Top 5 Buy / Sell analysis backed by price trends,
volume data, and live GW2 market research via Google Search.
"""

import io
from datetime import date
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
from db import fetch_opportunities, fetch_latest_volumes, fetch_item_trends, fetch_daily_volumes
from currency import format_gsc
from settings import get


# ── Data helpers ─────────────────────────────────────────────────────

def _load_data() -> pd.DataFrame:
    """Fetch opportunities + latest volumes + 7d trends + daily volumes, merged."""
    opp = fetch_opportunities()
    vol = fetch_latest_volumes()
    trends = fetch_item_trends()

    df = opp.merge(vol, on="item_id", how="left")
    df = df.merge(trends, on="item_id", how="left")

    # Merge daily transaction volumes (may not exist yet)
    try:
        dvol = fetch_daily_volumes()
        df = df.merge(dvol, on="item_id", how="left")
        df["avg_daily_sold"] = df["avg_daily_sold"].fillna(0).astype(int)
        df["avg_daily_bought"] = df["avg_daily_bought"].fillna(0).astype(int)
    except Exception:
        df["avg_daily_sold"] = 0
        df["avg_daily_bought"] = 0

    df["sell_quantity"] = df["sell_quantity"].fillna(0).astype(int)
    df["buy_quantity"] = df["buy_quantity"].fillna(0).astype(int)

    # Cast trend columns to float (PostgreSQL returns Decimal objects)
    trend_cols = [
        "avg_sell_7d", "avg_sell_prior_7d",
        "avg_buy_7d", "avg_buy_prior_7d",
        "avg_sell_qty_7d", "avg_sell_qty_prior_7d",
        "avg_buy_qty_7d", "avg_buy_qty_prior_7d",
    ]
    for col in trend_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Compute trend percentages (7d vs prior 7d)
    for prefix in ["sell", "buy"]:
        cur = f"avg_{prefix}_7d"
        prev = f"avg_{prefix}_prior_7d"
        df[f"{prefix}_price_trend_pct"] = (
            ((df[cur] - df[prev]) / df[prev].replace(0, pd.NA)) * 100
        ).round(1)

    for prefix in ["sell_qty", "buy_qty"]:
        cur = f"avg_{prefix}_7d"
        prev = f"avg_{prefix}_prior_7d"
        df[f"{prefix}_trend_pct"] = (
            ((df[cur] - df[prev]) / df[prev].replace(0, pd.NA)) * 100
        ).round(1)

    return df


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with zero / null price rows removed."""
    df = df.copy()
    return df[
        (df["latest_sell_copper"] > 0)
        & (df["latest_buy_copper"] > 0)
        & (df["avg_sell_copper_30d"] > 0)
        & (df["avg_buy_copper_30d"] > 0)
    ]


# ── AI analysis ──────────────────────────────────────────────────────

_ANALYSIS_SYSTEM = """\
You are an expert Guild Wars 2 Trading Post analyst.

Today's date is {today}.

You have access to Google Search. Use it to look up current GW2 events,
patches, or balance changes that could affect item demand.

You will receive a market snapshot CSV. Key columns explained:
- latest_buy / latest_sell: current TP prices
- avg_buy_30d / avg_sell_30d: 30-day average prices
- buy_discount_pct: how far below 30d avg the current buy price is (higher = better deal)
- flip_margin_pct: profit margin after 15% tax = ((sell * 0.85) - buy) / buy * 100
- sell_price_trend_7d / buy_price_trend_7d: price momentum (+ = rising)
- sell_supply_trend_7d: listing volume change (+ = more supply = bearish)
- buy_demand_trend_7d: buy order change (+ = more demand = bullish)
- avg_daily_sold / avg_daily_bought: actual items traded per day (higher = more liquid)

STRICT RULES — you MUST follow these:
1. The TP takes 15% tax. A flip is ONLY profitable if flip_margin_pct > 0.
2. NEVER recommend items with buy_discount_pct < 3% — those are noise, not real discounts.
3. NEVER recommend items with avg_daily_sold < 5 — illiquid items are too risky.
4. BUY list must be sorted by flip_margin_pct descending (most profitable first).
5. SELL list must be sorted by sell premium above 30d avg descending (most overpriced first).
6. For SELL, only include items where qty > 0 (player actually owns them).

OUTPUT FORMAT — produce exactly two sections:

## Top 5 Buy Recommendations
| # | Item | Buy Price | Flip Margin | Why |
|---|------|-----------|-------------|-----|
Rank 1 = highest flip_margin_pct. The "Why" column must be 1-2 sentences max
citing: the discount %, 7d price trend, and daily volume.

## Top 5 Sell Recommendations
| # | Item | Sell Price | Qty | Why |
|---|------|------------|-----|-----|
Rank 1 = highest premium above avg. The "Why" column must be 1-2 sentences max
citing: the premium %, whether price is peaking or still rising, and daily volume.

After both tables, add a "Market Context" paragraph (3 sentences max) with
any relevant GW2 news from your search.

If fewer than 5 items meet the criteria, list only those that do.
Do NOT invent data or recommend items that violate the rules above.
"""


def _build_ai_snapshot(df: pd.DataFrame) -> str:
    """Build an enriched CSV with pre-computed profitability, volume, and trends."""
    df = _clean(df)

    df["buy_discount_pct"] = (
        ((df["avg_buy_copper_30d"] - df["latest_buy_copper"])
         / df["avg_buy_copper_30d"].replace(0, pd.NA)) * 100
    ).round(1)

    df["flip_margin_pct"] = (
        ((df["latest_sell_copper"] * 0.85 - df["latest_buy_copper"])
         / df["latest_buy_copper"].replace(0, pd.NA)) * 100
    ).round(1)

    df["sell_premium_pct"] = (
        ((df["latest_sell_copper"] - df["avg_sell_copper_30d"])
         / df["avg_sell_copper_30d"].replace(0, pd.NA)) * 100
    ).round(1)

    df = df[df["sell_quantity"] >= 10].copy()
    top = df.nlargest(100, "flip_margin_pct").copy()

    for col in ["latest_sell_copper", "latest_buy_copper",
                "avg_sell_copper_30d", "avg_buy_copper_30d"]:
        top[col] = top[col].apply(
            lambda v: format_gsc(int(v)) if pd.notna(v) else "0c"
        )

    out = pd.DataFrame({
        "item_name": top["item_name"],
        "qty": top["current_count"],
        "latest_sell": top["latest_sell_copper"],
        "latest_buy": top["latest_buy_copper"],
        "avg_sell_30d": top["avg_sell_copper_30d"],
        "avg_buy_30d": top["avg_buy_copper_30d"],
        "buy_discount_pct": top["buy_discount_pct"].fillna(0),
        "flip_margin_pct": top["flip_margin_pct"].fillna(0),
        "sell_premium_pct": top["sell_premium_pct"].fillna(0),
        "sell_listings": top["sell_quantity"],
        "buy_orders": top["buy_quantity"],
        "avg_daily_sold": top["avg_daily_sold"],
        "avg_daily_bought": top["avg_daily_bought"],
        "sell_price_trend_7d": top["sell_price_trend_pct"].fillna(0),
        "buy_price_trend_7d": top["buy_price_trend_pct"].fillna(0),
        "sell_supply_trend_7d": top["sell_qty_trend_pct"].fillna(0),
        "buy_demand_trend_7d": top["buy_qty_trend_pct"].fillna(0),
    })

    buf = io.StringIO()
    out.to_csv(buf, index=False)
    return buf.getvalue()


def _extract_text(response) -> str:
    """Extract text content from a Gemini response, handling all edge cases."""
    if response is None:
        return ""
    try:
        if response.text:
            return response.text
    except (ValueError, AttributeError):
        pass

    text_parts = []
    for candidate in (response.candidates or []):
        content = getattr(candidate, "content", None)
        if content is None:
            continue
        for part in (getattr(content, "parts", None) or []):
            part_text = getattr(part, "text", None)
            if part_text and not getattr(part, "thought", False):
                text_parts.append(part_text)

    return "\n".join(text_parts).strip()


def _call_gemini(api_key: str, snapshot_csv: str) -> str:
    """Send enriched data to Gemini with Google Search grounding."""
    user_content = (
        f"Here is my full market snapshot with trend data:\n\n"
        f"```csv\n{snapshot_csv}```\n\n"
        f"First, search for current Guild Wars 2 news, events, updates, and "
        f"Trading Post market trends. Then use everything — the data AND your "
        f"search findings — to produce your Top 5 Buy and Top 5 Sell tables."
    )

    client = genai.Client(api_key=api_key)
    system_prompt = _ANALYSIS_SYSTEM.format(today=date.today().isoformat())

    # Primary: with Google Search + thinking
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
            max_output_tokens=8192,
            thinking_config=types.ThinkingConfig(thinking_budget=2048),
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    text = _extract_text(response)
    if text:
        return text

    # Fallback: without Google Search or thinking
    response2 = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
            max_output_tokens=8192,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    return _extract_text(response2) or "*No analysis was generated. Please try again.*"


# ── Page ─────────────────────────────────────────────────────────────

def page_ai_recommendations() -> None:
    st.header("AI Recommendations")

    api_key = get("gemini_api_key")
    if not api_key:
        st.warning("No Gemini API key configured. Go to **Settings** to add one.")
        return

    st.caption(
        "Analyzes your market data combined with current GW2 news and events "
        "to produce Top 5 Buy and Sell picks with reasoning."
    )

    if st.button("🤖 Generate AI Top 5 Picks", type="primary"):
        with st.spinner("Loading market data…"):
            try:
                df = _load_data()
            except Exception as exc:
                st.error(f"Database error: {exc}")
                return

            if df.empty:
                st.warning("No opportunity data available.")
                return

        with st.spinner("Researching GW2 market trends and analyzing data…"):
            try:
                csv_str = _build_ai_snapshot(df)
                analysis = _call_gemini(api_key, csv_str)
                st.session_state["rec_ai_analysis"] = analysis
            except Exception as exc:
                st.error(f"Gemini API error: {exc}")

    if "rec_ai_analysis" in st.session_state:
        st.divider()
        st.markdown(st.session_state["rec_ai_analysis"])