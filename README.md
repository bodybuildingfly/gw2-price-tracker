# ⚔️ GW2 Price Tracker

A Streamlit-based Guild Wars 2 Trading Post analytics dashboard designed to run as a Docker container on Unraid (or any Docker host). Combines real-time price tracking, trend analysis, and AI-powered trading recommendations.

## Pages

| Page | Description |
|------|-------------|
| **Dashboard** | Total liquid account value in Gold/Silver/Copper with full inventory breakdown |
| **Item Analysis** | Interactive price trends, order book depth, and daily transaction volume charts for any tracked item |
| **Recommendations** | Python-computed Buy/Sell tables filtered by discount %, premium %, and liquidity with daily volume data |
| **AI Recommendations** | Gemini 2.5 Flash analysis with Google Search grounding — produces ranked Top 5 Buy/Sell picks using pre-computed profitability metrics, volume data, and current GW2 event context |
| **Settings** | Persistent timezone and Gemini API key configuration |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  GW2 API    │────▶│  n8n (every  │────▶│  PostgreSQL 17   │
│             │     │  10 minutes) │     │                  │
└─────────────┘     └──────────────┘     │  gw2_items       │
                                         │  gw2_prices      │
┌─────────────┐     ┌──────────────┐     │  mv_item_opps    │
│  Gemini API │◀────│  Streamlit   │◀───▶│  mv_daily_vols   │
│  (on demand)│────▶│  Dashboard   │     └──────────────────┘
└─────────────┘     └──────────────┘
```

**Data flow:**
- **n8n "Update GW2 material prices"** — Polls `/v2/commerce/prices` every 10 minutes, inserts prices + order book quantities into `gw2_prices` (partitioned monthly, 90-day retention)
- **n8n "Update GW2 personal materials"** — Polls account endpoints hourly, updates `gw2_items.current_count` from materials, bank, and character inventories
- **Materialized views** — `mv_item_opportunities` (30-day averages + latest prices) and `mv_daily_volumes` (daily transaction throughput from order book deltas) are refreshed after each price update

## Quick Start

### 1. Configure environment

Edit `docker-compose.yml` and set your database credentials:

```yaml
environment:
  - DB_HOST=<your-postgres-host>
  - DB_PORT=5432
  - DB_NAME=gw2PriceDB
  - DB_USER=gw2user
  - DB_PASSWORD=<your-password>
```

### 2. Run database migrations

```sql
-- 003_daily_volumes_view.sql creates mv_daily_volumes
\i sql/003_daily_volumes_view.sql
REFRESH MATERIALIZED VIEW mv_daily_volumes;
```

### 3. Build & run

```bash
docker compose up -d --build
```

### 4. Access

Open `http://<your-server-ip>:8501` in a browser.

## Database Schema

PostgreSQL 17 with the following objects:

| Object | Type | Purpose |
|--------|------|---------|
| `gw2_items` | Table | Item metadata + personal inventory counts |
| `gw2_prices` | Partitioned table | 10-minute price + order book snapshots (monthly partitions, 90-day retention) |
| `mv_item_opportunities` | Materialized view | 30-day rolling averages + latest prices per item |
| `mv_daily_volumes` | Materialized view | Daily items sold/bought derived from order book deltas |
| `maintain_partitions()` | Function | Creates future partitions, drops expired ones (called by n8n) |

## n8n Workflows

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| Update GW2 material prices | Every 10 min | Fetches all material prices + quantities, inserts into `gw2_prices`, refreshes materialized views |
| Update GW2 personal materials | Hourly | Aggregates inventory from materials/bank/characters, updates `gw2_items.current_count`, runs partition maintenance |

## Development

Source files are bind-mounted in `docker-compose.yml` for live editing:

```yaml
volumes:
  - ./app.py:/app/app.py
  - ./db.py:/app/db.py
  - ./pages:/app/pages
```

Edit files on the host and Streamlit picks up changes on the next page load — no rebuild needed for `.py` changes. Rebuild only when `requirements.txt` changes:

```bash
docker compose up -d --build
```

## Query Caching

All database queries use `@st.cache_data` with TTL-based expiration:

| Query | TTL | Rationale |
|-------|-----|-----------|
| `fetch_item_list` | 10 min | Item catalog rarely changes |
| `fetch_item_trends` | 10 min | Expensive 14-day aggregation |
| `fetch_daily_volumes` | 10 min | Materialized view, refreshed every 10 min |
| `fetch_opportunities` | 5 min | Core dashboard data, refreshed with MV |
| `fetch_latest_volumes` | 5 min | Latest order book snapshot |
| `fetch_price_history` | 5 min | Per-item history (cached per item_id) |