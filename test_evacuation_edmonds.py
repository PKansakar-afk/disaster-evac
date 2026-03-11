import networkx as nx
import random
import matplotlib.pyplot as plt

size = 5
G = nx.grid_2d_graph(size, size)
G = G.to_directed()

for u, v in G.edges():
    G[u][v]['weight'] = random.randint(1, 10)     # travel time
    G[u][v]['capacity'] = random.randint(10, 50)  # road capacity

sources = [(0,0), (0,4)]
shelters = [(4,4), (4,0)]

# add super source and sink
G.add_node("super_source")
G.add_node("super_sink")

for s in sources:
    G.add_edge("super_source", s, capacity=100)

for t in shelters:
    G.add_edge(t, "super_sink", capacity=100)

print("\nShortest Paths (Dijkstra):")

for s in sources:
    for t in shelters:
        path = nx.shortest_path(G, s, t, weight='weight')
        length = nx.shortest_path_length(G, s, t, weight='weight')
        print(f"{s} -> {t} | path: {path} | time: {length}")

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

pos = {}

for node in G.nodes:
    if isinstance(node, tuple):
        pos[node] = node
    elif node == "super_source":
        pos[node] = (size/2, -1)
    else:
        pos[node] = (size/2, size+1)

# determine flow edges
flow_edges = []

for u in flow_dict:
    for v in flow_dict[u]:
        if flow_dict[u][v] > 0:
            flow_edges.append((u,v))

plt.figure(figsize=(10, 10))

# 1. Group nodes for color-coding
super_nodes = ["super_source", "super_sink"]
source_nodes = sources
shelter_nodes = shelters
regular_nodes = [n for n in G.nodes if n not in super_nodes + source_nodes + shelter_nodes]

# 2. Draw nodes with appropriate sizes and distinct colors
# We make the super nodes much larger (2500) to fit their long text labels
nx.draw_networkx_nodes(G, pos, nodelist=regular_nodes, node_color="lightblue", node_size=700)
nx.draw_networkx_nodes(G, pos, nodelist=source_nodes, node_color="lightgreen", node_size=700)
nx.draw_networkx_nodes(G, pos, nodelist=shelter_nodes, node_color="lightcoral", node_size=700)
nx.draw_networkx_nodes(G, pos, nodelist=super_nodes, node_color="gold", node_size=2500) 

# 3. Draw background grid edges (faded out to emphasize the flow)
nx.draw_networkx_edges(G, pos, edge_color="whitesmoke", arrows=False)

# 4. Highlight flow edges with curved arrows to prevent overlapping
nx.draw_networkx_edges(
    G,
    pos,
    edgelist=flow_edges,
    edge_color="red",
    width=2.5,
    arrows=True,
    arrowsize=15,
    connectionstyle="arc3,rad=0.15"  # <--- This curves the arrows!
)

# 5. Draw the text labels with a smaller, bolder font
nx.draw_networkx_labels(G, pos, font_size=8, font_weight="bold")

plt.title("Evacuation Flow Distribution (Edmonds-Karp)", fontsize=14, fontweight="bold")
plt.axis("off")
plt.tight_layout()
plt.show()