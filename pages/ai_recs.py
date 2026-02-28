"""
Page 4 — AI Recommendations
AI-powered swing trading analysis: buy items at price dips,
sell when they recover above average. Uses statistical signals
from 30-day price history + daily transaction volume.
"""

import io
import re
from datetime import date
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
from db import fetch_trading_signals, fetch_daily_volumes, fetch_item_list
from currency import format_gsc
from settings import get
from pages.charts import render_price_chart


# ── Data helpers ─────────────────────────────────────────────────────

def _load_data() -> pd.DataFrame:
    """Fetch trading signals + item metadata + daily volumes, merged."""
    signals = fetch_trading_signals()
    items = fetch_item_list()

    df = signals.merge(
        items[["item_id", "item_name", "current_count", "rarity"]],
        on="item_id", how="left",
    )

    # Merge daily transaction volumes (may not exist yet)
    try:
        dvol = fetch_daily_volumes()
        df = df.merge(dvol, on="item_id", how="left")
        df["avg_daily_sold"] = df["avg_daily_sold"].fillna(0).astype(int)
        df["avg_daily_bought"] = df["avg_daily_bought"].fillna(0).astype(int)
    except Exception:
        df["avg_daily_sold"] = 0
        df["avg_daily_bought"] = 0

    # Cast all numeric columns (PostgreSQL returns Decimal)
    numeric_cols = [
        "latest_sell", "latest_buy", "avg_sell_30d", "avg_buy_30d",
        "min_sell_30d", "max_sell_30d", "min_buy_30d", "max_buy_30d",
        "hist_min_sell", "hist_max_sell", "hist_min_buy", "hist_max_buy",
        "buy_z_score", "sell_z_score", "buy_range_pct", "sell_range_pct",
        "buy_trend_3d_vs_7d", "sell_trend_3d_vs_7d",
        "expected_profit_per_unit", "buy_volatility_pct", "sell_volatility_pct",
        "current_count",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


# ── AI analysis ──────────────────────────────────────────────────────

_ANALYSIS_SYSTEM = """\
You are an expert Guild Wars 2 Trading Post swing trading analyst.

Today's date is {today}.

You have access to Google Search. Use it to look up current GW2 events,
patches, or balance changes that could affect item demand.

STRATEGY: The player buys items when prices dip below normal, holds them,
then sells when prices recover above average. This is NOT instant flipping.

You will receive a market snapshot CSV. Key columns explained:
- latest_buy / latest_sell: current TP prices
- avg_buy_30d / avg_sell_30d: 30-day average prices
- buy_z_score: how many standard deviations BELOW average the buy price is
  (more negative = deeper dip = stronger buy signal)
- sell_z_score: how many std devs ABOVE average the sell price is
  (more positive = higher above normal = stronger sell signal)
- buy_range_pct: where current buy sits in its 30d range (0% = at floor, 100% = ceiling)
- sell_range_pct: where current sell sits in its 30d range
- buy_trend_3d_vs_7d: short-term momentum (positive = price recovering from dip)
- sell_trend_3d_vs_7d: short-term momentum (negative = price peaking/falling)
- expected_profit_per_unit: profit if price returns to 30d avg sell, after 15% tax
- buy_volatility_pct / sell_volatility_pct: price swing range as % of average
  (higher = more profitable swings)
- avg_daily_sold / avg_daily_bought: actual items traded per day (liquidity)
- total_sell_profit: total gold profit if all owned qty sold at current price after tax

STRICT RULES:
1. The TP takes 15% tax on all sales.
2. BUY candidates: buy_z_score must be <= -1.0 (at least 1 std dev below average).
3. BUY candidates: buy_trend_3d_vs_7d should be >= 0 (price recovering, not still falling).
4. BUY candidates: avg_daily_sold must be >= 10 (liquid enough to resell later).
5. BUY candidates: expected_profit_per_unit must be > 0.
6. BUY list sorted by expected_profit_per_unit descending.
7. SELL candidates: qty must be > 0 (player owns the item).
8. SELL candidates: sell_z_score must be >= 0.5 (meaningfully above average).
9. SELL candidates: total_sell_profit must be >= 1g (10000 copper).
10. SELL list sorted by total_sell_profit descending.

OUTPUT FORMAT — exactly two sections:

## Top 5 Buy Opportunities
| # | Item | Buy Price | Avg Price | Expected Profit | Why |
|---|------|-----------|-----------|-----------------|-----|
Rank 1 = highest expected_profit_per_unit. "Why" = 1-2 sentences citing:
z-score, range position, trend direction, and daily volume.

## Top 5 Sell Opportunities
| # | Item | Sell Price | Qty | Total Profit | Why |
|---|------|------------|-----|-------------|-----|
Rank 1 = highest total_sell_profit. "Why" = 1-2 sentences citing:
z-score, range position, trend direction, and daily volume.

After both tables, add a "Market Context" paragraph (3 sentences max) with
any relevant GW2 news from your search.

If fewer than 5 items meet the criteria, list only those that do and
briefly explain why pickings are slim (e.g. "market is flat").
Do NOT recommend items that violate the rules above.
"""


def _build_ai_snapshot(df: pd.DataFrame) -> str:
    """Build CSV with swing trading signals for the AI."""
    # Compute total sell profit for owned items
    df["total_sell_profit"] = (
        (df["latest_sell"] * 0.85 - df["avg_buy_30d"]) * df["current_count"]
    ).clip(lower=0).astype(int)

    # Format prices to g/s/c
    price_cols = {
        "latest_sell": "latest_sell",
        "latest_buy": "latest_buy",
        "avg_sell_30d": "avg_sell_30d",
        "avg_buy_30d": "avg_buy_30d",
        "expected_profit_per_unit": "expected_profit_per_unit",
        "total_sell_profit": "total_sell_profit",
    }
    formatted = df.copy()
    for col in price_cols:
        formatted[col] = formatted[col].apply(
            lambda v: format_gsc(int(v)) if pd.notna(v) and v > 0 else "0c"
        )

    out = pd.DataFrame({
        "item_name": formatted["item_name"],
        "qty": formatted["current_count"].astype(int),
        "latest_sell": formatted["latest_sell"],
        "latest_buy": formatted["latest_buy"],
        "avg_sell_30d": formatted["avg_sell_30d"],
        "avg_buy_30d": formatted["avg_buy_30d"],
        "buy_z_score": df["buy_z_score"],
        "sell_z_score": df["sell_z_score"],
        "buy_range_pct": df["buy_range_pct"],
        "sell_range_pct": df["sell_range_pct"],
        "buy_trend_3d_vs_7d": df["buy_trend_3d_vs_7d"],
        "sell_trend_3d_vs_7d": df["sell_trend_3d_vs_7d"],
        "expected_profit_per_unit": formatted["expected_profit_per_unit"],
        "buy_volatility_pct": df["buy_volatility_pct"],
        "sell_volatility_pct": df["sell_volatility_pct"],
        "avg_daily_sold": df["avg_daily_sold"],
        "avg_daily_bought": df["avg_daily_bought"],
        "total_sell_profit": formatted["total_sell_profit"],
    })

    # Drop items with no name (unmatched joins)
    out = out.dropna(subset=["item_name"])

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
    """Send trading signals to Gemini with Google Search grounding."""
    user_content = (
        f"Here is my market snapshot with swing trading signals:\n\n"
        f"```csv\n{snapshot_csv}```\n\n"
        f"First, search for current Guild Wars 2 news, events, updates, and "
        f"Trading Post market trends. Then analyze the data to find the best "
        f"swing trade opportunities — items to buy at dips and items to sell "
        f"at peaks."
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


def _parse_item_names(analysis: str) -> list[str]:
    """Extract item names from markdown table rows in the AI response."""
    # Match table rows: | number | item name | ...
    pattern = r'\|\s*\d+\s*\|\s*([^|]+?)\s*\|'
    matches = re.findall(pattern, analysis)
    # Filter out header-like matches
    names = [m.strip() for m in matches if m.strip() and m.strip() != "Item"]
    return names


# ── Page ─────────────────────────────────────────────────────────────

def page_ai_recommendations() -> None:
    st.header("AI Recommendations")

    api_key = get("gemini_api_key")
    if not api_key:
        st.warning("No Gemini API key configured. Go to **Settings** to add one.")
        return

    st.caption(
        "Swing trading analysis: finds items at price dips to buy, "
        "and items you own at price peaks to sell. Uses 30-day statistical "
        "signals, daily volume, and current GW2 news."
    )

    if st.button("🤖 Generate Trading Recommendations", type="primary"):
        with st.spinner("Loading trading signals…"):
            try:
                df = _load_data()
            except Exception as exc:
                import traceback
                traceback.print_exc()
                st.error(f"Database error: {exc}")
                st.code(traceback.format_exc(), language="text")
                return

            if df.empty:
                st.warning("No trading signal data available.")
                return

            # Build item name → id mapping for chart lookups
            item_map = dict(zip(df["item_name"], df["item_id"].astype(int)))
            st.session_state["rec_item_map"] = item_map

        with st.spinner("Analyzing market and researching GW2 news…"):
            try:
                csv_str = _build_ai_snapshot(df)
                analysis = _call_gemini(api_key, csv_str)
                st.session_state["rec_ai_analysis"] = analysis
                st.session_state["rec_ai_items"] = _parse_item_names(analysis)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                st.error(f"Gemini API error: {exc}")
                st.code(traceback.format_exc(), language="text")

    if "rec_ai_analysis" in st.session_state:
        st.divider()
        st.markdown(st.session_state["rec_ai_analysis"])

        # Chart viewer for recommended items
        item_map = st.session_state.get("rec_item_map", {})
        ai_items = st.session_state.get("rec_ai_items", [])

        # Match parsed names to known items
        chart_options = {
            name: item_map[name]
            for name in ai_items
            if name in item_map
        }

        if chart_options:
            st.divider()
            st.subheader("📊 Price History")
            selected = st.selectbox(
                "Select a recommended item to view its chart",
                options=list(chart_options.keys()),
                index=0,
            )
            if selected:
                render_price_chart(chart_options[selected], selected)