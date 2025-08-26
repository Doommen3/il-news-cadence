#!/usr/bin/env python3
import duckdb, pandas as pd, pathlib

DB = "data/news.duckdb"
OUTLETS_CSV = "data/il_outlets.csv"

def main():
    con = duckdb.connect(DB)
    con.execute("""
    CREATE TABLE IF NOT EXISTS outlets (
        outlet_id TEXT,
        name TEXT,
        homepage_url TEXT,
        rss_url TEXT,
        outlet_type TEXT,
        owner TEXT,
        counties_fips TEXT
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS articles (
        article_id BIGINT,               -- optional surrogate, not auto-generated
        outlet_id TEXT,
        url TEXT,
        title TEXT,
        published_at TIMESTAMP,
        source TEXT,                     -- 'rss' or 'sitemap'
        retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        hash TEXT,
        UNIQUE(hash)                     -- prevents duplicates
    )
    """)
    # Load outlets CSV (upsert by outlet_id: delete+insert for MVP)
    df = pd.read_csv(OUTLETS_CSV, dtype=str).fillna("")
    needed = ["outlet_id","name","homepage_url","rss_url","outlet_type","owner","counties_fips"]
    for col in needed:
        if col not in df.columns:
            raise SystemExit(f"Missing column in CSV: {col}")
    con.execute("DELETE FROM outlets")
    con.register("df", df)
    con.execute("INSERT INTO outlets SELECT * FROM df")
    print(f"Loaded {len(df)} outlets into {DB}")

if __name__ == "__main__":
    pathlib.Path("data").mkdir(exist_ok=True, parents=True)
    main()
