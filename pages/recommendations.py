"""
Page 3 — Recommendations
Python-computed BUY / SELL tables with liquidity filtering.
Auto-loads on page visit — no button required.
"""

import streamlit as st
import pandas as pd
from db import fetch_opportunities, fetch_latest_volumes, fetch_daily_volumes
from currency import format_gsc

# Minimum order-book depth to consider an item liquid enough to recommend
_MIN_SELL_LISTINGS = 10
_MIN_BUY_ORDERS = 10


def _load_data() -> pd.DataFrame:
    """Fetch opportunities + latest volumes + daily transaction volumes, merged."""
    opp = fetch_opportunities()
    vol = fetch_latest_volumes()
    df = opp.merge(vol, on="item_id", how="left")
    df["sell_quantity"] = df["sell_quantity"].fillna(0).astype(int)
    df["buy_quantity"] = df["buy_quantity"].fillna(0).astype(int)

    try:
        dvol = fetch_daily_volumes()
        df = df.merge(dvol, on="item_id", how="left")
        df["avg_daily_sold"] = df["avg_daily_sold"].fillna(0).astype(int)
        df["avg_daily_bought"] = df["avg_daily_bought"].fillna(0).astype(int)
    except Exception:
        df["avg_daily_sold"] = 0
        df["avg_daily_bought"] = 0

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


def _build_buy_table(df: pd.DataFrame) -> pd.DataFrame:
    """Items where latest buy price is below 30d average — good time to buy."""
    df = _clean(df)
    df = df[df["sell_quantity"] >= _MIN_SELL_LISTINGS]

    df["discount"] = df["avg_buy_copper_30d"] - df["latest_buy_copper"]
    df = df[df["discount"] > 0].sort_values("discount", ascending=False)
    df["discount_pct"] = ((df["discount"] / df["avg_buy_copper_30d"]) * 100).round(1)

    return pd.DataFrame({
        "Item": df["item_name"],
        "Buy Price": df["latest_buy_copper"].apply(format_gsc),
        "30d Avg Buy": df["avg_buy_copper_30d"].apply(format_gsc),
        "Discount %": df["discount_pct"],
        "Sold/Day": df["avg_daily_sold"],
    }).reset_index(drop=True)


def _build_sell_table(df: pd.DataFrame) -> pd.DataFrame:
    """Inventory items above 30d avg with enough demand to actually sell."""
    df = _clean(df)
    df = df[df["current_count"] > 0].copy()
    df = df[df["buy_quantity"] >= _MIN_BUY_ORDERS]

    df["premium"] = df["latest_sell_copper"] - df["avg_sell_copper_30d"]
    df = df[df["premium"] > 0].sort_values("premium", ascending=False)
    df["premium_pct"] = ((df["premium"] / df["avg_sell_copper_30d"]) * 100).round(1)

    return pd.DataFrame({
        "Item": df["item_name"],
        "Qty": df["current_count"],
        "Sell Price": df["latest_sell_copper"].apply(format_gsc),
        "Above Avg": df["premium_pct"],
        "Bought/Day": df["avg_daily_bought"],
    }).reset_index(drop=True)


def page_recommendations() -> None:
    st.header("Recommendations")

    try:
        df = _load_data()
    except Exception as exc:
        st.error(f"Failed to load data from the database: {exc}")
        return

    if df.empty:
        st.warning("No opportunity data available. Is the n8n workflow populating the database?")
        return

    buy_df = _build_buy_table(df)
    sell_df = _build_sell_table(df)

    st.subheader("📈 Buy — Below 30-Day Average")
    if buy_df.empty:
        st.info("No items are currently priced below their 30-day average.")
    else:
        st.caption(f"{len(buy_df)} items — filtered for discount & liquidity")
        st.dataframe(
            buy_df,
            hide_index=True,
            width="stretch",
            height=400,
            column_config={
                "Discount %": st.column_config.NumberColumn(format="%.1f %%"),
            },
        )

    st.subheader("💰 Sell — Above 30-Day Average")
    if sell_df.empty:
        st.info("No inventory items are currently above their 30-day average sell price.")
    else:
        st.caption(f"{len(sell_df)} items — filtered for demand & premium over average")
        st.dataframe(
            sell_df,
            hide_index=True,
            width="stretch",
            height=400,
            column_config={
                "Above Avg": st.column_config.NumberColumn(format="+%.1f %%"),
            },
        )