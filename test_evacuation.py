import networkx as nx
import random
import matplotlib.pyplot as plt

# ----------------------------
# 1. Generate Synthetic Graph
# ----------------------------

size = 5
G = nx.grid_2d_graph(size, size)
G = G.to_directed()

for u, v in G.edges():
    G[u][v]['weight'] = random.randint(1, 10)     # travel time
    G[u][v]['capacity'] = random.randint(10, 50)  # road capacity


# ----------------------------
# 2. Define Sources and Shelters
# ----------------------------

sources = [(0,0), (0,4)]
shelters = [(4,4), (4,0)]

# add super source and sink
G.add_node("super_source")
G.add_node("super_sink")

for s in sources:
    G.add_edge("super_source", s, capacity=100)

for t in shelters:
    G.add_edge(t, "super_sink", capacity=100)


# ----------------------------
# 3. Baseline: Dijkstra Routing
# ----------------------------

print("\nShortest Paths (Dijkstra):")

for s in sources:
    for t in shelters:
        path = nx.shortest_path(G, s, t, weight='weight')
        length = nx.shortest_path_length(G, s, t, weight='weight')
        print(f"{s} -> {t} | path: {path} | time: {length}")


# ----------------------------
# 4. Proposed: Edmonds-Karp Max Flow
# ----------------------------

flow_value, flow_dict = nx.maximum_flow(
    G,
    "super_source",
    "super_sink",
    capacity="capacity",
    flow_func=nx.algorithms.flow.edmonds_karp
)

print("\nMaximum evacuation flow:", flow_value)

print("\nEdges carrying flow:")
for u in flow_dict:
    for v in flow_dict[u]:
        if flow_dict[u][v] > 0:
            print(f"{u} -> {v} | flow = {flow_dict[u][v]}")


# ----------------------------
# 5. Visualize Network
# ----------------------------

pos = {}

for node in G.nodes:
    if isinstance(node, tuple):  # grid nodes
        pos[node] = node
    else:  # super source/sink
        pos[node] = (size/2, -1 if node=="super_source" else size+1)

nx.draw(G, pos, node_size=300, with_labels=True)
plt.title("Synthetic Evacuation Network")
plt.show()