"""
Page 4 -- AI Recommendations
Enhanced one-shot sell analysis: when to liquidate owned items
via direct TP sale, Mystic Forge promotion, or crafting refinement.
"""

import io
import re
from datetime import date, datetime
from typing import Optional
import streamlit as st
import pandas as pd
import pytz
from google import genai
from google.genai import types
from db import (
    fetch_trading_signals, fetch_daily_volumes, fetch_item_list,
    fetch_dow_patterns, fetch_promotion_prices, fetch_owned_item_history,
)
from currency import format_gsc
from settings import get
from pages.promotions import calculate_promotions
from pages.refinement import calculate_refinement


_DOW_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday",
              "Thursday", "Friday", "Saturday"]

_SELL_GOOD_DAYS = {2, 3, 4}   # Tue/Wed/Thu typically highest prices
_SELL_WEAK_DAYS = {5, 6}       # Fri/Sat typically lowest


# ── Data loading ──────────────────────────────────────────────────────

def _load_sell_context() -> dict:
    """
    Assemble full sell context for all owned items across all strategies.
    Returns a dict with keys: signals_df, dow_df, history_df,
    promotions, refinements, prices, inventory.
    """
    signals = fetch_trading_signals()
    items   = fetch_item_list()
    dow     = fetch_dow_patterns()
    history = fetch_owned_item_history()
    promo_prices = fetch_promotion_prices()

    # Merge signals with item metadata
    df = signals.merge(
        items[["item_id", "item_name", "current_count", "rarity"]],
        on="item_id", how="inner",
    )
    df = df[df["current_count"] > 0].copy()  # only owned items

    # Merge daily volumes
    try:
        dvol = fetch_daily_volumes()
        df = df.merge(dvol, on="item_id", how="left")
        df["avg_daily_sold"]   = df["avg_daily_sold"].fillna(0).astype(int)
        df["avg_daily_bought"] = df["avg_daily_bought"].fillna(0).astype(int)
    except Exception:
        df["avg_daily_sold"]   = 0
        df["avg_daily_bought"] = 0

    # Cast numerics
    for col in ["latest_sell", "latest_buy", "avg_sell_30d", "avg_buy_30d",
                "hist_max_sell", "hist_max_buy", "hist_min_sell", "hist_min_buy",
                "sell_z_score", "buy_z_score", "sell_range_pct",
                "sell_trend_3d_vs_7d", "sell_volatility_pct",
                "buy_trend_3d_vs_7d", "current_count"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Promotion and refinement data
    prices    = {
        row["item_name"]: (int(row["buy_price_copper"]), int(row["sell_price_copper"]))
        for _, row in promo_prices.iterrows()
    }
    inventory = {
        row["item_name"]: int(row["current_count"])
        for _, row in promo_prices.iterrows()
    }

    promotions  = [p for p in calculate_promotions(prices, inventory)
                   if p["profit"] > 0 and p["crafts_possible"] > 0]
    refinements = [r for r in calculate_refinement(prices, inventory)
                   if r["profit"] > 0 and r["owned_raw"] >= r["raw_qty"]]

    return {
        "df": df,
        "dow_df": dow,
        "history_df": history,
        "promotions": promotions,
        "refinements": refinements,
        "prices": prices,
        "inventory": inventory,
    }


# ── Snapshot builder ──────────────────────────────────────────────────

def _gw2tp_url(item_id: int, item_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", item_name.lower()).strip("-")
    return f"https://www.gw2tp.com/item/{item_id}-{slug}"


def _dow_context(item_id: int, dow_df: pd.DataFrame, today_dow: int) -> str:
    """Return a short string describing the day-of-week sell context."""
    if dow_df.empty:
        return "no DOW data"
    item_dow = dow_df[dow_df["item_id"] == item_id].copy()
    if item_dow.empty:
        return "no DOW data"

    item_dow["avg_sell"] = pd.to_numeric(item_dow["avg_sell"], errors="coerce")
    item_dow = item_dow.sort_values("day_of_week")

    best_day_idx = item_dow.loc[item_dow["avg_sell"].idxmax(), "day_of_week"]
    best_day = _DOW_NAMES[int(best_day_idx)]
    today_name = _DOW_NAMES[today_dow]

    today_row = item_dow[item_dow["day_of_week"] == today_dow]
    if today_row.empty:
        return f"best day to sell: {best_day}"

    today_avg = today_row["avg_sell"].values[0]
    max_avg   = item_dow["avg_sell"].max()
    pct_of_best = round((today_avg / max_avg * 100) if max_avg > 0 else 0, 0)

    return (
        f"today ({today_name}) = {pct_of_best:.0f}% of best sell day ({best_day})"
    )


def _price_sparkline(item_id: int, history_df: pd.DataFrame) -> str:
    """Return a compact 7-day price summary string."""
    item_hist = history_df[history_df["item_id"] == item_id].copy()
    if item_hist.empty:
        return "no recent history"

    for col in ["min_sell", "avg_sell", "max_sell"]:
        item_hist[col] = pd.to_numeric(item_hist[col], errors="coerce").fillna(0)

    rows = []
    for _, row in item_hist.tail(7).iterrows():
        rows.append(
            f"{row['price_date']}: "
            f"{format_gsc(int(row['min_sell']))}-{format_gsc(int(row['max_sell']))} "
            f"(avg {format_gsc(int(row['avg_sell']))})"
        )
    return " | ".join(rows)


def _build_sell_snapshot(ctx: dict) -> str:
    """
    Build the full sell analysis context for the AI.
    Sections: owned items, promotions, refinements.
    """
    df       = ctx["df"]
    dow_df   = ctx["dow_df"]
    hist_df  = ctx["history_df"]
    promotions  = ctx["promotions"]
    refinements = ctx["refinements"]

    # Today's DOW (GW2 convention: 0=Sun)
    try:
        tz = pytz.timezone(get("timezone"))
    except Exception:
        tz = pytz.UTC
    today_dow = (datetime.now(tz).weekday() + 1) % 7

    buf = io.StringIO()

    # ── Section 1: Owned Items ────────────────────────────────────────
    buf.write("=== OWNED ITEMS ===\n")
    buf.write(
        "Columns: item, gw2tp_url, qty, current_sell, 30d_avg_sell, "
        "30d_high_sell, sell_z_score, sell_range_pct, "
        "sell_trend_3d_vs_7d, avg_daily_bought, "
        "above_30d_high, total_sell_proceeds, dow_context, 7d_price_shape\n\n"
    )

    for _, row in df.sort_values("sell_range_pct", ascending=False).iterrows():
        iid   = int(row["item_id"])
        name  = row["item_name"]
        qty   = int(row["current_count"])
        sell  = int(row["latest_sell"])
        avg   = int(row["avg_sell_30d"])
        high  = int(row["hist_max_sell"])
        proceeds = int(sell * 0.85 * qty)
        above_high = sell > high

        buf.write(
            f"item={name}\n"
            f"  gw2tp_url={_gw2tp_url(iid, name)}\n"
            f"  qty={qty}\n"
            f"  current_sell={format_gsc(sell)}\n"
            f"  30d_avg_sell={format_gsc(avg)}\n"
            f"  30d_high_sell={format_gsc(high)}\n"
            f"  sell_z_score={row['sell_z_score']:.2f}\n"
            f"  sell_range_pct={row['sell_range_pct']:.1f}%\n"
            f"  sell_trend_3d_vs_7d={row['sell_trend_3d_vs_7d']:+.1f}%\n"
            f"  avg_daily_bought={int(row['avg_daily_bought'])}\n"
            f"  above_30d_high={'YES' if above_high else 'NO'}\n"
            f"  total_sell_proceeds={format_gsc(proceeds)}\n"
            f"  dow_context={_dow_context(iid, dow_df, today_dow)}\n"
            f"  7d_price_shape={_price_sparkline(iid, hist_df)}\n\n"
        )

    # ── Section 2: Promotions I can run now ──────────────────────────
    buf.write("=== MYSTIC FORGE PROMOTIONS (profitable + have materials) ===\n")
    if promotions:
        buf.write(
            "Columns: recipe, crafts_possible, profit_per_craft, "
            "profit_per_shard, total_profit_if_all_crafted\n\n"
        )
        for p in promotions:
            total = p["profit"] * p["crafts_possible"]
            buf.write(
                f"recipe={p['name']}\n"
                f"  crafts_possible={p['crafts_possible']}\n"
                f"  profit_per_craft={format_gsc(p['profit'])}\n"
                f"  profit_per_shard={format_gsc(p['profit_per_shard'])}\n"
                f"  total_profit_if_all_crafted={format_gsc(total)}\n\n"
            )
    else:
        buf.write("None currently profitable.\n\n")

    # ── Section 3: Refinements I can run now ─────────────────────────
    buf.write("=== CRAFTING REFINEMENTS (profitable + have materials) ===\n")
    if refinements:
        buf.write(
            "Columns: recipe, crafts_possible, profit_per_craft, "
            "profit_pct, total_profit_if_all_crafted\n\n"
        )
        for r in refinements:
            total = r["profit"] * r["crafts_possible"]
            buf.write(
                f"recipe={r['name']}\n"
                f"  crafts_possible={r['crafts_possible']}\n"
                f"  profit_per_craft={format_gsc(r['profit'])}\n"
                f"  profit_pct={r['profit_pct']:.1f}%\n"
                f"  total_profit_if_all_crafted={format_gsc(total)}\n\n"
            )
    else:
        buf.write("None currently profitable.\n\n")

    return buf.getvalue()


# ── AI call ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert Guild Wars 2 Trading Post investment advisor.
Your job is to help a player maximize gold by deciding what to do
with the items they currently own.

Today's date is {today}.

You have access to Google Search. Search for:
- Current GW2 events, festivals, patches, and balance changes
- Any community discussion about current TP trends
- Upcoming content that might affect material demand

You will receive three sections of market data:
1. OWNED ITEMS: Every item the player owns with price signals,
   sell context, and 7-day price shape
2. MYSTIC FORGE PROMOTIONS: Profitable recipes the player can run
   right now with their current materials
3. CRAFTING REFINEMENTS: Profitable refine recipes they can run now

KEY DEFINITIONS:
- above_30d_high=YES means the current price exceeds the highest
  price seen in the past 30 days (excluding last 12h) -- strong sell signal
- sell_z_score: std devs above 30d average (>0.5 = above normal,
  >1.5 = unusually high)
- sell_range_pct: position in 30d min/max range (100% = at ceiling)
- sell_trend_3d_vs_7d: recent momentum (positive = still rising,
  negative = starting to fall -- sell before it drops further)
- dow_context: how today compares to the best day of the week to sell
- 7d_price_shape: daily min-max-avg to show if price is climbing,
  peaking, or already falling
- total_sell_proceeds: gold received if entire stack sold now (after 15% tax)

ANALYSIS FRAMEWORK -- for each item, consider:
1. Is the price at or above its 30d high? (strongest sell signal)
2. Is the price unusually high (z_score > 0.5)?
3. Is today a good day to sell (dow_context)?
4. Is the trend still rising or starting to fall?
5. Is there a GW2 event driving demand that might end soon?
6. Would the player make more gold promoting or refining these
   materials instead of selling them raw?

OUTPUT FORMAT -- produce exactly three sections:

## Sell Now
Top 10 items to sell on the Trading Post, ranked by sell_range_pct
(highest = closest to 30d ceiling = strongest sell signal).
| # | Item | Qty | Proceeds | Confidence | Why |
|---|------|-----|----------|------------|-----|
- Item column MUST be a markdown link: [Name](gw2tp_url)
- Sort by sell_range_pct descending, limit to 10 items
- Confidence: High / Medium / Low
- Why: 1-2 sentences citing z-score, above_30d_high, trend, DOW context,
  and any relevant GW2 event

## Promote Now
Mystic Forge promotions to run before selling.
| # | Recipe | Crafts | Total Profit | Why |
|---|--------|--------|-------------|-----|
- Only include if promotion profit > direct TP sale profit for same materials
- Sort by total_profit_if_all_crafted descending

## Refine Now
Crafting refinements to run before selling.
| # | Recipe | Crafts | Total Profit | Why |
|---|--------|--------|-------------|-----|
- Only include if refinement profit > direct TP sale profit for raw materials
- Sort by total_profit_if_all_crafted descending

After all tables, one paragraph of Market Context (3 sentences max)
summarizing what your search found about current GW2 events and
how they affect the player's holdings.

RULES:
1. Sell Now is strictly limited to the top 10 by sell_range_pct -- no exceptions.
2. Promote Now and Refine Now only appear if genuinely more profitable
   than selling the raw materials directly.
3. Confidence = High only if: above_30d_high=YES OR z_score > 1.0
   AND sell_trend positive or flat AND dow_context >= 80% of best day.
"""


def _extract_text(response) -> str:
    if response is None:
        return ""
    try:
        if response.text:
            return response.text
    except (ValueError, AttributeError):
        pass
    parts = []
    for candidate in (response.candidates or []):
        content = getattr(candidate, "content", None)
        if content is None:
            continue
        for part in (getattr(content, "parts", None) or []):
            text = getattr(part, "text", None)
            if text and not getattr(part, "thought", False):
                parts.append(text)
    return "\n".join(parts).strip()


def _call_gemini(api_key: str, snapshot: str) -> str:
    client = genai.Client(api_key=api_key)
    system = _SYSTEM_PROMPT.format(today=date.today().isoformat())
    user_content = (
        "Here is my complete market data. Search for current GW2 news "
        "first, then analyze all three sections to produce your "
        "Sell Now, Promote Now, Refine Now, and Hold tables.\n\n"
        f"{snapshot}"
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
            max_output_tokens=8192,
            thinking_config=types.ThinkingConfig(thinking_budget=4096),
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    text = _extract_text(response)
    if text:
        return text

    response2 = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
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
        "Analyzes everything you own — direct TP sales, Mystic Forge "
        "promotions, and crafting refinements — alongside current GW2 "
        "events to tell you exactly what to sell, promote, refine, or hold."
    )

    if st.button("🤖 Analyze My Holdings", type="primary"):
        with st.spinner("Loading market data and your inventory..."):
            try:
                ctx = _load_sell_context()
            except Exception as exc:
                import traceback
                traceback.print_exc()
                st.error(f"Database error: {exc}")
                st.code(traceback.format_exc(), language="text")
                return

            if ctx["df"].empty:
                st.warning(
                    "No owned items found. Make sure your n8n inventory "
                    "workflow is running."
                )
                return

            owned_count = len(ctx["df"])
            promo_count = len(ctx["promotions"])
            ref_count   = len(ctx["refinements"])
            st.caption(
                f"Found {owned_count} owned items, "
                f"{promo_count} profitable promotions, "
                f"{ref_count} profitable refinements."
            )

        with st.spinner("Searching GW2 news and analyzing your holdings..."):
            try:
                snapshot = _build_sell_snapshot(ctx)
                analysis = _call_gemini(api_key, snapshot)
                st.session_state["ai_analysis"] = analysis
            except Exception as exc:
                import traceback
                traceback.print_exc()
                st.error(f"Gemini API error: {exc}")
                st.code(traceback.format_exc(), language="text")

    if "ai_analysis" in st.session_state:
        st.divider()
        st.markdown(st.session_state["ai_analysis"])