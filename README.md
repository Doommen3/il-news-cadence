# Illinois News Cadence (MVP)

Measure and visualize how frequently Illinois news outlets publish, and roll it up to counties.

**MVP features**
- Harvest recent article metadata (title, URL, publish time) from RSS feeds (preferred) or sitemaps (fallback).
- Store into DuckDB.
- Compute outlet‑level cadence metrics and a county‑level **Coverage Frequency Index (CFI)**.
- Streamlit app with an Illinois county choropleth and outlet table.

> This is a starter project intended for local execution. You will need to expand the outlet list over time.
> The harvester is polite: it prefers RSS and sitemaps, obeys robots.txt by default (requests respects it indirectly) and throttles requests.

---

## Quickstart

```bash
# 1) Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Initialize DB and seed outlets
python scripts/build_db.py

# 4) Harvest last 365 days (RSS first, sitemap fallback)
python scripts/harvest.py --days 365 --max-per-outlet 2000

# 5) Compute metrics and county rollups
python scripts/compute_metrics.py --days 365

# 6) Run the Streamlit app
streamlit run app/app.py
```

The Streamlit app lets you pick the date window, metric (e.g., CFI, total articles, avg/day), and filter by outlet type.

---

## Data model

- `data/news.duckdb` (DuckDB file)
- Tables:
  - `outlets(outlet_id, name, homepage_url, rss_url, outlet_type, owner, counties_fips)`
    - `counties_fips`: JSON array of county FIPS (strings) the outlet covers (e.g., `["17037","17099"]`).
  - `articles(article_id, outlet_id, url, title, published_at, source, retrieved_at, hash)`
  - `county_metrics(county_fips, metric_date, cfi, total_articles, outlets_active, freshness_p50_days, avg_posts_per_day)`

**CFI (Coverage Frequency Index)** (MVP): sum over outlets covering the county of each outlet's **posts per day** in the window, divided equally across all counties that outlet covers. (Locality weighting and syndication down‑weighting can be added later.)

---

## Files & Folders

- `data/il_outlets.csv` – starter list of Illinois outlets with their IL county FIPS coverage.
- `scripts/build_db.py` – create DB and load outlets.
- `scripts/harvest.py` – fetch article metadata (RSS preferred; sitemap fallback), write to DB.
- `scripts/compute_metrics.py` – compute outlet metrics + roll up to counties.
- `app/app.py` – Streamlit UI (map + tables).
- `requirements.txt` – dependencies.

---

## Extend the outlet list

Edit `data/il_outlets.csv` to add or update outlets:
- `homepage_url` is required; `rss_url` can be blank (the harvester tries discovery).
- `counties_fips` accepts multiple FIPS as a pipe `|` separator (e.g., `17031|17043`).
- FIPS for Illinois counties all start with `17xxx`.
- Good seed sources (for you to curate and paste in here): Northwestern Medill "State of Local News" inventory; Illinois Press Association directory.

---

## Notes & next steps

- Add a "locality score" using spaCy NER on article excerpts, and weight CFI accordingly.
- Detect chain‑wide duplicates via MinHash/LSH and down‑weight.
- Backfill historical metrics (2019→present) using GDELT or archived sitemaps for trends.
- Add per‑capita CFI once ACS county populations are joined.
- Add alerting for outlets that stop publishing (freshness > X days).

