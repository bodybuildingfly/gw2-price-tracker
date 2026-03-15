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


def _gw2tp_url(item_id: int, item_name: str) -> str:
    """Build a GW2TP item page URL from id and name."""
    slug = re.sub(r'[^a-z0-9]+', '-', item_name.lower()).strip('-')
    return f"https://www.gw2tp.com/item/{item_id}-{slug}"


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
- item_name / gw2tp_url: item name and its GW2TP price history page
- latest_buy / latest_sell: current TP prices
- hist_max_buy: highest buy price in past 30 days (excl. last 12h)
- hist_max_sell: highest sell price in past 30 days (excl. last 12h)
- buy_discount_from_high_pct: how far below the 30d high buy price the current buy is
- buy_profit_per_unit: profit per item if you buy now and sell at the 30d high sell, after 15% tax
- avg_daily_sold: items sold per day (buy-side liquidity - can you resell it?)
- avg_daily_bought: items bought per day (sell-side demand - will your listing fill?)
- buy_z_score: std devs from average (more negative = deeper dip)
- sell_z_score: std devs above average (more positive = higher peak)
- buy_trend_3d_vs_7d: short-term momentum (positive = recovering)
- sell_trend_3d_vs_7d: short-term momentum (negative = falling from peak)
- buy_volatility_pct: price swing range as pct of average (higher = bigger swings)
- total_sell_profit: total gold from selling full stack at current price after 15% tax

STRICT RULES:
1. The TP takes 15% tax on all sales.
2. BUY candidates: buy_profit_per_unit must be > 0 (profitable if price reverts to 30d high).
3. BUY candidates: buy_discount_from_high_pct must be >= 5 (meaningful dip from 30d high).
4. BUY candidates: avg_daily_sold must be >= 10 (liquid enough to resell later).
5. BUY candidates: buy_trend_3d_vs_7d should be >= 0 (recovering, not still falling).
6. BUY list sorted by buy_profit_per_unit descending.
7. SELL candidates: qty must be > 0 (player owns the item).
8. SELL candidates: latest_sell must be ABOVE hist_max_sell (at a new 30-day high).
9. SELL candidates: total_sell_profit must be >= 1g (10000 copper).
10. SELL candidates: avg_daily_bought must be >= 5 (enough demand to fill your listing).
11. SELL list sorted by total_sell_profit descending.

OUTPUT FORMAT -- exactly two sections:

## Top 5 Buy Opportunities
| # | Item | Buy Price | 30d High | Profit/Item | Sold/Day | Why |
|---|------|-----------|----------|-------------|----------|-----|
Rank 1 = highest buy_profit_per_unit. The Item column MUST be a markdown
link using the gw2tp_url: [Item Name](gw2tp_url). "Why" = 1-2 sentences
citing: discount from 30d high, trend direction, and volume.

## Top 5 Sell Opportunities
| # | Item | Sell Price | 30d High | Qty | Total Profit | Bought/Day | Why |
|---|------|------------|----------|-----|-------------|------------|-----|
Rank 1 = highest total_sell_profit. The Item column MUST be a markdown
link using the gw2tp_url: [Item Name](gw2tp_url). "Why" = 1-2 sentences
citing: how far above 30d high, trend direction, and volume.

After both tables, add a "Market Context" paragraph (3 sentences max) with
any relevant GW2 news from your search.

If fewer than 5 items meet the criteria, list only those that do and
briefly explain why pickings are slim (e.g. "market is flat").
Do NOT recommend items that violate the rules above.
"""


def _build_ai_snapshot(df: pd.DataFrame) -> str:
    """Build CSV with swing trading signals for the AI."""
    # Buy profit: what you'd make if you buy now and sell at the 30d high (after 15% tax)
    df["buy_profit_per_unit"] = (
        (df["hist_max_sell"] * 0.85 - df["latest_buy"])
    ).clip(lower=0).astype(int)

    # Buy discount: how far below the 30d high buy price
    df["buy_discount_from_high_pct"] = (
        (df["hist_max_buy"] - df["latest_buy"]) / df["hist_max_buy"].replace(0, pd.NA) * 100
    ).round(1).fillna(0)

    # Total gold from selling full stack at current sell price after 15% tax
    df["total_sell_profit"] = (
        df["latest_sell"] * 0.85 * df["current_count"]
    ).astype(int)

    # Pre-filter: remove owned items where sell price is not above 30d high
    # (keeps non-owned items for buy candidates)
    is_owned = df["current_count"] > 0
    is_above_high = df["latest_sell"] > df["hist_max_sell"]
    df = df[~is_owned | is_above_high].copy()

    # Format prices to g/s/c
    price_cols = [
        "latest_sell", "latest_buy", "hist_max_sell", "hist_max_buy",
        "buy_profit_per_unit", "total_sell_profit",
    ]
    formatted = df.copy()
    for col in price_cols:
        formatted[col] = formatted[col].apply(
            lambda v: format_gsc(int(v)) if pd.notna(v) and v > 0 else "0c"
        )

    out = pd.DataFrame({
        "item_name": formatted["item_name"],
        "gw2tp_url": df.apply(
            lambda r: _gw2tp_url(int(r["item_id"]), r["item_name"]), axis=1
        ),
        "qty": formatted["current_count"].astype(int),
        "latest_sell": formatted["latest_sell"],
        "latest_buy": formatted["latest_buy"],
        "hist_max_sell": formatted["hist_max_sell"],
        "hist_max_buy": formatted["hist_max_buy"],
        "buy_discount_from_high_pct": df["buy_discount_from_high_pct"],
        "buy_profit_per_unit": formatted["buy_profit_per_unit"],
        "buy_z_score": df["buy_z_score"],
        "sell_z_score": df["sell_z_score"],
        "buy_trend_3d_vs_7d": df["buy_trend_3d_vs_7d"],
        "sell_trend_3d_vs_7d": df["sell_trend_3d_vs_7d"],
        "buy_volatility_pct": df["buy_volatility_pct"],
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
    """Extract item names from markdown table rows in the AI response.
    Handles both plain text and markdown links like [Name](url)."""
    # Match table rows: | number | item cell | ...
    pattern = r'\|\s*\d+\s*\|\s*([^|]+?)\s*\|'
    matches = re.findall(pattern, analysis)
    names = []
    for m in matches:
        m = m.strip()
        if not m or m == "Item":
            continue
        # Extract name from markdown link [Name](url)
        link_match = re.match(r'\[([^\]]+)\]', m)
        if link_match:
            names.append(link_match.group(1).strip())
        else:
            names.append(m)
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