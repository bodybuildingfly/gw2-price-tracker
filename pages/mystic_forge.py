"""
Page 5 -- Mystic Forge
Two tabs:
1. Material Promotions -- Spirit Shard profit from Mystic Forge upgrades
2. Refinement Arbitrage -- profit from refining raw -> refined at crafting station
"""

import streamlit as st
import pandas as pd
from db import fetch_promotion_prices
from currency import format_gsc
from pages.promotions import calculate_promotions
from pages.refinement import calculate_refinement


def page_mystic_forge() -> None:
    st.header("Mystic Forge")

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

    tab1, tab2 = st.tabs(["🔮 Material Promotions", "⚒️ Refinement Arbitrage"])

    # ── Tab 1: Material Promotions ────────────────────────────────────
    with tab1:
        st.caption(
            "Profit from promoting materials in the Mystic Forge using Spirit Shards. "
            "Costs assume buying inputs via buy order. Revenue assumes selling output "
            "via sell listing after 15% TP tax. Sorted by profit per Spirit Shard."
        )

        results = calculate_promotions(prices, inventory)

        if not results:
            st.info("Could not calculate promotions -- price data may be missing.")
        else:
            profitable   = [r for r in results if r["profit"] > 0]
            unprofitable = [r for r in results if r["profit"] <= 0]

            st.subheader("Profitable Promotions")
            if profitable:
                rows = []
                for r in profitable:
                    rows.append({
                        "Recipe":       r["name"],
                        "Cost":         format_gsc(r["total_cost"]),
                        "Revenue":      format_gsc(r["revenue"]),
                        "Profit":       format_gsc(r["profit"]),
                        "Profit/Shard": format_gsc(r["profit_per_shard"]),
                        "Owned":        f"{r['owned_input']:,} / {r['input_qty']}",
                        "Crafts":       r["crafts_possible"],
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            else:
                st.info("No profitable promotions at current prices.")

            if unprofitable:
                with st.expander(f"Unprofitable recipes ({len(unprofitable)})"):
                    rows = []
                    for r in unprofitable:
                        rows.append({
                            "Recipe":  r["name"],
                            "Cost":    format_gsc(r["total_cost"]),
                            "Revenue": format_gsc(r["revenue"]),
                            "Loss":    format_gsc(abs(r["profit"])),
                        })
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        with st.expander("How this works"):
            st.markdown(
                "**Fine materials** (Blood, Bones, Claws, Fangs, Scales, Totems, Venom):\n"
                "- T5 to T6: 50 T5 + 1 T6 + 5 Crystalline Dust + 5 Philosopher's Stones -> avg 6 T6\n"
                "- T4 to T5: 50 T4 + 1 T5 + 5 Incandescent Dust + 4 Philosopher's Stones -> avg 6 T5\n\n"
                "**Common materials** (Cloth, Leather, Ore, Wood):\n"
                "- T5 to T6: 250 T5 + 1 T6 + 5 Crystalline Dust + 5 Philosopher's Stones -> avg 19 T6\n"
                "- T4 to T5: 250 T4 + 1 T5 + 5 Incandescent Dust + 4 Philosopher's Stones -> avg 86 T5\n\n"
                "**Philosopher's Stones** cost 1 Spirit Shard per 10 stones (from Miyani).\n\n"
                "**Profit/Shard** = profit per craft / spirit shards used per craft."
            )

    # ── Tab 2: Refinement Arbitrage ───────────────────────────────────
    with tab2:
        st.caption(
            "Profit from refining raw materials at a crafting station (no Spirit Shards). "
            "Formula: Revenue = refined_sell x 0.85 (TP tax). "
            "Cost = 2 x raw_buy. Sorted by profit per craft."
        )

        ref_results = calculate_refinement(prices, inventory)

        if not ref_results:
            st.info("Could not calculate refinement profits -- price data may be missing.")
        else:
            profitable   = [r for r in ref_results if r["profit"] > 0]
            unprofitable = [r for r in ref_results if r["profit"] <= 0]

            # Category filter
            categories = sorted({r["category"] for r in profitable})
            if categories:
                selected_cats = st.multiselect(
                    "Filter by material type",
                    options=categories,
                    default=categories,
                )
                profitable = [r for r in profitable if r["category"] in selected_cats]

            st.subheader("Profitable Refinements")
            if profitable:
                rows = []
                for r in profitable:
                    rows.append({
                        "Recipe":       r["name"],
                        "Tier":         r["tier"],
                        "Raw (x2)":     format_gsc(r["raw_buy"]),
                        "Cost":         format_gsc(r["cost"]),
                        "Revenue":      format_gsc(r["revenue"]),
                        "Profit":       format_gsc(r["profit"]),
                        "Profit %":     f"{r['profit_pct']:.1f}%",
                        "Owned Raw":    f"{r['owned_raw']:,}",
                        "Crafts":       r["crafts_possible"],
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            else:
                st.info("No profitable refinements at current prices.")

            if unprofitable:
                with st.expander(f"Unprofitable recipes ({len(unprofitable)})"):
                    rows = []
                    for r in unprofitable:
                        rows.append({
                            "Recipe":  r["name"],
                            "Tier":    r["tier"],
                            "Cost":    format_gsc(r["cost"]),
                            "Revenue": format_gsc(r["revenue"]),
                            "Loss":    format_gsc(abs(r["profit"])),
                        })
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        with st.expander("How this works"):
            st.markdown(
                "All recipes use a simple 2:1 ratio at a crafting station:\n"
                "- 2 raw material -> 1 refined material (no additional cost)\n\n"
                "**Profit** = (refined sell price x 0.85) - (2 x raw buy price)\n\n"
                "**When to buy inputs:** If profit is positive and you don't own the raw "
                "material, place buy orders for the raw material and sell orders for the "
                "refined output once crafted.\n\n"
                "Alloy ingots (Bronze, Steel, Darksteel) require vendor lumps and are excluded."
            )