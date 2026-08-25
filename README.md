# Wikidata Reading Graph

Turns a personal Wikipedia browsing history into an interactive knowledge-graph
visualization: each article you read becomes a node, and two nodes connect
when Wikidata says the underlying entities share a structural trait
(occupation, instance-of, genre, sport, and so on). Hovering an edge shows
exactly *why* two articles are linked.

This is step one toward a Wikidata-based article recommender: before ranking
new articles to suggest, it's worth seeing what the graph of your existing
interests actually looks like.

## How it works

1. **`scripts/extract_history.py`** — reads a browser history export
   (`.xlsx`, columns `date`, `title`, `url`, `visitCount`, ...), filters to
   `wikipedia.org` article pages, and dedupes into a list of unique article
   titles with visit counts.
2. **`scripts/fetch_wikidata.py`** — resolves each Wikipedia title to its
   Wikidata QID (via the Wikipedia API's `pageprops`), then pulls each
   entity's item-valued claims (e.g. `P106` occupation, `P31` instance of,
   `P136` genre) plus human-readable labels, all from Wikidata's public API.
3. **`scripts/build_graph.py`** — connects two articles when their entities
   share a `(property, value)` pair, e.g. both are `P106` (occupation) =
   *association football player*. Each shared trait is weighted by inverse
   document frequency, so common traits (e.g. `instance of = human`) barely
   count while rare shared traits pull nodes together. Only each node's
   strongest few connections are kept, so the graph stays readable instead
   of collapsing into a hairball.
4. **`web/`** — a static D3.js force-directed graph. Node size = visit
   count, color = dominant entity type, hover an edge to see the shared
   trait(s) driving the connection, click a node to see its full connection
   list in a side panel.

## Running it

```bash
pip install -r requirements.txt

# 1. Put your browser history export at data/raw/WIKI_HISTORY_LAST90.xlsx
#    (gitignored — this file is never committed)

# 2. Run the full pipeline
./scripts/run_pipeline.sh

# 3. Serve the web/ folder locally (fetch() needs http://, not file://)
cd web && python3 -m http.server 8000
# open http://localhost:8000
```

## Privacy note

`data/raw/` is gitignored — the raw browsing history export never gets
committed. `data/processed/` (derived article list + Wikidata graph) *is*
committed, since that's the whole point of the visualization — but it still
reveals reading interests, so double-check `data/processed/articles.json`
before pushing if that's a concern.

## Next steps

- Recommendation layer: given the graph, suggest new (unread) Wikidata
  entities that are structurally close to your reading clusters, with the
  same shared-trait reasoning shown here.
- Community detection (e.g. Louvain) instead of raw `instance_of` for
  coloring, to surface clusters the graph itself finds rather than a single
  dominant type.
- Optional semantic layer: embed article descriptions and show a second,
  text-similarity-based view alongside this explicit graph-relation view.
