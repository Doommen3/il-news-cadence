import duckdb, pandas as pd, numpy as np, plotly.express as px, requests, streamlit as st

st.set_page_config(page_title="Illinois News Cadence", layout="wide")
DB = "data/news.duckdb"

@st.cache_data(show_spinner=False)
def load_geojson():
    url = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
    return requests.get(url, timeout=20).json()

@st.cache_data(show_spinner=False)
def load_county_metrics():
    con = duckdb.connect(DB, read_only=True)
    df = con.execute("SELECT * FROM county_metrics ORDER BY county_fips").fetch_df()
    return df

@st.cache_data(show_spinner=False)
def load_outlet_metrics(days: int):
    """Compute outlet metrics in pandas to avoid DuckDB's window+aggregate limitation."""
    days = int(days)
    con = duckdb.connect(DB, read_only=True)
    art = con.execute(f"""
        SELECT outlet_id, published_at
        FROM articles
        WHERE published_at >= now() - INTERVAL {days} DAY
    """).fetch_df()

    if art.empty:
        outlets = con.execute("SELECT outlet_id, name, outlet_type, owner, counties_fips FROM outlets").fetch_df()
        # Return empty metrics merged to outlets for consistent columns
        empty_cols = {
            "total_articles": 0,
            "days_active": 0,
            "avg_posts_per_day": 0.0,
            "median_gap_days": np.nan,
            "freshness_days": np.nan,
        }
        return outlets.assign(**empty_cols)

    # Ensure UTC-aware timestamps
    art["published_at"] = pd.to_datetime(art["published_at"], utc=True, errors="coerce")
    art = art.dropna(subset=["published_at"])

    # Base stats
    art["date"] = art["published_at"].dt.date
    grp = art.groupby("outlet_id", as_index=False)
    stats = grp.agg(
        total_articles=("published_at", "count"),
        days_active=("date", "nunique"),
    )
    stats["avg_posts_per_day"] = stats["total_articles"] / days

    # Median gap in days (per outlet)
    srt = art.sort_values(["outlet_id", "published_at"]).copy()
    srt["gap_days"] = srt.groupby("outlet_id")["published_at"].diff().dt.total_seconds() / 86400.0
    med = srt.groupby("outlet_id", as_index=False)["gap_days"].median().rename(columns={"gap_days": "median_gap_days"})

    # Freshness (days since last post)
    now_utc = pd.Timestamp.now(tz="UTC")
    last_pub = art.groupby("outlet_id", as_index=False)["published_at"].max().rename(columns={"published_at": "last_published_at"})
    last_pub["freshness_days"] = (now_utc - last_pub["last_published_at"]).dt.total_seconds() / 86400.0
    last_pub = last_pub.drop(columns=["last_published_at"])

    # Merge
    metrics = stats.merge(med, on="outlet_id", how="left").merge(last_pub, on="outlet_id", how="left")

    # Enrich with outlet metadata
    outlets = con.execute("SELECT outlet_id, name, outlet_type, owner, counties_fips FROM outlets").fetch_df()
    df = outlets.merge(metrics, on="outlet_id", how="left")
    # Fill missing counts with 0 to avoid None values in the UI
    df[["total_articles", "days_active", "avg_posts_per_day"]] = (
        df[["total_articles", "days_active", "avg_posts_per_day"]].fillna(0)
    )
    return df.sort_values("total_articles", ascending=False, na_position="last")

st.title("Illinois News Cadence")
st.caption("MVP • Publication frequency rolled up to counties (CFI = posts/day summed over outlets, split across covered counties).")

days = st.sidebar.slider("Lookback window (days)", 30, 730, 365, step=15)
metric_choice = st.sidebar.selectbox("Map metric", ["cfi","total_articles","avg_posts_per_day","outlets_active","freshness_p50_days"], index=0)

county_df = load_county_metrics()
if county_df.empty:
    st.warning("No county metrics yet. Run the harvest and compute scripts first.")
else:
    il = county_df[county_df["county_fips"].str.startswith("17")]
    gj = load_geojson()
    # Plotly county GeoJSON uses 'id' = 5-digit FIPS string
    fig = px.choropleth_mapbox(
        il, geojson=gj, locations="county_fips", color=metric_choice,
        featureidkey="id",
        mapbox_style="carto-positron", zoom=5.4, center={"lat": 40.0, "lon": -89.0},
        opacity=0.6, color_continuous_scale="Viridis",
        hover_data={"county_fips": True, metric_choice: True}
    )
    st.plotly_chart(fig, use_container_width=True)
    st.subheader("County rollup (latest snapshot)")
    st.dataframe(il.sort_values(metric_choice, ascending=False), use_container_width=True)

st.subheader("Outlet metrics (computed on the fly)")
outlet_df = load_outlet_metrics(days)
if outlet_df.empty or outlet_df["total_articles"].isna().all():
    st.info("No outlet metrics to show yet. Harvest some data first.")
else:
    st.dataframe(outlet_df, use_container_width=True)
    st.download_button("Download outlet metrics CSV", outlet_df.to_csv(index=False).encode("utf-8"), file_name="outlet_metrics_window.csv", mime="text/csv")

st.markdown("---\n- CFI is a simple posts/day sum split across counties per outlet. Add locality weighting and deduping in later versions.\n- Fill `data/il_outlets.csv` with more outlets + county FIPS to improve coverage.\n- If an outlet lacks RSS, the harvester tries sitemap-based inference.")
