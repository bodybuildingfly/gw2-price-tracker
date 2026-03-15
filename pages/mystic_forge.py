"""
Page 5 — Mystic Forge
Profit calculator for material promotion recipes.
Shows profit per Spirit Shard for all T4->T5 and T5->T6 promotions.
"""

import streamlit as st
import pandas as pd
from db import fetch_promotion_prices
from currency import format_gsc
from pages.promotions import calculate_promotions


def page_mystic_forge() -> None:
    st.header("Mystic Forge Promotions")

    st.caption(
        "Profit from promoting materials in the Mystic Forge using Spirit Shards. "
        "Costs assume buying inputs via buy order. Revenue assumes selling output "
        "via sell listing after 15% TP tax. Sorted by profit per Spirit Shard."
    )

    try:
        promo_df = fetch_promotion_prices()
    except Exception as exc:
        st.error(f"Failed to load price data: {exc}")
        return

    prices = {
        row["item_name"]: (int(row["buy_price_copper"]), int(row["sell_price_copper"]))
        for _, row in promo_df.iterrows()
    }
    inventory = {
        row["item_name"]: int(row["current_count"])
        for _, row in promo_df.iterrows()
    }
    results = calculate_promotions(prices, inventory)

    if not results:
        st.info("Could not calculate promotions — price data may be missing.")
        return

    profitable = [r for r in results if r["profit"] > 0]
    unprofitable = [r for r in results if r["profit"] <= 0]

    # ── Profitable recipes ────────────────────────────────────────────
    st.subheader("💰 Profitable Promotions")
    if profitable:
        rows = []
        for r in profitable:
            rows.append({
                "Recipe": r["name"],
                "Cost": format_gsc(r["total_cost"]),
                "Revenue": format_gsc(r["revenue"]),
                "Profit": format_gsc(r["profit"]),
                "Profit/Shard": format_gsc(r["profit_per_shard"]),
                "Owned": f"{r['owned_input']:,} / {r['input_qty']}",
                "Crafts": r["crafts_possible"],
            })
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("No profitable promotions at current prices.")

    # ── Unprofitable recipes ──────────────────────────────────────────
    if unprofitable:
        with st.expander(f"❌ Unprofitable recipes ({len(unprofitable)})"):
            rows = []
            for r in unprofitable:
                rows.append({
                    "Recipe": r["name"],
                    "Cost": format_gsc(r["total_cost"]),
                    "Revenue": format_gsc(r["revenue"]),
                    "Loss": format_gsc(abs(r["profit"])),
                })
            st.dataframe(
                pd.DataFrame(rows),
                hide_index=True,
                width="stretch",
            )

    # ── Legend ─────────────────────────────────────────────────────────
    with st.expander("ℹ️ How this works"):
        st.markdown(
            "**Recipes** use the Mystic Forge to upgrade materials to the next tier.\n\n"
            "**Fine materials** (Blood, Bones, Claws, Fangs, Scales, Totems, Venom):\n"
            "- T5→T6: 50 T5 + 1 T6 + 5 Crystalline Dust + 5 Philosopher's Stones → avg 6 T6\n"
            "- T4→T5: 50 T4 + 1 T5 + 5 Incandescent Dust + 4 Philosopher's Stones → avg 6 T5\n\n"
            "**Common materials** (Cloth, Leather, Ore, Wood):\n"
            "- T5→T6: 250 T5 + 1 T6 + 5 Crystalline Dust + 5 Philosopher's Stones → avg 19 T6\n"
            "- T4→T5: 250 T4 + 1 T5 + 5 Incandescent Dust + 4 Philosopher's Stones → avg 86 T5\n\n"
            "**Philosopher's Stones** cost 1 Spirit Shard per 10 stones (from Miyani).\n\n"
            "**Profit/Shard** = profit per craft ÷ spirit shards used per craft."
        )