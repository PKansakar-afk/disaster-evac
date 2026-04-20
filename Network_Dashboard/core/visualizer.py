import plotly.graph_objects as go
import networkx as nx


# ─────────────────────────────────────────────────────────────────────────────
#  Colour helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_node_color(node_type, shelter_remaining=None, shelter_capacity=None):
    if node_type == "source":
        return "red"
    if node_type == "shelter":
        if shelter_remaining is not None and shelter_capacity:
            ratio = shelter_remaining / shelter_capacity
            if ratio == 0:   return "red"
            if ratio <= 0.3: return "orange"
            return "lime"
        return "lime"
    if node_type == "super":
        return "rgba(0,0,0,0)"
    return "lightblue"


def get_edge_color(flow, capacity):
    if flow == 0: return "#444"
    ratio = flow / capacity
    if ratio < 0.8:  return "green"
    if ratio <= 1.0: return "yellow"
    return "red"


# ─────────────────────────────────────────────────────────────────────────────
#  Shared layout builder
# ─────────────────────────────────────────────────────────────────────────────

def _base_layout(extra_annotations=None):
    return go.Layout(
        showlegend=False,
        margin=dict(b=0, l=0, r=0, t=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        annotations=extra_annotations or [],
        font=dict(color="black", size=14),
        updatemenus=[dict(
            type="buttons",
            buttons=[dict(
                label="▶ Play Routing Animation",
                method="animate",
                args=[None, {"frame": {"duration": 1000, "redraw": False},
                             "transition": {"duration": 500}}]
            )]
        )],
    )


def _geo_layout(extra_annotations=None):
    """Like _base_layout but locks aspect ratio for geographic (lon/lat) coords."""
    layout = _base_layout(extra_annotations)
    layout.yaxis.update(scaleanchor="x", scaleratio=1)
    return layout


# ─────────────────────────────────────────────────────────────────────────────
#  Grid network helpers  (pos keys are parsed node-name strings)
# ─────────────────────────────────────────────────────────────────────────────

def _node_trace(G, pos):
    node_x, node_y, node_colors, node_text = [], [], [], []
    for node in pos:
        node_x.append(pos[node][0])
        node_y.append(pos[node][1])
        data      = G.nodes[node]
        ntype     = data.get("type", "regular")
        remaining = data.get("shelter_remaining", None)
        capacity  = data.get("shelter_capacity",  None)
        node_colors.append(get_node_color(ntype, remaining, capacity))
        if ntype == "shelter" and capacity:
            used = capacity - (remaining or capacity)
            node_text.append(f"Shelter {node}<br>{used:,}/{capacity:,} used")
        elif ntype == "source":
            node_text.append(f"Hazard Zone {node}")
        else:
            node_text.append(f"Node {node}")
    return go.Scatter(
        x=node_x, y=node_y, mode="markers", hoverinfo="text",
        text=node_text,
        marker=dict(color=node_colors, size=10, line=dict(color="white", width=1)),
    )


def _base_edge_trace(G, pos):
    ex, ey = [], []
    for u, v in G.edges():
        if u in pos and v in pos:
            ex.extend([pos[u][0], pos[v][0], None])
            ey.extend([pos[u][1], pos[v][1], None])
    return go.Scatter(x=ex, y=ey, mode="lines",
                      line=dict(width=1, color="#444"), hoverinfo="none")


def _grid_edge_hover_trace(G, pos):
    """
    Invisible midpoint markers on every grid edge carrying capacity/flow info.
    When two directed edges share the same midpoint (u→v and v→u), only the
    one with higher flow is shown so you always see the active direction.
    """
    midpoint_best = {}  # (mx, my) → best data dict

    for u, v, data in G.edges(data=True):
        if u not in pos or v not in pos:
            continue
        ux, uy = pos[u]
        vx, vy = pos[v]
        key  = (round((ux + vx) / 2, 4), round((uy + vy) / 2, 4))
        flow = data.get("flow", 0)

        if key not in midpoint_best or flow > midpoint_best[key]["flow"]:
            midpoint_best[key] = {
                "u":      u,
                "v":      v,
                "flow":   flow,
                "cap":    data.get("capacity", 0),
                "weight": data.get("weight",   0),
            }

    mx, my, texts = [], [], []
    for (x, y), d in midpoint_best.items():
        mx.append(x)
        my.append(y)
        cap    = d["cap"]
        flow   = d["flow"]
        weight = d["weight"]
        ratio  = flow / cap if cap > 0 else 0
        status = ("🔴 Over capacity"   if ratio > 1
                  else "🟡 Near capacity" if ratio >= 0.8
                  else "🟢 Free flowing"  if flow > 0
                  else "⚪ No flow")
        texts.append(
            f"<b>{d['u']} → {d['v']}</b><br>"
            f"Capacity     : {cap} veh<br>"
            f"Flow         : {flow} veh<br>"
            f"Utilisation  : {ratio*100:.0f}%<br>"
            f"Travel weight: {weight}<br>"
            f"{status}"
        )

    return go.Scatter(
        x=mx, y=my,
        mode="markers",
        marker=dict(size=8, color="rgba(0,0,0,0)"),
        hoverinfo="text",
        text=texts,
        hoverlabel=dict(bgcolor="#1e1e2e", font_color="white", font_size=12),
        name="Edge info",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Grid network plots
# ─────────────────────────────────────────────────────────────────────────────

def plot_animated_network(G):
    pos = {n: tuple(map(int, n.split(",")))
           for n in G.nodes() if n not in ("S", "T")}

    node_tr    = _node_trace(G, pos)
    base_edge  = _base_edge_trace(G, pos)
    edge_hover = _grid_edge_hover_trace(G, pos)

    gx, gy, yx, yy, rx, ry = [], [], [], [], [], []
    for u, v, data in G.edges(data=True):
        if u in pos and v in pos and data.get("flow", 0) > 0:
            color = get_edge_color(data["flow"], data.get("capacity", 1))
            if color == "green":
                gx.extend([pos[u][0], pos[v][0], None])
                gy.extend([pos[u][1], pos[v][1], None])
            elif color == "yellow":
                yx.extend([pos[u][0], pos[v][0], None])
                yy.extend([pos[u][1], pos[v][1], None])
            elif color == "red":
                rx.extend([pos[u][0], pos[v][0], None])
                ry.extend([pos[u][1], pos[v][1], None])

    mk       = lambda c: dict(width=3, color=c)
    empty_g  = go.Scatter(x=[], y=[], mode="lines", line=mk("green"),  hoverinfo="none")
    empty_y  = go.Scatter(x=[], y=[], mode="lines", line=mk("yellow"), hoverinfo="none")
    empty_r  = go.Scatter(x=[], y=[], mode="lines", line=mk("red"),    hoverinfo="none")
    frame_g  = go.Scatter(x=gx, y=gy, mode="lines", line=mk("green"))
    frame_y  = go.Scatter(x=yx, y=yy, mode="lines", line=mk("yellow"))
    frame_r  = go.Scatter(x=rx, y=ry, mode="lines", line=mk("red"))

    fig = go.Figure(
        data=[base_edge, empty_g, empty_y, empty_r, node_tr, edge_hover],
        layout=_base_layout(),
        frames=[go.Frame(data=[base_edge, frame_g, frame_y, frame_r, node_tr, edge_hover])],
    )
    return fig


def plot_filtered_network(G, selected_route: dict):
    """
    Render the network highlighting only the edges in *selected_route*.
    """
    pos = {n: tuple(map(int, n.split(",")))
           for n in G.nodes() if n not in ("S", "T")}

    path_nodes = selected_route.get("path", [])
    path_edges = set()
    for i in range(len(path_nodes) - 1):
        path_edges.add((path_nodes[i], path_nodes[i + 1]))

    start_node = selected_route.get("start")
    end_node   = selected_route.get("end")

    # 1. Background: zero-flow edges (very dim)
    bg_x, bg_y = [], []
    for u, v, data in G.edges(data=True):
        if u in pos and v in pos and data.get("flow", 0) == 0:
            bg_x.extend([pos[u][0], pos[v][0], None])
            bg_y.extend([pos[u][1], pos[v][1], None])

    bg_trace = go.Scatter(x=bg_x, y=bg_y, mode="lines",
                          line=dict(width=1, color="#2a2a2a"), hoverinfo="none")

    # 2. Other active-flow edges (dim)
    dim_x, dim_y = [], []
    for u, v, data in G.edges(data=True):
        if u in pos and v in pos:
            if data.get("flow", 0) > 0 and (u, v) not in path_edges:
                dim_x.extend([pos[u][0], pos[v][0], None])
                dim_y.extend([pos[u][1], pos[v][1], None])

    dim_trace = go.Scatter(x=dim_x, y=dim_y, mode="lines",
                           line=dict(width=1, color="#555555"), hoverinfo="none")

    # 3. Selected route edges — bright cyan
    sel_x, sel_y = [], []
    for u, v in path_edges:
        if u in pos and v in pos:
            sel_x.extend([pos[u][0], pos[v][0], None])
            sel_y.extend([pos[u][1], pos[v][1], None])

    empty_sel = go.Scatter(x=[], y=[], mode="lines",
                           line=dict(width=5, color="#00e5ff"), hoverinfo="none")
    frame_sel = go.Scatter(x=sel_x, y=sel_y, mode="lines",
                           line=dict(width=5, color="#00e5ff"),
                           hoverinfo="none", name="Selected route")

    # Node trace with custom colours for start/end
    node_x, node_y, node_colors, node_sizes, node_text = [], [], [], [], []
    for node in pos:
        node_x.append(pos[node][0])
        node_y.append(pos[node][1])
        data      = G.nodes[node]
        ntype     = data.get("type", "regular")
        remaining = data.get("shelter_remaining", None)
        capacity  = data.get("shelter_capacity",  None)

        if node == start_node:
            node_colors.append("#ff1744")
            node_sizes.append(16)
            node_text.append(f"🚨 Hazard Zone {node} (route start)")
        elif node == end_node:
            node_colors.append("#00e676")
            node_sizes.append(16)
            if capacity:
                used = capacity - (remaining or capacity)
                node_text.append(f"🏥 Shelter {node} (route end)<br>{used:,}/{capacity:,} used")
            else:
                node_text.append(f"🏥 Shelter {node} (route end)")
        elif node in path_nodes:
            node_colors.append("#00e5ff")
            node_sizes.append(12)
            node_text.append(f"↔ {node} (on route)")
        else:
            node_colors.append(get_node_color(ntype, remaining, capacity))
            node_sizes.append(8)
            if ntype == "shelter" and capacity:
                used = capacity - (remaining or capacity)
                node_text.append(f"Shelter {node}<br>{used:,}/{capacity:,} used")
            elif ntype == "source":
                node_text.append(f"Hazard Zone {node}")
            else:
                node_text.append(f"Node {node}")

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers", hoverinfo="text",
        text=node_text,
        marker=dict(
            color=node_colors, size=node_sizes,
            line=dict(color="white", width=1),
            opacity=[1.0 if n in path_nodes or G.nodes[n].get("type") in ("source", "shelter")
                     else 0.35 for n in pos],
        ),
    )

    # Arrow annotations along selected path
    annotations = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        if u in pos and v in pos:
            annotations.append(dict(
                x=pos[v][0], y=pos[v][1],
                ax=pos[u][0], ay=pos[u][1],
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True,
                arrowhead=3, arrowsize=1.5, arrowwidth=2,
                arrowcolor="#00e5ff",
            ))

    edge_hover = _grid_edge_hover_trace(G, pos)

    fig = go.Figure(
        data=[bg_trace, dim_trace, empty_sel, node_trace, edge_hover],
        layout=_base_layout(extra_annotations=annotations),
        frames=[go.Frame(data=[bg_trace, dim_trace, frame_sel, node_trace, edge_hover])],
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
#  OSM network helpers  (node_pos dict passed in separately)
# ─────────────────────────────────────────────────────────────────────────────

def _osm_node_trace(G, node_pos):
    xs, ys, colors, text = [], [], [], []
    for node, (x, y) in node_pos.items():
        xs.append(x)
        ys.append(y)
        data      = G.nodes[node]
        ntype     = data.get("type", "regular")
        remaining = data.get("shelter_remaining", None)
        capacity  = data.get("shelter_capacity",  None)
        colors.append(get_node_color(ntype, remaining, capacity))
        if ntype == "shelter" and capacity:
            used = capacity - (remaining or capacity)
            text.append(f"Shelter {node}<br>{used:,}/{capacity:,} used")
        elif ntype == "source":
            text.append(f"🚨 Hazard Zone {node}")
        else:
            text.append(f"Node {node}")
    return go.Scatter(
        x=xs, y=ys, mode="markers", hoverinfo="text", text=text,
        marker=dict(color=colors, size=8, line=dict(color="white", width=1)),
    )


def _osm_edge_hover_trace(G, node_pos):
    """
    Invisible midpoint markers for OSM edges.
    When two directed edges share the same midpoint (u→v and v→u), only the
    one with higher flow is shown so you always see the active direction.
    """
    midpoint_best = {}  # (mx, my) → best data dict

    for u, v, data in G.edges(data=True):
        if u not in node_pos or v not in node_pos:
            continue
        ux, uy = node_pos[u]
        vx, vy = node_pos[v]
        key  = (round((ux + vx) / 2, 6), round((uy + vy) / 2, 6))
        flow = data.get("flow", 0)

        if key not in midpoint_best or flow > midpoint_best[key]["flow"]:
            midpoint_best[key] = {
                "u":      u,
                "v":      v,
                "flow":   flow,
                "cap":    data.get("capacity", 0),
                "weight": data.get("weight",   0),
            }

    mx, my, texts = [], [], []
    for (x, y), d in midpoint_best.items():
        mx.append(x)
        my.append(y)
        cap    = d["cap"]
        flow   = d["flow"]
        weight = d["weight"]
        ratio  = flow / cap if cap > 0 else 0
        status = ("🔴 Over capacity"   if ratio > 1
                  else "🟡 Near capacity" if ratio >= 0.8
                  else "🟢 Free flowing"  if flow > 0
                  else "⚪ No flow")
        texts.append(
            f"<b>Road Segment</b><br>"
            f"Capacity     : {cap} veh<br>"
            f"Flow         : {flow} veh<br>"
            f"Utilisation  : {ratio*100:.0f}%<br>"
            f"Travel weight: {weight}<br>"
            f"{status}"
        )

    return go.Scatter(
        x=mx, y=my,
        mode="markers",
        marker=dict(size=8, color="rgba(0,0,0,0)"),
        hoverinfo="text",
        text=texts,
        hoverlabel=dict(bgcolor="#1e1e2e", font_color="white", font_size=12),
        name="Edge info",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  OSM network plots
# ─────────────────────────────────────────────────────────────────────────────

def plot_osm_network(G, node_pos):
    """Full animated OSM network."""
    base_ex, base_ey = [], []
    gx, gy, yx, yy, rx, ry = [], [], [], [], [], []

    for u, v, data in G.edges(data=True):
        if u not in node_pos or v not in node_pos:
            continue
        ux, uy = node_pos[u]
        vx, vy = node_pos[v]
        base_ex.extend([ux, vx, None])
        base_ey.extend([uy, vy, None])
        flow = data.get("flow", 0)
        if flow > 0:
            color = get_edge_color(flow, data.get("capacity", 1))
            if color == "green":
                gx.extend([ux, vx, None]); gy.extend([uy, vy, None])
            elif color == "yellow":
                yx.extend([ux, vx, None]); yy.extend([uy, vy, None])
            elif color == "red":
                rx.extend([ux, vx, None]); ry.extend([uy, vy, None])

    base_tr = go.Scatter(x=base_ex, y=base_ey, mode="lines",
                         line=dict(width=1, color="#444"), hoverinfo="none")
    mk      = lambda c: dict(width=3, color=c)
    empty_g = go.Scatter(x=[], y=[], mode="lines", line=mk("green"),  hoverinfo="none")
    empty_y = go.Scatter(x=[], y=[], mode="lines", line=mk("yellow"), hoverinfo="none")
    empty_r = go.Scatter(x=[], y=[], mode="lines", line=mk("red"),    hoverinfo="none")
    frame_g = go.Scatter(x=gx, y=gy, mode="lines", line=mk("green"))
    frame_y = go.Scatter(x=yx, y=yy, mode="lines", line=mk("yellow"))
    frame_r = go.Scatter(x=rx, y=ry, mode="lines", line=mk("red"))
    node_tr    = _osm_node_trace(G, node_pos)
    edge_hover = _osm_edge_hover_trace(G, node_pos)

    return go.Figure(
        data=[base_tr, empty_g, empty_y, empty_r, node_tr, edge_hover],
        layout=_geo_layout(),
        frames=[go.Frame(data=[base_tr, frame_g, frame_y, frame_r, node_tr, edge_hover])],
    )


def plot_osm_filtered(G, node_pos, selected_route: dict):
    """Single-route highlight on OSM graph."""
    path_nodes = selected_route.get("path", [])
    path_edges = set(zip(path_nodes, path_nodes[1:]))
    start_node = selected_route.get("start")
    end_node   = selected_route.get("end")

    bg_x, bg_y, dim_x, dim_y, sel_x, sel_y = [], [], [], [], [], []

    for u, v, data in G.edges(data=True):
        if u not in node_pos or v not in node_pos:
            continue
        ux, uy = node_pos[u]
        vx, vy = node_pos[v]
        if (u, v) in path_edges:
            sel_x.extend([ux, vx, None]); sel_y.extend([uy, vy, None])
        elif data.get("flow", 0) > 0:
            dim_x.extend([ux, vx, None]); dim_y.extend([uy, vy, None])
        else:
            bg_x.extend([ux, vx, None]); bg_y.extend([uy, vy, None])

    bg_tr  = go.Scatter(x=bg_x,  y=bg_y,  mode="lines",
                        line=dict(width=1, color="#2a2a2a"), hoverinfo="none")
    dim_tr = go.Scatter(x=dim_x, y=dim_y, mode="lines",
                        line=dict(width=1, color="#555"),    hoverinfo="none")
    emp_s  = go.Scatter(x=[],    y=[],    mode="lines",
                        line=dict(width=4, color="#00e5ff"), hoverinfo="none")
    frm_s  = go.Scatter(x=sel_x, y=sel_y, mode="lines",
                        line=dict(width=4, color="#00e5ff"), name="Route")

    # Node colours
    nxs, nys, nc, nsz, nt, opacities = [], [], [], [], [], []
    for node, (x, y) in node_pos.items():
        nxs.append(x); nys.append(y)
        data      = G.nodes[node]
        ntype     = data.get("type", "regular")
        remaining = data.get("shelter_remaining", None)
        capacity  = data.get("shelter_capacity",  None)

        if node == start_node:
            nc.append("#ff1744"); nsz.append(14)
            nt.append("🚨 Hazard Zone (route start)")
            opacities.append(1.0)
        elif node == end_node:
            nc.append("#00e676"); nsz.append(14)
            used = (capacity or 0) - (remaining or capacity or 0)
            nt.append(f"🏥 Shelter (route end) {used}/{capacity}")
            opacities.append(1.0)
        elif node in path_nodes:
            nc.append("#00e5ff"); nsz.append(10)
            nt.append(f"↔ on route")
            opacities.append(1.0)
        else:
            nc.append(get_node_color(ntype, remaining, capacity))
            nsz.append(6)
            nt.append(f"Node {node}")
            opacities.append(0.25)

    node_tr = go.Scatter(
        x=nxs, y=nys, mode="markers", hoverinfo="text", text=nt,
        marker=dict(color=nc, size=nsz, opacity=opacities,
                    line=dict(color="white", width=1)),
    )

    # Arrow annotations along selected path
    annotations = []
    for u, v in path_edges:
        if u in node_pos and v in node_pos:
            ux, uy = node_pos[u]
            vx, vy = node_pos[v]
            annotations.append(dict(
                x=vx, y=vy, ax=ux, ay=uy,
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=3, arrowsize=1.5,
                arrowwidth=2, arrowcolor="#00e5ff",
            ))

    edge_hover = _osm_edge_hover_trace(G, node_pos)

    return go.Figure(
        data=[bg_tr, dim_tr, emp_s, node_tr, edge_hover],
        layout=_geo_layout(extra_annotations=annotations),
        frames=[go.Frame(data=[bg_tr, dim_tr, frm_s, node_tr, edge_hover])],
    )