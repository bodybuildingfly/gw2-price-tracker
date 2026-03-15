"""
Mystic Forge material promotion recipes and profit calculator.

Recipes sourced from https://wiki.guildwars2.com/wiki/Mystic_Forge/Material_Promotion
Philosopher's Stones: 10 per Spirit Shard (from Miyani vendor)

Fine materials T5->T6:  50 T5 + 1 T6 + 5 Crystalline Dust + 5 Philosopher's Stones -> avg 6 T6
Fine materials T4->T5:  50 T4 + 1 T5 + 5 Incandescent Dust + 4 Philosopher's Stones -> avg 6 T5
Common materials T5->T6: 250 T5 + 1 T6 + 5 Crystalline Dust + 5 Philosopher's Stones -> avg 19 T6
Common materials T4->T5: 250 T4 + 1 T5 + 5 Incandescent Dust + 4 Philosopher's Stones -> avg 86 T5
"""

# Average output per forge attempt (conservative estimates from community data)
AVG_FINE_OUTPUT = 6
AVG_COMMON_T5_T6_OUTPUT = 19
AVG_COMMON_T4_T5_OUTPUT = 86

# Philosopher's Stones per Spirit Shard
PHILO_PER_SHARD = 10

# ── Recipe definitions ───────────────────────────────────────────────
# Each recipe: (name, input_name, input_qty, output_name, catalyst_name,
#               catalyst_qty, philo_stones, avg_output, category)

FINE_T5_T6 = [
    ("Blood T5->T6", "Vial of Potent Blood", 50, "Vial of Powerful Blood",
     "Pile of Crystalline Dust", 5, 5, AVG_FINE_OUTPUT),
    ("Bone T5->T6", "Large Bone", 50, "Ancient Bone",
     "Pile of Crystalline Dust", 5, 5, AVG_FINE_OUTPUT),
    ("Claw T5->T6", "Large Claw", 50, "Vicious Claw",
     "Pile of Crystalline Dust", 5, 5, AVG_FINE_OUTPUT),
    ("Fang T5->T6", "Large Fang", 50, "Vicious Fang",
     "Pile of Crystalline Dust", 5, 5, AVG_FINE_OUTPUT),
    ("Scale T5->T6", "Large Scale", 50, "Armored Scale",
     "Pile of Crystalline Dust", 5, 5, AVG_FINE_OUTPUT),
    ("Totem T5->T6", "Intricate Totem", 50, "Elaborate Totem",
     "Pile of Crystalline Dust", 5, 5, AVG_FINE_OUTPUT),
    ("Venom T5->T6", "Potent Venom Sac", 50, "Powerful Venom Sac",
     "Pile of Crystalline Dust", 5, 5, AVG_FINE_OUTPUT),
]

FINE_T4_T5 = [
    ("Blood T4->T5", "Vial of Thick Blood", 50, "Vial of Potent Blood",
     "Pile of Incandescent Dust", 5, 4, AVG_FINE_OUTPUT),
    ("Bone T4->T5", "Heavy Bone", 50, "Large Bone",
     "Pile of Incandescent Dust", 5, 4, AVG_FINE_OUTPUT),
    ("Claw T4->T5", "Sharp Claw", 50, "Large Claw",
     "Pile of Incandescent Dust", 5, 4, AVG_FINE_OUTPUT),
    ("Fang T4->T5", "Sharp Fang", 50, "Large Fang",
     "Pile of Incandescent Dust", 5, 4, AVG_FINE_OUTPUT),
    ("Scale T4->T5", "Smooth Scale", 50, "Large Scale",
     "Pile of Incandescent Dust", 5, 4, AVG_FINE_OUTPUT),
    ("Totem T4->T5", "Engraved Totem", 50, "Intricate Totem",
     "Pile of Incandescent Dust", 5, 4, AVG_FINE_OUTPUT),
    ("Venom T4->T5", "Full Venom Sac", 50, "Potent Venom Sac",
     "Pile of Incandescent Dust", 5, 4, AVG_FINE_OUTPUT),
]

