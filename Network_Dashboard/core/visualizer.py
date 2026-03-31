import plotly.graph_objects as go
import networkx as nx

def get_node_color(node_type):
    if node_type == "source": return "red"
    if node_type == "shelter": return "lime"
    if node_type == "super": return "rgba(0,0,0,0)"
    return "lightblue"

def get_edge_color(flow, capacity):
    if flow == 0: return "#444"
    ratio = flow / capacity
    if ratio < 0.8: return "green"
    if ratio <= 1.0: return "yellow"
    return "red"

def plot_animated_network(G):
    pos = {node: tuple(map(int, node.split(','))) for node in G.nodes() if node not in ["S", "T"]}
    
    # 1. Base Node Trace
    node_x, node_y, node_colors = [], [], []
    for node in pos:
        node_x.append(pos[node][0])
        node_y.append(pos[node][1])
        node_colors.append(get_node_color(G.nodes[node].get("type", "regular")))

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode='markers', hoverinfo='text',
        text=[f"Node: {n}" for n in pos],
        marker=dict(color=node_colors, size=10, line=dict(color="white", width=1))
    )

    # 2. Base Edge Trace (Gray lines)
    edge_x, edge_y = [], []
    for u, v in G.edges():
        if u in pos and v in pos:
            edge_x.extend([pos[u][0], pos[v][0], None])
            edge_y.extend([pos[u][1], pos[v][1], None])

    base_edge_trace = go.Scatter(
        x=edge_x, y=edge_y, mode='lines', line=dict(width=1, color='#444'), hoverinfo='none'
    )

    # 3. Calculate Flow Lines for Animation Frame
    green_x, green_y, yellow_x, yellow_y, red_x, red_y = [], [], [], [], [], []
    
    for u, v, data in G.edges(data=True):
        if u in pos and v in pos and data.get('flow', 0) > 0:
            color = get_edge_color(data['flow'], data.get('capacity', 1)) # Default capacity to 1 to avoid /0
            if color == "green":
                green_x.extend([pos[u][0], pos[v][0], None])
                green_y.extend([pos[u][1], pos[v][1], None])
            elif color == "yellow":
                yellow_x.extend([pos[u][0], pos[v][0], None])
                yellow_y.extend([pos[u][1], pos[v][1], None])
            elif color == "red":
                red_x.extend([pos[u][0], pos[v][0], None])
                red_y.extend([pos[u][1], pos[v][1], None])

    # -- THE FIX: Create empty traces for the base figure --
    empty_green = go.Scatter(x=[], y=[], mode='lines', line=dict(width=3, color="green"), hoverinfo='none')
    empty_yellow = go.Scatter(x=[], y=[], mode='lines', line=dict(width=3, color="yellow"), hoverinfo='none')
    empty_red = go.Scatter(x=[], y=[], mode='lines', line=dict(width=3, color="red"), hoverinfo='none')

    # -- Populated traces for the final animation frame --
    frame_green = go.Scatter(x=green_x, y=green_y, mode='lines', line=dict(width=3, color="green"))
    frame_yellow = go.Scatter(x=yellow_x, y=yellow_y, mode='lines', line=dict(width=3, color="yellow"))
    frame_red = go.Scatter(x=red_x, y=red_y, mode='lines', line=dict(width=3, color="red"))

    # 4. Assemble Figure (Ensure data array and frame array match 1-to-1)
    fig = go.Figure(
        # Base state: 5 layers (Gray, Empty Green, Empty Yellow, Empty Red, Nodes)
        data=[base_edge_trace, empty_green, empty_yellow, empty_red, node_trace], 
        layout=go.Layout(
            showlegend=False,
            margin=dict(b=0, l=0, r=0, t=0),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            updatemenus=[dict(
                type="buttons",
                buttons=[dict(label="▶ Play Routing Animation",
                              method="animate",
                              args=[None, {"frame": {"duration": 1000, "redraw": False}, "transition": {"duration": 500}}])]
            )]
        ),
        # Frame state: 5 layers (Gray, Filled Green, Filled Yellow, Filled Red, Nodes)
        frames=[go.Frame(data=[base_edge_trace, frame_green, frame_yellow, frame_red, node_trace])] 
    )
    
    return fig