import networkx as nx

def run_routing(G, algorithm_name, population):
    metrics = {"throughput": 0, "makespan": 0, "max_congestion": 0}
    
    # Identify sources for population distribution
    sources = [n for n, d in G.nodes(data=True) if d.get('type') == 'source']
    pop_per_source = population / len(sources) if sources else 0

    if algorithm_name == "Dijkstra":
        for source in sources:
            try:
                path = nx.shortest_path(G, source, "T", weight="weight")
                G['S'][source]['flow'] = G['S'][source].get('flow', 0) + pop_per_source
                for i in range(len(path)-1):
                    u, v = path[i], path[i+1]
                    G[u][v]['flow'] = G[u][v].get('flow', 0) + pop_per_source
            except nx.NetworkXNoPath:
                pass
        
        max_cong = 0
        max_path_time = 0
        
        for source in sources:
            try:
                path = nx.shortest_path(G, source, "T", weight="weight")
                current_path_time = 0
                for i in range(len(path)-1):
                    u, v = path[i], path[i+1]
                    edge = G[u][v]
                    if edge.get('capacity', 1) > 0 and u != 'S' and v != 'T':
                        cong = edge['flow'] / edge['capacity']
                        max_cong = max(max_cong, cong)
                        # "Delays are estimated by proportionally scaling travel time based on congestion"
                        current_path_time += edge['weight'] * max(1, cong) 
                max_path_time = max(max_path_time, current_path_time)
            except:
                pass
                
        metrics["max_congestion"] = round(max_cong, 2)
        metrics["makespan"] = round(max_path_time, 2)
        metrics["throughput"] = round(population / max_path_time, 2) if max_path_time > 0 else 0
        metrics["avg_travel_time"] = round(max_path_time, 2)

    elif algorithm_name == "Max Flow (Edmonds-Karp)":
        # NetworkX calculates the max capacity per unit time
        flow_value, flow_dict = nx.maximum_flow(G, "S", "T", capacity='capacity', flow_func=nx.algorithms.flow.edmonds_karp)
        
        max_cong = 0
        total_cost = 0

        for u in flow_dict:
            for v in flow_dict[u]:
                if G.has_edge(u, v):
                    f = flow_dict[u][v]
                    G[u][v]['flow'] = f
                    if G[u][v].get('capacity', 1) > 0 and u != 'S' and v != 'T':
                        max_cong = max(max_cong, G[u][v]['flow'] / G[u][v]['capacity'])
                        total_cost += f * G[u][v]['weight']
        
        throughput = flow_value
        metrics["throughput"] = round(throughput, 2)
        metrics["makespan"] = round(population / throughput, 2) if throughput > 0 else float('inf')
        metrics["max_congestion"] = round(max_cong, 2)
        metrics["avg_travel_time"] = round(total_cost / throughput, 2) if throughput > 0 else 0

    elif algorithm_name == "MCMF":
        flow_dict = nx.max_flow_min_cost(G, "S", "T", capacity='capacity', weight='weight')
        
        throughput = sum(flow_dict[u]["T"] for u in flow_dict if "T" in flow_dict[u])
        
        max_cong = 0
        total_cost = 0
        for u in flow_dict:
            for v in flow_dict[u]:
                if G.has_edge(u, v):
                    f = flow_dict[u][v]
                    G[u][v]['flow'] = f
                    if G[u][v].get('capacity', 1) > 0 and u != 'S' and v != 'T':
                        max_cong = max(max_cong, f / G[u][v]['capacity'])
                        total_cost += f * G[u][v]['weight']
                        
        metrics["throughput"] = round(throughput, 2)
        metrics["makespan"] = round(population / throughput, 2) if throughput > 0 else float('inf')
        metrics["max_congestion"] = round(max_cong, 2)
        metrics["avg_travel_time"] = round(total_cost / throughput, 2) if throughput > 0 else 0

    return G, metrics

def extract_active_routes(G):
    """
    Uses Flow Decomposition to extract discrete paths from a continuous flow network.
    """
    import networkx as nx
    routes = []
    
    # Create a temporary graph of just the edges with active traffic
    flow_G = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        f = data.get('flow', 0)
        if f > 0:
            flow_G.add_edge(u, v, flow=f)
            
    # Trace paths from Super-Source (S) to Super-Sink (T)
    if not flow_G.has_node('S') or not flow_G.has_node('T'):
        return routes
        
    while True:
        try:
            # Find an active path
            path = nx.shortest_path(flow_G, 'S', 'T')
            
            # Find the bottleneck (the maximum number of evacuees that took this exact route)
            path_flow = min(flow_G[path[i]][path[i+1]]['flow'] for i in range(len(path)-1))
            
            if path_flow <= 0:
                break
                
            # Clean up the path for the UI (Remove the invisible 'S' and 'T' nodes)
            clean_path = [n for n in path if n not in ('S', 'T')]
            
            if len(clean_path) > 0:
                routes.append({
                    "start": clean_path[0],
                    "end": clean_path[-1],
                    "path": clean_path,
                    "volume": round(path_flow, 2)
                })
            
            # "Subtract" this group of evacuees from the network
            for i in range(len(path)-1):
                u, v = path[i], path[i+1]
                flow_G[u][v]['flow'] -= path_flow
                # Remove the edge if it's empty so we don't traverse it again
                if flow_G[u][v]['flow'] <= 0.001: 
                    flow_G.remove_edge(u, v)
                    
        except nx.NetworkXNoPath:
            break # No more paths left to extract!
            
    # Sort routes by volume (largest groups first)
    routes.sort(key=lambda x: x['volume'], reverse=True)
    return routes