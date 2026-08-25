"""Turn per-entity Wikidata claims into a weighted graph.

Two entities get an edge if they share a (property, value) pair, e.g. both
have P106 (occupation) = Q937857 (association football player). Shared
values that are extremely common (e.g. P31=Q5 "human", shared by almost
everyone) carry little information, so each shared (property, value) is
weighted by inverse document frequency: rarer shared traits count for more.

Input:  data/processed/entities.json, data/processed/labels.json
Output: data/processed/graph.json  {nodes: [...], edges: [...]}
        web/data/graph.json        (copy, for the browser to fetch)
"""
import json
import math
from collections import defaultdict
from itertools import combinations
from pathlib import Path

PROCESSED = Path(__file__).parent.parent / "data" / "processed"
ENTITIES_PATH = PROCESSED / "entities.json"
LABELS_PATH = PROCESSED / "labels.json"
GRAPH_PATH = PROCESSED / "graph.json"
WEB_DATA_DIR = Path(__file__).parent.parent / "web" / "data"

# Properties excluded from edge-building: not about shared *kind/trait*
# (e.g. "different from", "topic's main category") or too Wikipedia-internal.
EXCLUDED_PROPS = {
    "P373",     # Commons category
    "P910",     # topic's main category
    "P1889",    # different from
    "P2860",    # cites work
    "P1343",    # described by source (bibliographic cross-reference, not a real trait)
    "P5008",    # on focus list of Wikimedia project (Wikipedia-internal bookkeeping)
    "P10527",   # documentation files at (archive bookkeeping)
    "P735",     # given name (coincidental name match, not a real shared trait)
    "P734",     # family name (ditto, unless P22/P25/P26/P40/P3373 already captures real kinship)
    "P6104",    # maintained by WikiProject (Wikipedia-internal bookkeeping)
    "P7763",    # copyright status as a creator (legal/Commons bookkeeping, not a real trait)
    "P5021",    # assessment (evaluative framework, e.g. Bechdel test; redundant with instance-of=film)
}

# Cap on how many entities may share a value before we consider it
# uninformative "hairball glue" (e.g. instance-of=human, country=USA).
MAX_VALUE_DOC_FREQ_RATIO = 0.35

TOP_K_NEIGHBORS = 6  # keep the graph legible: strongest edges per node
MIN_EDGE_WEIGHT = 0.15


def main():
    entities = json.loads(ENTITIES_PATH.read_text())
    labels = json.loads(LABELS_PATH.read_text())
    titles = list(entities.keys())
    n = len(titles)

    # document frequency of each (prop, value) pair across our entity set
    doc_freq = defaultdict(int)
    for title, ent in entities.items():
        for pid, vals in ent["claims"].items():
            if pid in EXCLUDED_PROPS:
                continue
            for vid in vals:
                doc_freq[(pid, vid)] += 1

    max_allowed = max(2, int(n * MAX_VALUE_DOC_FREQ_RATIO))
    informative = {
        pv: freq for pv, freq in doc_freq.items() if 1 < freq <= max_allowed
    }
    idf = {pv: math.log(n / freq) for pv, freq in informative.items()}

    # invert: (prop, value) -> list of titles that have it, restricted to informative pairs
    holders = defaultdict(list)
    for title, ent in entities.items():
        for pid, vals in ent["claims"].items():
            if pid in EXCLUDED_PROPS:
                continue
            for vid in vals:
                if (pid, vid) in informative:
                    holders[(pid, vid)].append(title)

    # accumulate pairwise edge weight + the specific shared traits (for tooltips)
    edge_weight = defaultdict(float)
    edge_reasons = defaultdict(list)
    for (pid, vid), members in holders.items():
        if len(members) < 2:
            continue
        w = idf[(pid, vid)]
        for a, b in combinations(sorted(members), 2):
            edge_weight[(a, b)] += w
            edge_reasons[(a, b)].append(
                {"property": labels.get(pid, pid), "value": labels.get(vid, vid)}
            )

    # keep only the strongest edges per node (top-k) to stay legible
    neighbor_candidates = defaultdict(list)
    for (a, b), w in edge_weight.items():
        neighbor_candidates[a].append((w, b))
        neighbor_candidates[b].append((w, a))

    kept_pairs = set()
    for node, cands in neighbor_candidates.items():
        cands.sort(key=lambda x: -x[0])
        for w, other in cands[:TOP_K_NEIGHBORS]:
            if w < MIN_EDGE_WEIGHT:
                continue
            pair = tuple(sorted((node, other)))
            kept_pairs.add(pair)

    nodes = []
    for title, ent in entities.items():
        # dominant "instance of" label, used for coloring/clustering in the viz
        p31 = ent["claims"].get("P31", [])
        instance_of = labels.get(p31[0], "") if p31 else ""
        nodes.append(
            {
                "id": title,
                "qid": ent["qid"],
                "label": ent["label"],
                "description": ent["description"],
                "instance_of": instance_of,
                "visits": ent["visits"],
                "last_seen": ent["last_seen"],
            }
        )

    edges = []
    for a, b in kept_pairs:
        reasons = edge_reasons[(a, b)]
        reasons.sort(key=lambda r: -idf.get((r["property"], r["value"]), 0))  # best-effort order
        edges.append(
            {
                "source": a,
                "target": b,
                "weight": round(edge_weight[(a, b)], 3),
                "reasons": reasons[:5],
            }
        )

    graph = {"nodes": nodes, "edges": edges}
    GRAPH_PATH.write_text(json.dumps(graph, indent=2, ensure_ascii=False))
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (WEB_DATA_DIR / "graph.json").write_text(json.dumps(graph, ensure_ascii=False))

    isolated = sum(1 for nd in nodes if not any(nd["id"] in (e["source"], e["target"]) for e in edges))
    print(f"Nodes: {len(nodes)}  Edges: {len(edges)}  Isolated nodes: {isolated}")
    print(f"Wrote {GRAPH_PATH} and web/data/graph.json")


if __name__ == "__main__":
    main()
