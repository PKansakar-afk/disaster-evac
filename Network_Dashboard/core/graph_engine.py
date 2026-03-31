import networkx as nx
import random

def generate_city_grid(n=10, num_shelters=2, num_sources=5, capacity_range=(10, 50), speed_range=(1, 10)):
    G = nx.grid_2d_graph(n, n).to_directed()
    mapping = {node: f"{node[0]},{node[1]}" for node in G.nodes()}
    G = nx.relabel_nodes(G, mapping)

    # 1. Assign random attributes to edges
    for u, v in G.edges():
        # Determine road type probabilities (50% Local, 30% Urban, 20% Highway)
        rand_val = random.random()
        if rand_val < 0.50:
            cap = 10   # Local roads
        elif rand_val < 0.80:
            cap = 30   # Urban roads
        else:
            cap = 100  # Highways
            
        G[u][v]['capacity'] = cap
        G[u][v]['weight'] = random.randint(1, 10) # Travel time U(1,10)
        G[u][v]['flow'] = 0

    # 2. Select Sources (Hazard Zones) and Sinks (Shelters)
    nodes = list(G.nodes())
    shelters = random.sample(nodes, num_shelters)
    remaining_nodes = [n for n in nodes if n not in shelters]
    sources = random.sample(remaining_nodes, num_sources)

    # 3. Add node types for visualization
    nx.set_node_attributes(G, "regular", "type")
    for s in shelters: G.nodes[s]["type"] = "shelter"
    for s in sources: G.nodes[s]["type"] = "source"

    # 4. Add Super-Source (S) and Super-Sink (T) for Flow Algorithms
    G.add_node("S", type="super")
    G.add_node("T", type="super")
    
    # Connect Super-Source to all actual sources (Infinite capacity, 0 cost)
    for source in sources:
        G.add_edge("S", source, capacity=999999, weight=0, flow=0)
        
    # Connect all actual shelters to Super-Sink
    for shelter in shelters:
        G.add_edge(shelter, "T", capacity=999999, weight=0, flow=0)

    return G, sources, shelters

# Quick test
if __name__ == "__main__":
    test_graph = generate_city_grid(5)
    print(f"Generated grid with {test_graph.number_of_nodes()} intersections.")
    print(f"Sample edge data: {list(test_graph.edges(data=True))[0]}")