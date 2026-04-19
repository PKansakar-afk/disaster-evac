import networkx as nx
import random
import math

def generate_city_grid(n=10, num_shelters=2, num_sources=5, population=1000, capacity_range=(10, 50), speed_range=(1, 10)):
    G = nx.grid_2d_graph(n, n).to_directed()
    mapping = {node: f"{node[0]},{node[1]}" for node in G.nodes()}
    G = nx.relabel_nodes(G, mapping)

    for u, v in G.edges():
        rand_val = random.random()
        if rand_val < 0.50:
            cap = 10
        elif rand_val < 0.80:
            cap = 30
        else:
            cap = 100
        G[u][v]['capacity'] = cap
        G[u][v]['weight'] = random.randint(1, 10)
        G[u][v]['flow'] = 0

    nodes = list(G.nodes())
    shelters = random.sample(nodes, num_shelters)
    remaining_nodes = [n for n in nodes if n not in shelters]
    sources = random.sample(remaining_nodes, num_sources)

    nx.set_node_attributes(G, "regular", "type")
    for s in shelters: G.nodes[s]["type"] = "shelter"
    for s in sources:  G.nodes[s]["type"] = "source"

    G.graph["population"] = population

    # Compute population per source
    pop_per_source = math.ceil(population / num_sources)

    # Compute real shelter capacity
    shelter_cap = math.ceil(population / num_shelters)

    G.add_node("S", type="super")
    G.add_node("T", type="super")

    for source in sources:
        G.add_edge("S", source, capacity=pop_per_source, weight=0, flow=0)

    for shelter in shelters:
        G.add_edge(shelter, "T", capacity=shelter_cap, weight=0, flow=0)
        G.nodes[shelter]["shelter_capacity"]  = shelter_cap
        G.nodes[shelter]["shelter_remaining"] = shelter_cap

    return G, sources, shelters