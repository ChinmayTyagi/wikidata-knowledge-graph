#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1/3: extracting Wikipedia titles from browser history export =="
python3 scripts/extract_history.py

echo "== 2/3: resolving titles to Wikidata entities + claims =="
python3 scripts/fetch_wikidata.py

echo "== 3/3: building the shared-trait graph =="
python3 scripts/build_graph.py

echo "Done. Open web/index.html (via a local server) to view the graph."
