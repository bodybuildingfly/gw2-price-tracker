"""
Page 2 — Item Analysis
Lets the user pick an item, then displays raw price and volume trends.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from db import fetch_item_list, fetch_price_history, fetch_daily_volumes_detail
from settings import get
from pages.charts import render_price_chart, _localize


def page_item_analysis() -> None:
    st.header("Item Analysis")

    # ── Item selector ────────────────────────────────────────────────
    try:
        items_df = fetch_item_list()
    except Exception as exc:
        st.error(f"Could not load items: {exc}")
        return

    if items_df.empty:
        st.warning("No items found in gw2_items.")
        return

    # Build a mapping for the selectbox
    item_options = dict(
        zip(
            items_df["item_name"] + " (" + items_df["rarity"] + ")",
            items_df["item_id"],
        )
    )

    selected_label = st.selectbox(
        "Select an item",
        options=sorted(item_options.keys()),
        index=None,
        placeholder="Start typing an item name…",
    )

    if selected_label is None:
        st.info("Choose an item from the dropdown to view its price and volume history.")
        return

    item_id = int(item_options[selected_label])

    # ── Fetch raw price history ──────────────────────────────────────
    try:
        price_df = fetch_price_history(item_id)
    except Exception as exc:
        st.error(f"Could not load price history: {exc}")
        return

    if price_df.empty:
        st.warning("No price history found for this item.")
        return

    tz_name = get("timezone")
    price_df = _localize(price_df, tz_name)

    # ── Price Trends chart ───────────────────────────────────────────
    st.subheader("Price Trends")
    render_price_chart(item_id, selected_label, height=400)

    # ── Volume Trends chart ──────────────────────────────────────────
    st.subheader("Volume Trends")

    vol_fig = go.Figure()
    vol_fig.add_trace(
        go.Scatter(
            x=price_df["recorded_at"],
            y=price_df["sell_quantity"],
            mode="lines",
            name="Sell Listings",
            line=dict(color="#e74c3c"),
        )
    )
    vol_fig.add_trace(
        go.Scatter(
            x=price_df["recorded_at"],
            y=price_df["buy_quantity"],
            mode="lines",
            name="Buy Orders",
            line=dict(color="#2ecc71"),
        )
    )
    vol_fig.update_layout(
        yaxis_title="Quantity",
        xaxis_title="Time",
        legend=dict(orientation="h", y=1.12),
        margin=dict(l=20, r=20, t=40, b=20),
        hovermode="x unified",
    )
    st.plotly_chart(vol_fig, width="stretch")

    # ── Daily Transaction Volume chart ────────────────────────────────
    try:
        dvol_df = fetch_daily_volumes_detail()
        dvol_item = dvol_df[dvol_df["item_id"] == item_id].sort_values("snap_date")
    except Exception:
        dvol_item = pd.DataFrame()

    if not dvol_item.empty:
        st.subheader("Daily Transaction Volume")

        txn_fig = go.Figure()
        txn_fig.add_trace(
            go.Bar(
                x=dvol_item["snap_date"],
                y=dvol_item["items_sold"],
                name="Sold",
                marker_color="#e74c3c",
            )
        )
        txn_fig.add_trace(
            go.Bar(
                x=dvol_item["snap_date"],
                y=dvol_item["items_bought"],
                name="Bought",
                marker_color="#2ecc71",
            )
        )
        txn_fig.update_layout(
            barmode="group",
            yaxis_title="Items Traded",
            xaxis_title="Date",
            legend=dict(orientation="h", y=1.12),
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.plotly_chart(txn_fig, width="stretch")