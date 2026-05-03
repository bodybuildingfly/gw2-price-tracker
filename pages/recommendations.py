"""
Page 3 — Recommendations
Trading opportunities across three strategies:
- Price Breakouts (30d floor/ceiling)
- Sleeping Giants (high margin + high volume + dip recovery)
- Weekend Volatility (day-of-week price patterns)
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from db import (fetch_trading_signals, fetch_daily_volumes, fetch_item_list,
                fetch_sleeping_giants, fetch_dow_patterns)
from currency import format_gsc
from pages.charts import render_price_chart


def _load_data() -> pd.DataFrame:
    """Fetch trading signals + item metadata + daily volumes, merged."""
    signals = fetch_trading_signals()
    items = fetch_item_list()

    df = signals.merge(
        items[["item_id", "item_name", "current_count", "rarity"]],
        on="item_id", how="left",
    )

    try:
        dvol = fetch_daily_volumes()
        df = df.merge(dvol, on="item_id", how="left")
        df["avg_daily_sold"] = df["avg_daily_sold"].fillna(0).astype(int)
        df["avg_daily_bought"] = df["avg_daily_bought"].fillna(0).astype(int)
    except Exception:
        df["avg_daily_sold"] = 0
        df["avg_daily_bought"] = 0

    numeric_cols = [
        "latest_sell", "latest_buy", "avg_sell_30d", "avg_buy_30d",
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


def _get_buy_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Items selling below their 30d historical floor (excl. last 12h)."""
    df = df[
        (df["hist_min_sell"] > 0)
        & (df["latest_sell"] < df["hist_min_sell"])
    ].copy()

    # % below the historical floor
    df["below_floor_pct"] = (
        (df["hist_min_sell"] - df["latest_sell"]) / df["hist_min_sell"] * 100
    ).round(1)

    return df.sort_values("below_floor_pct", ascending=False).head(5)