COMMON_T5_T6 = [
    ("Cloth T5->T6", "Silk Scrap", 250, "Gossamer Scrap",
     "Pile of Crystalline Dust", 5, 5, AVG_COMMON_T5_T6_OUTPUT),
    ("Leather T5->T6", "Thick Leather Section", 250, "Hardened Leather Section",
     "Pile of Crystalline Dust", 5, 5, AVG_COMMON_T5_T6_OUTPUT),
    ("Ore T5->T6", "Mithril Ore", 250, "Orichalcum Ore",
     "Pile of Crystalline Dust", 5, 5, AVG_COMMON_T5_T6_OUTPUT),
    ("Wood T5->T6", "Elder Wood Log", 250, "Ancient Wood Log",
     "Pile of Crystalline Dust", 5, 5, AVG_COMMON_T5_T6_OUTPUT),
]

COMMON_T4_T5 = [
    ("Cloth T4->T5", "Linen Scrap", 250, "Silk Scrap",
     "Pile of Incandescent Dust", 5, 4, AVG_COMMON_T4_T5_OUTPUT),
    ("Leather T4->T5", "Rugged Leather Section", 250, "Thick Leather Section",
     "Pile of Incandescent Dust", 5, 4, AVG_COMMON_T4_T5_OUTPUT),
    ("Ore T4->T5", "Platinum Ore", 250, "Mithril Ore",
     "Pile of Incandescent Dust", 5, 4, AVG_COMMON_T4_T5_OUTPUT),
    ("Wood T4->T5", "Hard Wood Log", 250, "Elder Wood Log",
     "Pile of Incandescent Dust", 5, 4, AVG_COMMON_T4_T5_OUTPUT),
]

ALL_RECIPES = FINE_T5_T6 + FINE_T4_T5 + COMMON_T5_T6 + COMMON_T4_T5


def calculate_promotions(prices: dict, inventory: dict) -> list[dict]:
    """
    Calculate profit for all promotion recipes.

    Args:
        prices: dict mapping item_name -> (buy_price_copper, sell_price_copper)
        inventory: dict mapping item_name -> count owned

    Returns:
        List of dicts with recipe profitability, sorted by profit_per_shard desc.
    """
    results = []

    for (name, inp, inp_qty, out, catalyst, cat_qty, philo, avg_out) in ALL_RECIPES:
        # Look up prices (buy = what we pay to acquire, sell = what we get when selling)
        inp_buy = prices.get(inp, (0, 0))[0]        # buy order price to acquire input
        out_sell = prices.get(out, (0, 0))[1]        # sell listing price for output
        cat_buy = prices.get(catalyst, (0, 0))[0]    # buy order price for catalyst
        out_buy = prices.get(out, (0, 0))[0]         # need 1 output as ingredient

        # Skip if any price is missing
        if not all([inp_buy, out_sell, cat_buy, out_buy]):
            continue

        # Cost per craft
        input_cost = inp_buy * inp_qty
        catalyst_cost = cat_buy * cat_qty
        output_ingredient_cost = out_buy * 1  # 1 unit of output material needed
        total_cost = input_cost + catalyst_cost + output_ingredient_cost

        # Revenue per craft (after 15% TP tax)
        revenue = int(out_sell * 0.85 * avg_out)

        # Profit per craft
        profit = revenue - total_cost

        # Spirit shards per craft
        shards_per_craft = philo / PHILO_PER_SHARD

        # Profit per spirit shard
        profit_per_shard = int(profit / shards_per_craft) if shards_per_craft > 0 else 0

        # How many crafts can we do with current inventory?
        owned_input = inventory.get(inp, 0)
        crafts_possible = owned_input // inp_qty

        # Can we buy components cheaply? Check if input is below average
        results.append({
            "name": name,
            "input_name": inp,
            "input_qty": inp_qty,
            "output_name": out,
            "catalyst_name": catalyst,
            "avg_output": avg_out,
            "total_cost": total_cost,
            "revenue": revenue,
            "profit": profit,
            "shards_per_craft": shards_per_craft,
            "profit_per_shard": profit_per_shard,
            "crafts_possible": crafts_possible,
            "owned_input": owned_input,
        })

    # Sort by profit per spirit shard descending
    results.sort(key=lambda r: r["profit_per_shard"], reverse=True)
    return results