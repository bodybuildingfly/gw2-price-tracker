"""
Page 3 — Recommendations
Top 5 BUY / SELL opportunities based on 30-day price breakouts.
Buy = current sell price below historical 30d floor (excl. last 24h).
Sell = current buy price above historical 30d ceiling (excl. last 24h).
"""

import streamlit as st
import pandas as pd
from db import fetch_trading_signals, fetch_daily_volumes, fetch_item_list
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
    """Items selling below their 30d historical floor (excl. last 24h)."""
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
    """Owned items buying above their 30d historical ceiling (excl. last 24h)."""
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
            render_price_chart(int(row["item_id"]), row["item_name"])


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
            render_price_chart(int(row["item_id"]), row["item_name"])


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
        "(excluding the last 24 hours). Ranked by % below floor."
    )
    if buy_df.empty:
        st.info("No items currently selling below their 30-day historical floor.")
    else:
        _render_buy_expanders(buy_df)

    st.subheader("💰 Sell — Above 30-Day Ceiling")
    st.caption(
        "Items you own with buy orders above the highest price seen in the past "
        "30 days (excluding the last 24 hours). Ranked by % above ceiling."
    )
    if sell_df.empty:
        st.info("No owned items currently buying above their 30-day historical ceiling.")
    else:
        _render_sell_expanders(sell_df)