def _get_sell_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Owned items buying above their 30d historical ceiling (excl. last 12h)."""
    df = df[
        (df["current_count"] > 0)
        & (df["hist_max_buy"] > 0)
        & (df["latest_buy"] > df["hist_max_buy"])
    ].copy()

    # % above the historical ceiling
    df["above_ceiling_pct"] = (
        (df["latest_buy"] - df["hist_max_buy"]) / df["hist_max_buy"] * 100
    ).round(1)

    return df.sort_values("above_ceiling_pct", ascending=False).head(5)


def _render_buy_expanders(df: pd.DataFrame) -> None:
    """Render expandable rows for buy candidates with charts."""
    for _, row in df.iterrows():
        label = (
            f"**{row['item_name']}** — "
            f"Sell: {format_gsc(int(row['latest_sell']))} · "
            f"30d Floor: {format_gsc(int(row['hist_min_sell']))} · "
            f"**{row['below_floor_pct']:.1f}% below**"
        )
        with st.expander(label):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Current Sell", format_gsc(int(row["latest_sell"])))
            c2.metric("30d Floor", format_gsc(int(row["hist_min_sell"])))
            c3.metric("30d Avg Sell", format_gsc(int(row["avg_sell_30d"])))
            c4.metric("Sold/Day", f"{int(row['avg_daily_sold']):,}")
            render_price_chart(int(row["item_id"]), row["item_name"], key_suffix="_buy")


def _render_sell_expanders(df: pd.DataFrame) -> None:
    """Render expandable rows for sell candidates with charts."""
    for _, row in df.iterrows():
        label = (
            f"**{row['item_name']}** — "
            f"Buy: {format_gsc(int(row['latest_buy']))} · "
            f"30d Ceiling: {format_gsc(int(row['hist_max_buy']))} · "
            f"Qty: {int(row['current_count'])} · "
            f"**{row['above_ceiling_pct']:.1f}% above**"
        )
        with st.expander(label):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Current Buy", format_gsc(int(row["latest_buy"])))
            c2.metric("30d Ceiling", format_gsc(int(row["hist_max_buy"])))
            c3.metric("30d Avg Buy", format_gsc(int(row["avg_buy_30d"])))
            c4.metric("Bought/Day", f"{int(row['avg_daily_bought']):,}")
            render_price_chart(int(row["item_id"]), row["item_name"], key_suffix="_sell")


def page_recommendations() -> None:
    st.header("Recommendations")

    try:
        df = _load_data()
    except Exception as exc:
        st.error(f"Failed to load data from the database: {exc}")
        return

    if df.empty:
        st.warning("No trading signal data available. Is the n8n workflow populating the database?")
        return

    buy_df = _get_buy_candidates(df)
    sell_df = _get_sell_candidates(df)

    st.subheader("📈 Buy — Below 30-Day Floor")
    st.caption(
        "Items currently selling below the lowest price seen in the past 30 days "
        "(excluding the last 12 hours). Ranked by % below floor."
    )
    if buy_df.empty:
        st.info("No items currently selling below their 30-day historical floor.")
    else:
        _render_buy_expanders(buy_df)

    st.subheader("💰 Sell — Above 30-Day Ceiling")
    st.caption(
        "Items you own with buy orders above the highest price seen in the past "
        "30 days (excluding the last 12 hours). Ranked by % above ceiling."
    )
    if sell_df.empty:
        st.info("No owned items currently buying above their 30-day historical ceiling.")
    else:
        _render_sell_expanders(sell_df)


# ── Sleeping Giants ───────────────────────────────────────────────────

def _render_sleeping_giants() -> None:
    """Items with 20%+ margin, 100+ daily volume, currently in a dip."""
    st.subheader("💤 Sleeping Giants")
    st.caption(
        "Items with a 20%+ flip margin and 100+ units sold per day, currently "
        "trading in a price dip with signs of recovery. These are the highest "
        "conviction swing trades — high margin AND high liquidity."
    )

    try:
        df = fetch_sleeping_giants()
    except Exception as exc:
        st.error(f"Could not load Sleeping Giants data: {exc}")
        return

    if df.empty:
        st.info("No Sleeping Giants found at current prices. Check back when the market dips.")
        return

    # Cast numerics
    for col in ["latest_sell", "latest_buy", "avg_sell_30d", "avg_buy_30d",
                "hist_max_sell", "buy_z_score", "buy_trend_3d_vs_7d",
                "buy_volatility_pct", "avg_daily_sold", "margin_pct", "current_count"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["profit_per_unit"] = (
        (df["latest_sell"] * 0.85 - df["latest_buy"]).clip(lower=0).astype(int)
    )

    df = df.sort_values("margin_pct", ascending=False).head(10)

    for _, row in df.iterrows():
        label = (
            f"**{row['item_name']}** — "
            f"Margin: **{row['margin_pct']:.1f}%** · "
            f"Profit: {format_gsc(int(row['profit_per_unit']))} · "
            f"Sold/Day: {int(row['avg_daily_sold']):,} · "
            f"Z-Score: {row['buy_z_score']:.1f}"
        )
        with st.expander(label):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Buy Price", format_gsc(int(row["latest_buy"])))
            c2.metric("Sell Price", format_gsc(int(row["latest_sell"])))
            c3.metric("3d Trend", f"{row['buy_trend_3d_vs_7d']:+.1f}%")
            c4.metric("Volatility", f"{row['buy_volatility_pct']:.1f}%")
            render_price_chart(int(row["item_id"]), row["item_name"], key_suffix="_giant")


# ── Weekend Volatility ────────────────────────────────────────────────

_DOW_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday",
              "Thursday", "Friday", "Saturday"]

_WEEKEND_DAYS = {5, 6}    # Friday, Saturday
_WEEKDAY_DAYS = {2, 3, 4}  # Tuesday, Wednesday, Thursday


def _render_weekend_volatility() -> None:
    """Items with meaningful day-of-week price cyclicality."""
    st.subheader("📅 Weekend Volatility")
    st.caption(
        "Items whose prices cycle predictably by day of week. "
        "Weekend columns show typical Friday/Saturday prices vs "
        "Tuesday–Thursday. A large gap means a reliable buy-low/sell-high rhythm."
    )

    try:
        dow_df = fetch_dow_patterns()
        items_df = fetch_item_list()
    except Exception as exc:
        st.error(f"Could not load day-of-week data: {exc}")
        return

    if dow_df.empty:
        st.info("Not enough data yet for day-of-week analysis. Check back after a few more weeks.")
        return

    for col in ["avg_sell", "stddev_sell", "avg_buy", "stddev_buy", "day_of_week"]:
        dow_df[col] = pd.to_numeric(dow_df[col], errors="coerce").fillna(0)

    # Pivot to wide format: one row per item, one column per DOW
    pivot = dow_df.pivot(index="item_id", columns="day_of_week", values="avg_buy")
    pivot.columns = [_DOW_NAMES[c] for c in pivot.columns]

    # Weekend avg (Fri/Sat) vs weekday avg (Tue/Wed/Thu)
    weekend_cols = [_DOW_NAMES[d] for d in _WEEKEND_DAYS if _DOW_NAMES[d] in pivot.columns]
    weekday_cols = [_DOW_NAMES[d] for d in _WEEKDAY_DAYS if _DOW_NAMES[d] in pivot.columns]

    if not weekend_cols or not weekday_cols:
        st.info("Insufficient day-of-week coverage yet.")
        return

    pivot["weekend_avg"] = pivot[weekend_cols].mean(axis=1)
    pivot["weekday_avg"] = pivot[weekday_cols].mean(axis=1)

    # Items that dip on weekends: weekend price notably below weekday price
    pivot["dip_pct"] = (
        (pivot["weekday_avg"] - pivot["weekend_avg"])
        / pivot["weekday_avg"].replace(0, pd.NA) * 100
    ).round(1)

    pivot = pivot[pivot["dip_pct"] >= 5].copy()  # at least 5% cheaper on weekends

    if pivot.empty:
        st.info("No strong day-of-week patterns detected yet. More data needed.")
        return

    pivot = pivot.merge(
        items_df[["item_id", "item_name", "current_count"]],
        left_index=True, right_on="item_id", how="left"
    ).dropna(subset=["item_name"])

    # Show today's position
    from settings import get
    try:
        tz = pytz.timezone(get("timezone"))
    except Exception:
        tz = pytz.UTC
    today_dow = datetime.now(tz).weekday()  # 0=Monday in Python
    # Convert Python DOW (0=Mon) to GW2 DOW (0=Sun)
    today_dow_name = _DOW_NAMES[(today_dow + 1) % 7]

    st.caption(f"Today is **{today_dow_name}**. "
               f"Weekend days (Fri/Sat) tend to be cheapest for these items.")

    pivot = pivot.sort_values("dip_pct", ascending=False).head(15)

    rows = []
    for _, row in pivot.iterrows():
        rows.append({
            "Item": row["item_name"],
            "Weekend Avg": format_gsc(int(row["weekend_avg"])),
            "Weekday Avg": format_gsc(int(row["weekday_avg"])),
            "Weekend Dip": f"{row['dip_pct']:.1f}%",
            "Best Day to Buy": min(
                weekend_cols,
                key=lambda d: row.get(d, float("inf"))
            ),
            "Best Day to Sell": max(
                weekday_cols,
                key=lambda d: row.get(d, 0)
            ),
        })

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
    )


# ── Page ─────────────────────────────────────────────────────────────

def page_recommendations_full() -> None:
    """Wrap the full recommendations page with all strategies."""
    page_recommendations()

    st.divider()
    _render_sleeping_giants()

    st.divider()
    _render_weekend_volatility()