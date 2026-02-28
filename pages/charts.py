"""
Shared price chart component — renders a 30-day price history chart
for a given item. Used by Recommendations and AI Recommendations pages.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import pytz
from db import fetch_price_history
from currency import format_gsc
from settings import get


def _make_tick_vals(lo: float, hi: float, n_ticks: int = 6) -> list[int]:
    """Return ~n_ticks nicely-rounded copper values spanning lo..hi."""
    if hi <= lo:
        return [int(lo)]
    raw_step = (hi - lo) / max(n_ticks - 1, 1)
    magnitude = 10 ** int(np.floor(np.log10(max(raw_step, 1))))
    nice_step = int(np.ceil(raw_step / magnitude) * magnitude)
    nice_step = max(nice_step, 1)
    start = int(lo // nice_step) * nice_step
    vals = list(range(start, int(hi) + nice_step, nice_step))
    return vals


def _localize(df: pd.DataFrame, tz_name: str) -> pd.DataFrame:
    """Convert the recorded_at column to the user's chosen timezone."""
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC
    if df["recorded_at"].dt.tz is None:
        df["recorded_at"] = df["recorded_at"].dt.tz_localize("UTC")
    df["recorded_at"] = df["recorded_at"].dt.tz_convert(tz)
    return df


def render_price_chart(item_id: int, item_name: str, height: int = 300) -> None:
    """Render a compact 30-day price history chart for one item."""
    try:
        price_df = fetch_price_history(item_id)
    except Exception:
        st.caption(f"Could not load price history for {item_name}.")
        return

    if price_df.empty:
        st.caption(f"No price history available for {item_name}.")
        return

    tz_name = get("timezone")
    price_df = _localize(price_df, tz_name)

    sell_hover = price_df["sell_price_copper"].apply(format_gsc)
    buy_hover = price_df["buy_price_copper"].apply(format_gsc)

    all_prices = pd.concat(
        [price_df["sell_price_copper"], price_df["buy_price_copper"]]
    )
    tick_vals = _make_tick_vals(all_prices.min(), all_prices.max())
    tick_text = [format_gsc(int(v)) for v in tick_vals]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=price_df["recorded_at"],
            y=price_df["sell_price_copper"],
            mode="lines",
            name="Sell",
            line=dict(color="#e74c3c"),
            hovertemplate="Sell: %{customdata}<extra></extra>",
            customdata=sell_hover,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=price_df["recorded_at"],
            y=price_df["buy_price_copper"],
            mode="lines",
            name="Buy",
            line=dict(color="#2ecc71"),
            hovertemplate="Buy: %{customdata}<extra></extra>",
            customdata=buy_hover,
        )
    )
    fig.update_layout(
        height=height,
        yaxis=dict(
            title="Price",
            tickvals=tick_vals,
            ticktext=tick_text,
        ),
        xaxis_title="",
        legend=dict(orientation="h", y=1.15),
        margin=dict(l=10, r=10, t=10, b=10),
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")