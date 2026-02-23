"""
Database helpers — SQLAlchemy engine and cached query wrappers for
the GW2 Price Tracker Streamlit app.
"""

import os
import streamlit as st
import pandas as pd
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text


def _get_url() -> str:
    """Build a PostgreSQL connection URL from environment variables."""
    user = quote_plus(os.getenv("DB_USER", "gw2user"))
    password = quote_plus(os.getenv("DB_PASSWORD", "changeme"))
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "gw2")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


@st.cache_resource(show_spinner=False)
def get_engine():
    """
    Return a SQLAlchemy engine.  Cached so a single pool is reused
    across Streamlit re-runs within the same server process.
    """
    return create_engine(_get_url(), pool_pre_ping=True)


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute *sql* and return the result set as a DataFrame."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            return pd.read_sql_query(text(sql), conn, params=params)
    except Exception as exc:
        # If the pool went stale, dispose and retry once
        engine.dispose()
        get_engine.clear()
        engine = get_engine()
        try:
            with engine.connect() as conn:
                return pd.read_sql_query(text(sql), conn, params=params)
        except Exception:
            raise exc


# ── Convenience query functions ──────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def fetch_opportunities() -> pd.DataFrame:
    """Return the full materialized view for dashboard / AI pages."""
    return run_query(
        """
        SELECT item_id,
               item_name,
               current_count,
               avg_sell_copper_30d,
               avg_buy_copper_30d,
               latest_sell_copper,
               latest_buy_copper
          FROM mv_item_opportunities
         ORDER BY (current_count * latest_sell_copper) DESC
        """
    )


@st.cache_data(ttl=600, show_spinner=False)
def fetch_item_list() -> pd.DataFrame:
    """Return all items for the dropdown selector."""
    return run_query(
        """
        SELECT item_id, item_name, rarity, icon_url
          FROM gw2_items
         ORDER BY item_name
        """
    )


@st.cache_data(ttl=300, show_spinner=False)
def fetch_price_history(item_id: int) -> pd.DataFrame:
    """Return raw 3-hour price/volume rows for a single item."""
    return run_query(
        """
        SELECT sell_price_copper,
               buy_price_copper,
               sell_quantity,
               buy_quantity,
               recorded_at
          FROM gw2_prices
         WHERE item_id = :item_id
         ORDER BY recorded_at
        """,
        {"item_id": item_id},
    )


@st.cache_data(ttl=300, show_spinner=False)
def fetch_latest_volumes() -> pd.DataFrame:
    """Return the most recent sell_quantity and buy_quantity per item."""
    return run_query(
        """
        SELECT DISTINCT ON (item_id)
               item_id,
               sell_quantity,
               buy_quantity
          FROM gw2_prices
         ORDER BY item_id, recorded_at DESC
        """
    )


@st.cache_data(ttl=600, show_spinner=False)
def fetch_item_trends() -> pd.DataFrame:
    """
    Per-item trend metrics: 7-day vs prior-7-day averages for prices
    and volumes.  Returns percentage changes so the AI can see momentum.
    """
    return run_query(
        """
        SELECT item_id,

               -- Price averages per window
               AVG(sell_price_copper)
                   FILTER (WHERE recorded_at >= NOW() - INTERVAL '7 days')
                   AS avg_sell_7d,
               AVG(sell_price_copper)
                   FILTER (WHERE recorded_at >= NOW() - INTERVAL '14 days'
                             AND recorded_at <  NOW() - INTERVAL '7 days')
                   AS avg_sell_prior_7d,

               AVG(buy_price_copper)
                   FILTER (WHERE recorded_at >= NOW() - INTERVAL '7 days')
                   AS avg_buy_7d,
               AVG(buy_price_copper)
                   FILTER (WHERE recorded_at >= NOW() - INTERVAL '14 days'
                             AND recorded_at <  NOW() - INTERVAL '7 days')
                   AS avg_buy_prior_7d,

               -- Volume averages per window
               AVG(sell_quantity)
                   FILTER (WHERE recorded_at >= NOW() - INTERVAL '7 days')
                   AS avg_sell_qty_7d,
               AVG(sell_quantity)
                   FILTER (WHERE recorded_at >= NOW() - INTERVAL '14 days'
                             AND recorded_at <  NOW() - INTERVAL '7 days')
                   AS avg_sell_qty_prior_7d,

               AVG(buy_quantity)
                   FILTER (WHERE recorded_at >= NOW() - INTERVAL '7 days')
                   AS avg_buy_qty_7d,
               AVG(buy_quantity)
                   FILTER (WHERE recorded_at >= NOW() - INTERVAL '14 days'
                             AND recorded_at <  NOW() - INTERVAL '7 days')
                   AS avg_buy_qty_prior_7d

          FROM gw2_prices
         WHERE recorded_at >= NOW() - INTERVAL '14 days'
         GROUP BY item_id
        """
    )


@st.cache_data(ttl=600, show_spinner=False)
def fetch_daily_volumes() -> pd.DataFrame:
    """
    Return daily sold/bought volumes from the materialized view.
    Averages the last 7 days to smooth out single-day spikes.
    """
    return run_query(
        """
        SELECT item_id,
               ROUND(AVG(items_sold))::INTEGER   AS avg_daily_sold,
               ROUND(AVG(items_bought))::INTEGER  AS avg_daily_bought
          FROM mv_daily_volumes
         WHERE snap_date >= (CURRENT_DATE - INTERVAL '7 days')
         GROUP BY item_id
        """
    )


@st.cache_data(ttl=600, show_spinner=False)
def fetch_daily_volumes_detail() -> pd.DataFrame:
    """Return per-day sold/bought for the last 7 days (for charts or AI)."""
    return run_query(
        """
        SELECT item_id,
               snap_date,
               items_sold,
               items_bought
          FROM mv_daily_volumes
         WHERE snap_date >= (CURRENT_DATE - INTERVAL '7 days')
         ORDER BY snap_date DESC
        """
    )