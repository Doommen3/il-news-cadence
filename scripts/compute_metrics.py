#!/usr/bin/env python3
import argparse, json, math
import duckdb, pandas as pd, numpy as np

DB = "data/news.duckdb"

def compute_outlet_metrics(con, days):
    days = int(days)
    df = con.execute(f"""
        SELECT outlet_id, published_at
        FROM articles
        WHERE published_at >= now() - INTERVAL {days} DAY
          AND published_at <= now() + INTERVAL 1 DAY
    """).fetch_df()

    outlets = con.execute("SELECT outlet_id FROM outlets").fetch_df()

    if df.empty:
        return outlets.assign(
            total_articles=0,
            days_active=0,
            avg_posts_per_day=0.0,
            median_gap_days=np.nan,
            freshness_days=np.nan,
        )

    # Force UTC-aware timestamps
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["published_at"])
    if df.empty:
        return outlets.assign(
            total_articles=0,
            days_active=0,
            avg_posts_per_day=0.0,
            median_gap_days=np.nan,
            freshness_days=np.nan,
        )

    df["date"] = df["published_at"].dt.date
    grp = df.groupby("outlet_id", as_index=False)
    stats = grp.agg(
        total_articles=("published_at","count"),
        days_active=("date","nunique")
    )
    stats["avg_posts_per_day"] = stats["total_articles"] / days

    # median gap + freshness
    med_gaps = []
    freshness = []
    now_utc = pd.Timestamp.now(tz="UTC")
    for oid, g in df.sort_values("published_at").groupby("outlet_id"):
        g = g.sort_values("published_at")
        if len(g) >= 2:
            d = g["published_at"].diff().dt.total_seconds().dropna() / 86400.0
            med = float(np.median(d)) if len(d) else float("nan")
        else:
            med = float("nan")
        med_gaps.append((oid, med))

        max_pub = g["published_at"].max()
        # max_pub is tz-aware (UTC), so subtract with tz-aware now
        fres = (now_utc - max_pub).total_seconds()/86400.0
        freshness.append((oid, fres))

    md = pd.DataFrame(med_gaps, columns=["outlet_id","median_gap_days"])
    fr = pd.DataFrame(freshness, columns=["outlet_id","freshness_days"])
    out = stats.merge(md, on="outlet_id", how="left").merge(fr, on="outlet_id", how="left")

    # Merge with full outlet list to include outlets with no articles
    full = outlets.merge(out, on="outlet_id", how="left")
    full[["total_articles", "days_active", "avg_posts_per_day"]] = (
        full[["total_articles", "days_active", "avg_posts_per_day"]].fillna(0)
    )
    return full

def rollup_counties(con, outlet_metrics):
    outlets = con.execute("SELECT outlet_id, name, counties_fips FROM outlets").fetch_df()
    if outlets.empty:
        return pd.DataFrame(columns=["county_fips","metric_date","cfi","total_articles","outlets_active","avg_posts_per_day","freshness_p50_days"])

    rows = []
    for _, r in outlets.iterrows():
        fipses = [x.strip() for x in str(r["counties_fips"]).split("|") if str(x).strip()]
        if not fipses:
            continue
        rows.append({"outlet_id": r["outlet_id"], "name": r["name"], "n_counties": len(fipses), "county_fipses": fipses})

    if not rows:
        return pd.DataFrame(columns=["county_fips","metric_date","cfi","total_articles","outlets_active","avg_posts_per_day","freshness_p50_days"])

    expl = []
    for row in rows:
        for f in row["county_fipses"]:
            expl.append({"outlet_id": row["outlet_id"], "name": row["name"], "county_fips": f, "share": 1.0/row["n_counties"]})
    map_df = pd.DataFrame(expl)

    merged = map_df.merge(outlet_metrics, on="outlet_id", how="left").fillna(0.0)
    merged["ppd"] = merged["avg_posts_per_day"] * merged["share"]
    county = merged.groupby("county_fips", as_index=False).agg(
        cfi=("ppd","sum"),
        total_articles=("total_articles","sum"),
        outlets_active=("outlet_id","nunique"),
        avg_posts_per_day=("avg_posts_per_day","sum")
    )
    fresh = merged.groupby("county_fips", as_index=False)["freshness_days"].median().rename(columns={"freshness_days":"freshness_p50_days"})
    county = county.merge(fresh, on="county_fips", how="left")
    county["metric_date"] = pd.Timestamp.now(tz="UTC").date().isoformat()
    return county[["county_fips","metric_date","cfi","total_articles","outlets_active","avg_posts_per_day","freshness_p50_days"]]

def main(days):
    con = duckdb.connect(DB)
    con.execute("""
    CREATE TABLE IF NOT EXISTS county_metrics (
        county_fips TEXT,
        metric_date DATE,
        cfi DOUBLE,
        total_articles BIGINT,
        outlets_active BIGINT,
        avg_posts_per_day DOUBLE,
        freshness_p50_days DOUBLE
    )
    """ )
    outlet_metrics = compute_outlet_metrics(con, days)
    if outlet_metrics.empty:
        print("No articles in the window; nothing to compute yet.")
        return
    county = rollup_counties(con, outlet_metrics)
    con.register("county_df", county)
    con.execute("DELETE FROM county_metrics WHERE metric_date = CURRENT_DATE")
    con.execute("INSERT INTO county_metrics SELECT * FROM county_df")
    county.to_csv("outputs/county_metrics.csv", index=False)
    outlet_metrics.to_csv("outputs/outlet_metrics.csv", index=False)
    print("Wrote outputs/county_metrics.csv and outputs/outlet_metrics.csv")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()
    main(args.days)
