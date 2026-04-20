import networkx as nx
import random
import matplotlib.pyplot as plt

size = 5
G = nx.grid_2d_graph(size, size)
G = G.to_directed()

# Assign random travel times (weights) and capacities
for u, v in G.edges():
    G[u][v]['weight'] = random.randint(1, 10)     # travel time
    G[u][v]['capacity'] = random.randint(10, 50)  # road capacity

sources = [(0,0), (0,4)]
shelters = [(4,4), (4,0)]

# Add super source and sink
G.add_node("super_source")
G.add_node("super_sink")

# Connect super nodes. 
for s in sources:
    G.add_edge("super_source", s, capacity=100, weight=0)

for t in shelters:
    G.add_edge(t, "super_sink", capacity=100, weight=0)

print("\n--- Fastest Overall Evacuation Route (Dijkstra) ---")

# Find the absolute shortest path from any source to any shelter
best_path = nx.shortest_path(G, "super_source", "super_sink", weight='weight')
best_time = nx.shortest_path_length(G, "super_source", "super_sink", weight='weight')

print(f"Path: {best_path}")
print(f"Total Travel Time: {best_time}")

# Convert the path of nodes into a list of edges so we can draw them
dijkstra_edges = [(best_path[i], best_path[i+1]) for i in range(len(best_path)-1)]

pos = {}
for node in G.nodes:
    if isinstance(node, tuple):
        pos[node] = node
    elif node == "super_source":
        pos[node] = (size/2, -1)
    else:
        pos[node] = (size/2, size+1)

# Group nodes for color-coding
super_nodes = ["super_source", "super_sink"]
source_nodes = sources
shelter_nodes = shelters
regular_nodes = [n for n in G.nodes if n not in super_nodes + source_nodes + shelter_nodes]

plt.figure(figsize=(10, 10))

# Draw nodes
nx.draw_networkx_nodes(G, pos, nodelist=regular_nodes, node_color="lightblue", node_size=700)
nx.draw_networkx_nodes(G, pos, nodelist=source_nodes, node_color="lightgreen", node_size=700)
nx.draw_networkx_nodes(G, pos, nodelist=shelter_nodes, node_color="lightcoral", node_size=700)
nx.draw_networkx_nodes(G, pos, nodelist=super_nodes, node_color="gold", node_size=2500) 

# Draw background grid edges (faded out)
nx.draw_networkx_edges(G, pos, edge_color="whitesmoke", arrows=False)

# Highlight Dijkstra's Shortest Path edges in blue
nx.draw_networkx_edges(
    G,
    pos,
    edgelist=dijkstra_edges,
    edge_color="blue",
    width=3.5,            # Made slightly thicker to stand out
    arrows=True,
    arrowsize=18,
    connectionstyle="arc3,rad=0.15"  # Curves arrows to prevent overlap
)

# Draw the text labels
nx.draw_networkx_labels(G, pos, font_size=8, font_weight="bold")

plt.title("Fastest Evacuation Route (Dijkstra's Algorithm)", fontsize=14, fontweight="bold")
plt.axis("off")
plt.tight_layout()
plt.show()