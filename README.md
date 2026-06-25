<div align="center">

# Illinois News Cadence

**Measure how often Illinois news outlets publish, and roll the cadence up to county-level coverage.**

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat&logo=python&logoColor=white)
![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=flat&logo=duckdb&logoColor=black)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat&logo=streamlit&logoColor=white)
![pandas](https://img.shields.io/badge/pandas-150458?style=flat&logo=pandas&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-3F4F75?style=flat&logo=plotly&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

</div>

## Overview

Illinois News Cadence harvests recent article metadata from local news outlets, stores it in a DuckDB database, and computes how frequently each outlet publishes. Those per-outlet rates are rolled up into a county-level **Coverage Frequency Index (CFI)** so you can see where local news is dense and where coverage is thin. An interactive Streamlit app renders the results as an Illinois county choropleth alongside sortable outlet tables. The project is an MVP designed for local execution; the starter outlet list is meant to be expanded over time.

## Features

- Harvest article metadata (title, URL, publish time) from RSS/Atom feeds, with sitemap parsing as a fallback.
- Automatic RSS discovery: probes common feed paths and parses `<link rel="alternate">` tags when no feed URL is configured.
- Polite harvesting with a custom User-Agent, per-request timeouts, and configurable throttling between outlets.
- Deduplication by SHA-1 URL hash with a `UNIQUE` constraint so re-runs don't double-count articles.
- Per-outlet metrics: total articles, days active, average posts per day, median gap between posts, and freshness (days since last post).
- County rollup via the Coverage Frequency Index, splitting each outlet's posts/day evenly across the counties it covers.
- Streamlit dashboard with an adjustable lookback window, selectable map metric, county choropleth, and CSV export of outlet metrics.

## Tech stack

- **Python 3.9+**
- **DuckDB** — embedded analytical database (`data/news.duckdb`)
- **feedparser** — RSS/Atom parsing
- **requests** + **BeautifulSoup4** — HTTP and HTML/XML (sitemap) parsing
- **pandas** + **NumPy** — metric computation
- **python-dateutil** — flexible date parsing
- **tqdm**, **tenacity** — progress and retries
- **Streamlit** + **Plotly** — interactive dashboard and choropleth map

## How it works

1. **Seed** — `data/il_outlets.csv` lists outlets with their homepage, optional RSS URL, type, owner, and pipe-delimited Illinois county FIPS codes.
2. **Build** — `scripts/build_db.py` creates the `outlets`, `articles`, and `county_metrics` tables in DuckDB and loads the outlet CSV.
3. **Harvest** — `scripts/harvest.py` fetches recent articles per outlet (RSS first, sitemap fallback), filters to a lookback window, and inserts deduplicated rows into `articles`.
4. **Compute** — `scripts/compute_metrics.py` aggregates per-outlet cadence statistics and rolls them up to a per-county CFI, writing back to `county_metrics` and to CSVs under `outputs/`.
5. **Visualize** — `app/app.py` reads the database and renders the county map plus outlet tables in Streamlit.

The Coverage Frequency Index (CFI) for a county is the sum, over every outlet covering that county, of the outlet's posts-per-day in the window, with each outlet's rate divided equally across all counties it serves. Locality weighting and syndication de-duplication are future enhancements.

## Getting started

### Prerequisites

- Python 3.9 or newer

### Installation

```bash
# 1) Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2) Install dependencies
pip install -r requirements.txt
```

### Run the pipeline

```bash
# 3) Initialize the database and load the seed outlets
python scripts/build_db.py

# 4) Harvest the last 365 days (RSS first, sitemap fallback)
python scripts/harvest.py --days 365 --max-per-outlet 2000

# 5) Compute outlet metrics and county rollups
python scripts/compute_metrics.py --days 365

# 6) Launch the dashboard
streamlit run app/app.py
```

> **Note:** `compute_metrics.py` writes CSVs to an `outputs/` directory. Create it first (`mkdir -p outputs`) if it does not exist.

### Harvest options

| Flag | Default | Description |
| --- | --- | --- |
| `--days` | `365` | Lookback window in days |
| `--max-per-outlet` | `2000` | Cap on items fetched per outlet |
| `--throttle` | `1.0` | Seconds to sleep between outlets |
| `--only-outlet-id` | `None` | Harvest a single outlet by ID |

### Extend the outlet list

Edit `data/il_outlets.csv` to add outlets. `homepage_url` is required; `rss_url` may be blank (the harvester attempts discovery). Provide one or more Illinois county FIPS codes separated by `|` (for example, `17031|17043`). Illinois county FIPS codes all begin with `17`.

## Author

**Devin Oommen** — [devinoommen.com](https://devinoommen.com) · Oommen & Company

## License

Released under the [MIT License](LICENSE).
