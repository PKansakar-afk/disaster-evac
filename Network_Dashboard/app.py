import streamlit as st

# Import our backend functions
from core.graph_engine import generate_city_grid
from core.routing import run_routing, extract_active_routes
from core.visualizer import plot_animated_network

st.set_page_config(layout="wide", page_title="Evacuation Routing Simulator")

# --- 1. SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("⚙️ Controls Panel")
    algorithm = st.selectbox("Algorithm", ["Dijkstra", "Max Flow (Edmonds-Karp)", "MCMF"])
    
    st.divider()
    st.subheader("Network Parameters")
    grid_size = st.slider("Grid Size (n x n)", min_value=5, max_value=50, step=5, value=10)
    population = st.number_input("Population Size", min_value=100, max_value=100000, value=1000)
    num_shelters = st.slider("# Shelters", min_value=1, max_value=10, step=1, value=2)
    
    st.divider()
    run_sim = st.button("Run Simulation", type="primary", use_container_width=True)

# --- SESSION STATE (The Memory Fix) ---
# Initialize memory to store the base graph so it doesn't reset randomly
if 'base_graph' not in st.session_state:
    st.session_state.base_graph = None
    st.session_state.sources = None
    st.session_state.shelters = None
    st.session_state.last_params = None

# --- 2. MAIN DASHBOARD AREA ---
st.title("🚨 Evacuation Routing Simulator")

if run_sim:
    st.write(f"Running **{algorithm}**...")
    
    # We only generate a NEW graph if it's the first time OR if you changed the layout parameters
    current_params = (grid_size, num_shelters)
    
    if st.session_state.base_graph is None or st.session_state.last_params != current_params:
        with st.spinner("Generating new city grid..."):
            G, sources, shelters = generate_city_grid(n=grid_size, num_shelters=num_shelters)
            # Save to memory!
            st.session_state.base_graph = G
            st.session_state.sources = sources
            st.session_state.shelters = shelters
            st.session_state.last_params = current_params
    else:
        st.toast("Reusing the same city layout for direct algorithm comparison!")

    # Grab the saved graph and MAKE A COPY so the flow data doesn't permanently overwrite it
    G_working = st.session_state.base_graph.copy()
    sources = st.session_state.sources
    shelters = st.session_state.shelters
    
    st.success(f"✅ City loaded! {len(sources)} Hazard Zones (Red) and {len(shelters)} Shelters (Green).")
    
    # 2. Run the Routing Algorithm on the COPY
    with st.spinner(f"Calculating routes using {algorithm}..."):
        G_routed, metrics = run_routing(G_working, algorithm, population)
    
    # 3. Draw the Animated Map
    st.subheader("🗺️ Live Evacuation Map")
    st.caption("Press 'Play Routing Animation' below the map to see traffic flow.")
    
    fig = plot_animated_network(G_routed)
    st.plotly_chart(fig, use_container_width=True)
    
    # 4. Display Metrics
    st.subheader("📊 Simulation Metrics")
    col1, col2, col3, col4 = st.columns(4) # Changed to 4 columns!
    
    col1.metric("Throughput", f"{metrics.get('throughput', 0)} veh/time")
    col2.metric("Makespan", f"{metrics.get('makespan', 0)} time units")
    
    cong = metrics.get('max_congestion', 0)
    cong_str = f"⚠️ {cong}x Cap" if cong > 1 else f"✅ {cong}x Cap"
    col3.metric("Max Congestion", cong_str)
    
    col4.metric("Avg Travel Time", f"{metrics.get('avg_travel_time', 0)} time units")

    # 5. Display the Turn-by-Turn Routes
    st.divider()
    routes = extract_active_routes(G_routed)
    
    with st.expander(f"📋 View Detailed Routing Logs ({len(routes)} distinct paths found)"):
        if not routes:
            st.info("No active routes found.")
        else:
            for i, route in enumerate(routes):
                # Format the path using arrows
                path_str = " ➔ ".join(str(node) for node in route['path'])
                
                st.markdown(f"**Route {i+1}** (Volume: `{route['volume']}` evacuees)")
                st.write(f"🚦 **Path:** {path_str}")
                st.caption(f"From Hazard {route['start']} to Shelter {route['end']}")
                st.divider()

else:
    st.write("👈 Adjust your parameters in the sidebar and click **Run Simulation** to begin.")