#!/usr/bin/env python3
import time, hashlib, argparse
from urllib.parse import urljoin
import duckdb, feedparser, requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
import pandas as pd
from tqdm import tqdm

DB = "data/news.duckdb"
HEADERS = {"User-Agent": "IL-News-Cadence/0.1 (+https://example.local)"}

def canonicalize_url(base, link):
    if not link: return None
    try:
        return urljoin(base, link)
    except Exception:
        return link

def discover_rss(homepage_url):
    candidates = ["/feed", "/rss", "/rss.xml", "/feed.xml", "/index.xml"]
    for c in candidates:
        test = canonicalize_url(homepage_url, c)
        try:
            r = requests.get(test, headers=HEADERS, timeout=10)
            if r.ok and ("xml" in r.headers.get("Content-Type","") or r.text.strip().startswith("<?xml")):
                return test
        except Exception:
            pass
    try:
        r = requests.get(homepage_url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.find_all("link"):
            rel = (link.get("rel") or [])
            type_ = (link.get("type") or "").lower()
            if ("alternate" in rel) and ("rss" in type_ or "atom" in type_):
                href = link.get("href")
                if href:
                    return canonicalize_url(homepage_url, href)
    except Exception:
        pass
    return None

def parse_rss(url, max_items=500):
    fp = feedparser.parse(url)
    items = []
    for e in fp.entries[:max_items]:
        pub = None
        for k in ["published", "pubDate", "updated", "created"]:
            v = getattr(e, k, None) or e.get(k)
            if v:
                try:
                    pub = dtparser.parse(v)
                    break
                except Exception:
                    continue
        title = getattr(e, "title", "") or e.get("title","" )
        link = getattr(e, "link",  "") or e.get("link", "")
        items.append({"title": title, "link": link, "published": pub})
    return items

def parse_sitemap(homepage_url, max_items=1500):
    items, tested = [], set()
    def get(u):
        if u in tested: return None
        tested.add(u)
        try:
            r = requests.get(u, headers=HEADERS, timeout=12)
            if r.ok: return r.text
        except Exception:
            return None
        return None
    def parse_urls(x):
        soup = BeautifulSoup(x, "xml")
        out = []
        for url in soup.find_all("url"):
            loc = url.loc.text if url.loc else None
            lastmod = url.lastmod.text if url.lastmod else None
            out.append((loc, lastmod))
        return out
    def parse_sitemapindex(x):
        soup = BeautifulSoup(x, "xml")
        out = []
        for sm in soup.find_all("sitemap"):
            loc = sm.loc.text if sm.loc else None
            out.append(loc)
        return out
    root_sm = canonicalize_url(homepage_url, "/sitemap.xml")
    root_txt = get(root_sm)
    if not root_txt: return items
    if "<sitemapindex" in root_txt:
        for sm in parse_sitemapindex(root_txt)[:25]:
            txt = get(sm)
            if not txt: continue
            for loc, lastmod in parse_urls(txt):
                items.append({"title":"", "link": loc, "published": dtparser.parse(lastmod) if lastmod else None})
                if len(items) >= max_items: return items
    else:
        for loc, lastmod in parse_urls(root_txt):
            items.append({"title":"", "link": loc, "published": dtparser.parse(lastmod) if lastmod else None})
            if len(items) >= max_items: break
    return items

def within_days(dt_obj, days):
    """Return True if dt_obj is within the past `days` from now (UTC).
    Handles both tz-aware and tz-naive datetimes robustly.
    """
    if not dt_obj:
        return False
    now_utc = pd.Timestamp.now(tz="UTC")
    try:
        ts = pd.Timestamp(dt_obj)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
    except Exception:
        return False
    return ts >= now_utc - pd.Timedelta(days=days)

def main(days, max_per_outlet, throttle, only_outlet_id):
    con = duckdb.connect(DB)
    # Ensure table exists (no IDENTITY, dedupe by hash)
    con.execute("""
    CREATE TABLE IF NOT EXISTS articles (
        article_id BIGINT,
        outlet_id TEXT,
        url TEXT,
        title TEXT,
        published_at TIMESTAMP,
        source TEXT,
        retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        hash TEXT,
        UNIQUE(hash)
    )
    """)
    outlets = con.execute("""
        SELECT outlet_id, name, homepage_url,
               CASE WHEN NULLIF(rss_url,'') IS NULL THEN NULL ELSE rss_url END AS rss_url
        FROM outlets
    """).fetch_df()

    if only_outlet_id:
        outlets = outlets[outlets["outlet_id"] == only_outlet_id]
        if outlets.empty:
            raise SystemExit(f"Outlet {only_outlet_id} not found")

    def url_hash(u): return hashlib.sha1((u or "").encode("utf-8")).hexdigest()

    inserted_total = 0
    for _, row in tqdm(outlets.iterrows(), total=len(outlets), desc="Outlets"):
        outlet_id = row["outlet_id"]
        homepage = row["homepage_url"]
        rss = row["rss_url"]
        if not rss:
            rss = discover_rss(homepage)

        items, source = [], None
        if rss:
            try:
                items = parse_rss(rss, max_items=max_per_outlet)
                source = "rss"
            except Exception:
                items = []
        if not items:
            try:
                items = parse_sitemap(homepage, max_items=max_per_outlet)
                source = "sitemap"
            except Exception:
                items = []

        items = [it for it in items if within_days(it["published"], days)]
        if not items:
            time.sleep(throttle)
            continue

        for it in items:
            link = it["link"]
            if not link: continue
            h = url_hash(link)
            exists = con.execute("SELECT 1 FROM articles WHERE hash = ? LIMIT 1", [h]).fetchone()
            if exists: continue
            title = it.get("title") or ""
            pub = it.get("published")
            try:
                con.execute("""
                    INSERT INTO articles (outlet_id, url, title, published_at, source, hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, [outlet_id, link, title, pub, source, h])
                inserted_total += 1
            except Exception:
                pass
        time.sleep(throttle)
    print(f"Inserted {inserted_total} new article rows. DB: {DB}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--max-per-outlet", type=int, default=2000)
    ap.add_argument("--throttle", type=float, default=1.0)
    ap.add_argument("--only-outlet-id", type=str, default=None)
    args = ap.parse_args()
    main(args.days, args.max_per_outlet, args.throttle, args.only_outlet_id)
