"""
Page 1 — Main Dashboard
Shows total liquid account value and a summary table from mv_item_opportunities.
"""

import streamlit as st
import pandas as pd
from db import fetch_opportunities
from currency import format_gsc, copper_to_gsc


def page_dashboard() -> None:
    st.header("Dashboard")

    try:
        df = fetch_opportunities()
    except Exception as exc:
        st.error(f"Failed to load data from the database: {exc}")
        return

    if df.empty:
        st.warning("No item data found. Is the n8n workflow populating the database?")
        return

    # ── Total liquid value ───────────────────────────────────────────
    df["total_value_copper"] = df["current_count"] * df["latest_sell_copper"]
    total_copper = int(df["total_value_copper"].sum())
    g, s, c = copper_to_gsc(total_copper)

    col1, col2, col3 = st.columns(3)
    col1.metric("Gold", f"{g:,}")
    col2.metric("Silver", f"{s}")
    col3.metric("Copper", f"{c}")

    st.metric("Total Liquid Account Value", format_gsc(total_copper))

    st.divider()

    # ── Inventory breakdown table ────────────────────────────────────
    st.subheader("Inventory Breakdown")

    display = df[df["current_count"] > 0].copy()
    if display.empty:
        st.info("No items currently in inventory.")
        return

    display["latest_sell"] = display["latest_sell_copper"].apply(format_gsc)
    display["latest_buy"] = display["latest_buy_copper"].apply(format_gsc)
    display["total_value"] = display["total_value_copper"].apply(format_gsc)

    st.dataframe(
        display[
            ["item_name", "current_count", "latest_sell", "latest_buy", "total_value"]
        ].rename(
            columns={
                "item_name": "Item",
                "current_count": "Qty",
                "latest_sell": "Sell Price",
                "latest_buy": "Buy Price",
                "total_value": "Total Value",
            }
        ),
        width="stretch",
        hide_index=True,
    )