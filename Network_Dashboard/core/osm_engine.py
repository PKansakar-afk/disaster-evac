import math
import random

import networkx as nx

try:
    import osmnx as ox
    OSM_AVAILABLE = True
except ImportError:
    OSM_AVAILABLE = False

# ── Preset locations (point-radius so size is predictable) ───────────────────
PRESET_LOCATIONS = {
    "Rattanakosin — Bangkok Old Town":      {"lat": 13.7510, "lon": 100.4927, "dist": 700},
    "Silom — CBD & Financial District":     {"lat": 13.7234, "lon": 100.5291, "dist": 700},
    "Chatuchak — Northern Bangkok":         {"lat": 13.8199, "lon": 100.5499, "dist": 700},
    "Lat Phrao — Residential Inner Ring":   {"lat": 13.8175, "lon": 100.5697, "dist": 700},
    "Sukhumvit — Dense Urban Corridor":     {"lat": 13.7372, "lon": 100.5601, "dist": 700},
    "Thonburi — West Bank":                 {"lat": 13.7274, "lon": 100.4833, "dist": 700},
    "Bang Na — Eastern Suburbs":            {"lat": 13.6658, "lon": 100.6095, "dist": 700},
    "Don Mueang — Northern Airport Area":   {"lat": 13.9125, "lon": 100.6067, "dist": 700},
}

def _multidigraph_to_digraph(G_raw):
    """
    Collapse a MultiDiGraph to a plain DiGraph, keeping the
    shortest parallel edge (by length) for each (u, v) pair.
    Works with all osmnx versions.
    """
    G = nx.DiGraph()
    for node, data in G_raw.nodes(data=True):
        G.add_node(node, **data)
    for u, v, data in G_raw.edges(data=True):
        if (not G.has_edge(u, v) or
                data.get("length", 9_999) < G[u][v].get("length", 9_999)):
            G.add_edge(u, v, **data)
    return G


def load_osm_graph(
    location_key: str,
    num_shelters: int = 2,
    num_sources:  int = 5,
    population:   int = 100,
    seed:         int = 42,
):
    """
    Download an OSM street network and wire it up exactly like
    generate_city_grid() so the existing routing functions work unchanged.

    Returns
    -------
    G          : nx.DiGraph  with S / T super-nodes attached
    sources    : list of node ids  (hazard zones)
    shelters   : list of node ids  (safe zones)
    node_pos   : dict {node_id: (lon, lat)}  for plotting
    """
    if not OSM_AVAILABLE:
        raise ImportError("osmnx is not installed. Run: pip install osmnx")

    ox.settings.log_console = False
    ox.settings.use_cache   = True

    loc   = PRESET_LOCATIONS[location_key]
    G_raw = ox.graph_from_point(
        (loc["lat"], loc["lon"]),
        dist=loc["dist"],
        network_type="drive",
    )

    # Keep only the largest strongly-connected component
    G_di  = _multidigraph_to_digraph(G_raw)
    scc   = max(nx.strongly_connected_components(G_di), key=len)
    G_di  = G_di.subgraph(scc).copy()

    # Build routing graph with standardised edge attributes
    G = nx.DiGraph()

    for node, data in G_di.nodes(data=True):
        G.add_node(node, x=data["x"], y=data["y"], type="regular")

    for u, v, data in G_di.edges(data=True):
        length  = data.get("length", 100)         # metres
        highway = data.get("highway", "residential")
        if isinstance(highway, list):
            highway = highway[0]

        # Capacity proxy from road class
        if   highway in ("motorway", "trunk", "primary"):   cap = 100
        elif highway in ("secondary", "tertiary"):           cap =  50
        else:                                                cap =  20

        # Travel-time weight (length / avg speed for that road type)
        speeds = {"motorway": 90, "trunk": 70, "primary": 50,
                  "secondary": 40, "tertiary": 30}
        speed  = speeds.get(highway, 20)          # km/h
        weight = max(1, int(length / speed))       # ≈ seconds at scale

        G.add_edge(u, v, capacity=cap, weight=weight, flow=0)

    # Randomly assign sources and shelters
    nodes = list(G.nodes())
    rng = random.Random(seed)
    rng.shuffle(nodes)
    shelters = nodes[:num_shelters]
    sources  = nodes[num_shelters: num_shelters + num_sources]

    nx.set_node_attributes(G, "regular", "type")
    for s in shelters: G.nodes[s]["type"] = "shelter"
    for s in sources:  G.nodes[s]["type"] = "source"

    # Super-source S and super-sink T
    pop_per_source = math.ceil(population / num_sources)
    shelter_cap    = math.ceil(population / num_shelters)

    G.add_node("S", type="super")
    G.add_node("T", type="super")

    for src in sources:
        G.add_edge("S", src, capacity=pop_per_source, weight=0, flow=0)

    for sh in shelters:
        G.add_edge(sh, "T", capacity=shelter_cap, weight=0, flow=0)
        G.nodes[sh]["shelter_capacity"]  = shelter_cap
        G.nodes[sh]["shelter_remaining"] = shelter_cap

    node_pos = {
        n: (d["x"], d["y"])
        for n, d in G.nodes(data=True)
        if n not in ("S", "T")
    }

    return G, sources, shelters, node_pos