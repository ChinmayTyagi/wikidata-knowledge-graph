"""Resolve Wikipedia article titles to Wikidata entities and pull their
structural claims (item-valued properties only — the edges of our graph).

Input:  data/processed/articles.json
Output: data/processed/entities.json   {title: {qid, label, description, claims: {P: [Q,...]}}}
        data/processed/labels.json     {QID/PID: "human readable label"}
"""
import json
import time
from pathlib import Path

import requests

PROCESSED = Path(__file__).parent.parent / "data" / "processed"
ARTICLES_PATH = PROCESSED / "articles.json"
ENTITIES_PATH = PROCESSED / "entities.json"
LABELS_PATH = PROCESSED / "labels.json"

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "wikidata-knowledge-graph-viz/0.1 (personal project)"}

BATCH = 50


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def get_with_retry(url, params, max_retries=6):
    delay = 1.0
    for attempt in range(max_retries):
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", delay))
            print(f"  429 rate limited, waiting {wait}s...")
            time.sleep(wait)
            delay *= 2
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"Gave up after {max_retries} retries: {url}")


def resolve_titles_to_qids(titles):
    """Wikipedia title -> Wikidata QID via pageprops, following redirects."""
    title_to_qid = {}
    for batch in chunks(titles, BATCH):
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "pageprops",
            "redirects": 1,
            "format": "json",
            "formatversion": 2,
        }
        r = get_with_retry(WIKIPEDIA_API, params)
        data = r.json()
        # map normalized/redirected titles back to the original requested title
        original_of = {t: t for t in batch}
        for norm in data.get("query", {}).get("normalized", []):
            original_of[norm["to"]] = original_of.get(norm["from"], norm["from"])
        for red in data.get("query", {}).get("redirects", []):
            src = original_of.get(red["from"], red["from"])
            original_of[red["to"]] = src

        for page in data.get("query", {}).get("pages", []):
            title = page.get("title")
            orig = original_of.get(title, title)
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                title_to_qid[orig] = qid
        time.sleep(0.2)
    return title_to_qid


def fetch_entities_claims(qids):
    """wbgetentities for claims + label + description, item-valued claims only."""
    entities = {}
    for batch in chunks(qids, BATCH):
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "labels|descriptions|claims",
            "languages": "en",
            "format": "json",
        }
        r = get_with_retry(WIKIDATA_API, params)
        data = r.json().get("entities", {})
        for qid, ent in data.items():
            label = ent.get("labels", {}).get("en", {}).get("value", qid)
            desc = ent.get("descriptions", {}).get("en", {}).get("value", "")
            claims = {}
            for pid, statements in ent.get("claims", {}).items():
                values = []
                for st in statements:
                    mainsnak = st.get("mainsnak", {})
                    if mainsnak.get("snaktype") != "value":
                        continue
                    dv = mainsnak.get("datavalue", {})
                    if dv.get("type") != "wikibase-entityid":
                        continue
                    values.append(dv["value"]["id"])
                if values:
                    claims[pid] = sorted(set(values))
            entities[qid] = {"label": label, "description": desc, "claims": claims}
        time.sleep(0.2)
    return entities


def fetch_labels(ids):
    labels = {}
    ids = sorted(set(ids))
    for batch in chunks(ids, BATCH):
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "labels",
            "languages": "en",
            "format": "json",
        }
        r = get_with_retry(WIKIDATA_API, params)
        data = r.json().get("entities", {})
        for id_, ent in data.items():
            labels[id_] = ent.get("labels", {}).get("en", {}).get("value", id_)
        time.sleep(0.5)
    return labels


def main():
    articles = json.loads(ARTICLES_PATH.read_text())
    titles = [a["title"] for a in articles]

    print(f"Resolving {len(titles)} titles to Wikidata QIDs...")
    title_to_qid = resolve_titles_to_qids(titles)
    unresolved = [t for t in titles if t not in title_to_qid]
    print(f"Resolved {len(title_to_qid)}/{len(titles)}. Unresolved: {unresolved[:20]}"
          + (" ..." if len(unresolved) > 20 else ""))

    qids = sorted(set(title_to_qid.values()))
    print(f"Fetching claims for {len(qids)} entities...")
    entities_by_qid = fetch_entities_claims(qids)

    # build title-keyed entities.json, carrying visit metadata along
    articles_by_title = {a["title"]: a for a in articles}
    entities = {}
    for title, qid in title_to_qid.items():
        ent = entities_by_qid.get(qid)
        if not ent:
            continue
        entities[title] = {
            "qid": qid,
            "label": ent["label"],
            "description": ent["description"],
            "claims": ent["claims"],
            "visits": articles_by_title[title]["visits"],
            "last_seen": articles_by_title[title]["last_seen"],
        }

    # collect every value id and property id referenced, so the viz can show labels
    value_ids = set()
    prop_ids = set()
    for ent in entities.values():
        for pid, vals in ent["claims"].items():
            prop_ids.add(pid)
            value_ids.update(vals)

    print(f"Fetching labels for {len(value_ids)} value entities and {len(prop_ids)} properties...")
    labels = {}
    labels.update(fetch_labels(value_ids))
    labels.update(fetch_labels(prop_ids))
    # also include the seed entities' own labels for convenience
    for title, ent in entities.items():
        labels[ent["qid"]] = ent["label"]

    ENTITIES_PATH.write_text(json.dumps(entities, indent=2, ensure_ascii=False))
    LABELS_PATH.write_text(json.dumps(labels, indent=2, ensure_ascii=False))
    print(f"Wrote {len(entities)} entities -> {ENTITIES_PATH}")
    print(f"Wrote {len(labels)} labels -> {LABELS_PATH}")


if __name__ == "__main__":
    main()
