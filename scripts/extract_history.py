"""Extract unique Wikipedia article titles (with visit frequency) from a
browser history export.

Input:  data/raw/WIKI_HISTORY_LAST90.xlsx  (columns: date, title, url, visitCount, ...)
Output: data/processed/articles.json       [{title, visits, first_seen, last_seen}, ...]
"""
import json
import re
import urllib.parse
from pathlib import Path

import pandas as pd

RAW_PATH = Path(__file__).parent.parent / "data" / "raw" / "WIKI_HISTORY_LAST90.xlsx"
OUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "articles.json"

# Non-article namespaces to drop (Special:, Talk:, Wikipedia:, etc.)
NAMESPACE_PREFIXES = (
    "Special:", "Talk:", "Wikipedia:", "File:", "Help:", "Category:",
    "Template:", "Portal:", "User:",
)


def title_from_url(url: str) -> str | None:
    url = url.split("#")[0]
    m = re.search(r"/wiki/([^?]+)", url)
    if not m:
        return None
    title = urllib.parse.unquote(m.group(1)).replace("_", " ")
    if any(title.startswith(p) for p in NAMESPACE_PREFIXES):
        return None
    if title == "Main Page":
        return None
    return title


def main():
    df = pd.read_excel(RAW_PATH)
    df = df[df["url"].str.contains("wikipedia.org/wiki/", na=False)].copy()
    df["clean_title"] = df["url"].apply(title_from_url)
    df = df.dropna(subset=["clean_title"])

    grouped = (
        df.groupby("clean_title")
        .agg(visits=("clean_title", "size"), first_seen=("date", "min"), last_seen=("date", "max"))
        .reset_index()
        .rename(columns={"clean_title": "title"})
        .sort_values("last_seen")
    )
    grouped["first_seen"] = grouped["first_seen"].astype(str)
    grouped["last_seen"] = grouped["last_seen"].astype(str)

    records = grouped.to_dict(orient="records")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    print(f"Wrote {len(records)} unique articles to {OUT_PATH}")


if __name__ == "__main__":
    main()
