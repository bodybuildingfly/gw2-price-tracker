"""
Crafting station refinement recipes and profit calculator.

All refinement is done at a crafting station at no additional cost
(no Spirit Shards, no vendor materials for simple 2:1 recipes).

Simple rule: 2 raw material -> 1 refined material
Profit = (refined_sell * 0.85) - (2 * raw_buy)

Alloy ingots (Bronze, Steel, Darksteel) require vendor lumps (not on TP)
and are excluded.
"""

# (recipe_name, raw_item_name, raw_qty, refined_item_name, tier, category)
REFINEMENT_RECIPES = [
    # Metals -- simple 2:1 ore -> ingot
    ("Copper Refine",       "Copper Ore",     2, "Copper Ingot",         1, "Metal"),
    ("Iron Refine",         "Iron Ore",       2, "Iron Ingot",           2, "Metal"),
    ("Platinum Refine",     "Platinum Ore",   2, "Platinum Ingot",       3, "Metal"),
    ("Mithril Refine",      "Mithril Ore",    2, "Mithril Ingot",        5, "Metal"),
    ("Orichalcum Refine",   "Orichalcum Ore", 2, "Orichalcum Ingot",     6, "Metal"),

    # Wood -- 2 log -> 1 plank
    ("Green Wood Refine",   "Green Wood Log",    2, "Green Wood Plank",    1, "Wood"),
    ("Soft Wood Refine",    "Soft Wood Log",     2, "Soft Wood Plank",     2, "Wood"),
    ("Seasoned Wood Refine","Seasoned Wood Log",  2, "Seasoned Wood Plank", 3, "Wood"),
    ("Hard Wood Refine",    "Hard Wood Log",     2, "Hard Wood Plank",     4, "Wood"),
    ("Elder Wood Refine",   "Elder Wood Log",    2, "Elder Wood Plank",    5, "Wood"),
    ("Ancient Wood Refine", "Ancient Wood Log",  2, "Ancient Wood Plank",  6, "Wood"),

    # Cloth -- 2 scrap -> 1 bolt
    ("Jute Refine",         "Jute Scrap",        2, "Bolt of Jute",        1, "Cloth"),
    ("Wool Refine",         "Wool Scrap",        2, "Bolt of Wool",        2, "Cloth"),
    ("Cotton Refine",       "Cotton Scrap",      2, "Bolt of Cotton",      3, "Cloth"),
    ("Linen Refine",        "Linen Scrap",       2, "Bolt of Linen",       4, "Cloth"),
    ("Silk Refine",         "Silk Scrap",        2, "Bolt of Silk",        5, "Cloth"),
    ("Gossamer Refine",     "Gossamer Scrap",    2, "Bolt of Gossamer",    6, "Cloth"),

    # Leather -- 2 section -> 1 square
    ("Rawhide Refine",      "Rawhide Leather Section",  2, "Rawhide Leather Square",  1, "Leather"),
    ("Thin Refine",         "Thin Leather Section",     2, "Thin Leather Square",     2, "Leather"),
    ("Coarse Refine",       "Coarse Leather Section",   2, "Coarse Leather Square",   3, "Leather"),
    ("Rugged Refine",       "Rugged Leather Section",   2, "Rugged Leather Square",   4, "Leather"),
    ("Thick Refine",        "Thick Leather Section",    2, "Square of Thick Leather", 5, "Leather"),
    ("Hardened Refine",     "Hardened Leather Section", 2, "Square of Hardened Leather", 6, "Leather"),
]


def calculate_refinement(prices: dict, inventory: dict) -> list[dict]:
    """
    Calculate profit for all refinement recipes.

    Args:
        prices:    item_name -> (buy_price_copper, sell_price_copper)
        inventory: item_name -> count owned

    Returns:
        List of result dicts sorted by profit descending.
    """
    results = []

    for (name, raw, raw_qty, refined, tier, category) in REFINEMENT_RECIPES:
        raw_buy     = prices.get(raw,     (0, 0))[0]
        refined_sell = prices.get(refined, (0, 0))[1]
        refined_buy  = prices.get(refined, (0, 0))[0]

        if not raw_buy or not refined_sell:
            continue

        cost     = raw_buy * raw_qty
        revenue  = int(refined_sell * 0.85)
        profit   = revenue - cost

        owned_raw    = inventory.get(raw, 0)
        owned_refined = inventory.get(refined, 0)
        crafts_possible = owned_raw // raw_qty

        # Buy signal: how many could we buy and profitably refine?
        # Use the current raw buy order price as cost basis
        results.append({
            "name": name,
            "raw_name": raw,
            "raw_qty": raw_qty,
            "refined_name": refined,
            "tier": tier,
            "category": category,
            "raw_buy": raw_buy,
            "refined_sell": refined_sell,
            "refined_buy": refined_buy,
            "cost": cost,
            "revenue": revenue,
            "profit": profit,
            "profit_pct": round((profit / cost * 100) if cost > 0 else 0, 1),
            "owned_raw": owned_raw,
            "owned_refined": owned_refined,
            "crafts_possible": crafts_possible,
        })

    results.sort(key=lambda r: r["profit"], reverse=True)
    return results