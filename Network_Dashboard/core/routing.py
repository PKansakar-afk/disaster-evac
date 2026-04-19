import networkx as nx
import math

def run_routing(G, algorithm_name, population):
    metrics = {"throughput": 0, "makespan": 0, "max_congestion": 0}
    
    # Identify sources for population distribution
    sources = [n for n, d in G.nodes(data=True) if d.get('type') == 'source']
    pop_per_source = math.ceil(population / len(sources)) if sources else 0

    if algorithm_name == "Dijkstra":
        # Build a residual capacity tracker
        # We need to track how much capacity each edge has LEFT as we route
        # batches of evacuees through it. We store this separately so we can
        # subtract from it without permanently modifying the graph.
        remaining_edge_cap = {
            (u, v): data.get('capacity', 0)
            for u, v, data in G.edges(data=True)
        }

        # Track how much space each shelter still has
        remaining_shelter_cap = {
            node: data.get('shelter_capacity', 999999)
            for node, data in G.nodes(data=True)
            if data.get('type') == 'shelter'
        }

        total_evacuees_safe     = 0
        total_evacuees_stranded = 0
        max_cong                = 0
        total_weighted_time     = 0   # for avg travel time = sum(flow * path_time)

        for source in sources:
            remaining_at_source = pop_per_source

            while remaining_at_source > 0:

                # Step 1: Build a view of the graph that only includes edges that still have remaining capacity
                feasible_G = nx.DiGraph()
                for u, v, data in G.edges(data=True):
                    if remaining_edge_cap.get((u, v), 0) > 0:
                        feasible_G.add_edge(u, v, weight=data.get('weight', 1))

                # Step 2: Only route toward shelters that still have room
                reachable_shelters = [
                    s for s in remaining_shelter_cap
                    if remaining_shelter_cap[s] > 0
                ]
                if not reachable_shelters:
                    # No shelter has space — everyone remaining is stranded
                    total_evacuees_stranded += remaining_at_source
                    break

                # Step 3: Find shortest path from this source to the super-sink T, but only over feasible edges
                try:
                    path = nx.shortest_path(feasible_G, source, "T", weight="weight")
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    # No feasible path exists anymore — evacuees are stranded
                    total_evacuees_stranded += remaining_at_source
                    remaining_at_source = 0
                    break

                # Step 4: Find the bottleneck — the tightest constraint along this specific path
                # This is the min of:
                #   a) how many people are still waiting at this source
                #   b) the minimum remaining edge capacity along the path
                #   c) how much space the destination shelter has left

                # The destination shelter is the node just before "T" in path
                dest_shelter = path[-2]  # path looks like [source, ..., shelter, T]

                edge_bottleneck = min(
                    remaining_edge_cap.get((path[i], path[i+1]), 0)
                    for i in range(len(path) - 1)
                )
                shelter_bottleneck = remaining_shelter_cap.get(dest_shelter, 0)

                batch_size = min(remaining_at_source, edge_bottleneck, shelter_bottleneck)

                if batch_size <= 0:
                    # This path is completely blocked — stranded
                    total_evacuees_stranded += remaining_at_source
                    break

                # Step 5: Move this batch along the path
                path_travel_time = 0
                for i in range(len(path) - 1):
                    u, v = path[i], path[i+1]
                    G[u][v]['flow']             = G[u][v].get('flow', 0) + batch_size
                    remaining_edge_cap[(u, v)] -= batch_size

                    # Accumulate travel time for this path (skip S and T edges)
                    if u != 'S' and v != 'T':
                        path_travel_time += G[u][v].get('weight', 0)

                # Update shelter remaining space
                remaining_shelter_cap[dest_shelter]          -= batch_size
                remaining_edge_cap[(dest_shelter, "T")]      -= batch_size

                # Accumulate metrics
                total_evacuees_safe     += batch_size
                remaining_at_source     -= batch_size
                total_weighted_time     += batch_size * path_travel_time

                # Track congestion: worst ratio seen across all edges used
                for i in range(len(path) - 1):
                    u, v = path[i], path[i+1]
                    cap = G[u][v].get('capacity', 1)
                    if cap > 0 and u != 'S' and v != 'T':
                        cong = G[u][v]['flow'] / cap
                        max_cong = max(max_cong, cong)

        # Compute final metrics
        pct_evacuated = round(100 * total_evacuees_safe / population, 1) if population > 0 else 0
        avg_tt        = round(total_weighted_time / total_evacuees_safe, 2) if total_evacuees_safe > 0 else 0

        # Makespan: worst-case path time, scaled by congestion on each edge
        # (congested edges slow everyone down proportionally)
        max_path_time = 0
        for source in sources:
            try:
                path = nx.shortest_path(G, source, "T", weight="weight")
                t = sum(
                    G[path[i]][path[i+1]]['weight']
                    * max(1, G[path[i]][path[i+1]]['flow']
                            / max(G[path[i]][path[i+1]].get('capacity', 1), 1))
                    for i in range(len(path) - 1)
                    if path[i] != 'S' and path[i+1] != 'T'
                )
                max_path_time = max(max_path_time, t)
            except Exception:
                pass

        metrics["max_congestion"]       = round(max_cong, 2)
        metrics["makespan"]             = round(max_path_time, 2) if max_path_time > 0 else round(population / max(total_evacuees_safe, 1), 2)
        metrics["throughput"]           = round(total_evacuees_safe / max(max_path_time, 1), 2)
        metrics["avg_travel_time"]      = avg_tt
        metrics["evacuees_safe"]        = int(total_evacuees_safe)
        metrics["evacuees_stranded"]    = int(total_evacuees_stranded)
        metrics["pct_evacuated"]        = pct_evacuated
        metrics["feasible"]             = (total_evacuees_stranded == 0)
        
    elif algorithm_name == "Max Flow (Edmonds-Karp)":
        flow_value, flow_dict = nx.maximum_flow(
            G, "S", "T",
            capacity='capacity',
            flow_func=nx.algorithms.flow.edmonds_karp
        )

        max_cong    = 0
        total_cost  = 0

        for u in flow_dict:
            for v in flow_dict[u]:
                if G.has_edge(u, v):
                    f = flow_dict[u][v]
                    G[u][v]['flow'] = f
                    if G[u][v].get('capacity', 1) > 0 and u != 'S' and v != 'T':
                        max_cong   = max(max_cong, f / G[u][v]['capacity'])
                        total_cost += f * G[u][v]['weight']

        # compare what the network moved vs what was demanded
        # flow_value is naturally capped by shelter capacity (now finite).
        # If flow_value < population, the network could not evacuate everyone.
        evacuees_safe     = min(flow_value, population)
        evacuees_stranded = max(0, population - evacuees_safe)
        pct_evacuated     = round(100 * evacuees_safe / population, 1) if population > 0 else 0

        throughput = flow_value
        # metrics
        metrics["throughput"]           = round(throughput, 2)
        metrics["makespan"]             = round(population / throughput, 2) if throughput > 0 else float('inf')
        metrics["max_congestion"]       = round(max_cong, 2)
        metrics["avg_travel_time"]      = round(total_cost / throughput, 2) if throughput > 0 else 0
        metrics["evacuees_safe"]        = int(evacuees_safe)
        metrics["evacuees_stranded"]    = int(evacuees_stranded)
        metrics["pct_evacuated"]        = pct_evacuated
        metrics["feasible"]             = (evacuees_stranded == 0)

    elif algorithm_name == "MCMF":
        flow_dict = nx.max_flow_min_cost(
            G, "S", "T",
            capacity='capacity',
            weight='weight'
        )

        throughput = sum(flow_dict[u]["T"] for u in flow_dict if "T" in flow_dict[u])

        max_cong   = 0
        total_cost = 0
        for u in flow_dict:
            for v in flow_dict[u]:
                if G.has_edge(u, v):
                    f = flow_dict[u][v]
                    G[u][v]['flow'] = f
                    if G[u][v].get('capacity', 1) > 0 and u != 'S' and v != 'T':
                        max_cong   = max(max_cong, f / G[u][v]['capacity'])
                        total_cost += f * G[u][v]['weight']

        # feasibility check
        # nx.max_flow_min_cost internally calls maximum_flow first, so
        # throughput is already capped by the finite shelter capacities.
        # We just need to check if that cap is enough to clear all evacuees.
        evacuees_safe     = min(throughput, population)
        evacuees_stranded = max(0, population - evacuees_safe)
        pct_evacuated     = round(100 * evacuees_safe / population, 1) if population > 0 else 0

        metrics["throughput"]           = round(throughput, 2)
        metrics["makespan"]             = round(population / throughput, 2) if throughput > 0 else float('inf')
        metrics["max_congestion"]       = round(max_cong, 2)
        metrics["avg_travel_time"]      = round(total_cost / throughput, 2) if throughput > 0 else 0
        # NEW metric keys
        metrics["evacuees_safe"]        = int(evacuees_safe)
        metrics["evacuees_stranded"]    = int(evacuees_stranded)
        metrics["pct_evacuated"]        = pct_evacuated
        metrics["feasible"]             = (evacuees_stranded == 0)

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