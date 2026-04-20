import streamlit as st
import pandas as pd
import plotly.express as px

# ── Our backend modules ───────────────────────────────────────────────────────
from core.graph_engine import generate_city_grid
from core.routing      import run_routing, extract_active_routes
from core.visualizer   import plot_animated_network
from core.visualizer   import plot_filtered_network
from core.visualizer import plot_osm_network, plot_osm_filtered
from core.experiments  import (
    experiment_generator,
    summarize_results,
    GRID_SIZES, POPULATIONS, SHELTER_COUNTS, ALGORITHMS, NUM_SEEDS,
    TIMEOUT_SEC,
    _scale_sources
)

try:
    from core.osm_engine import load_osm_graph, PRESET_LOCATIONS, OSM_AVAILABLE
except ImportError:
    OSM_AVAILABLE = False
    PRESET_LOCATIONS = {}

st.set_page_config(layout="wide", page_title="Evacuation Routing Simulator")

# ─────────────────────────────────────────────────────────────────────────────
#  SHARED SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
for key, default in [
    ("base_graph",  None),
    ("sources",     None),
    ("shelters",    None),
    ("last_params", None),
    ("exp_results", None),
    ("exp_summary", None),
    ("last_G",      None),
    ("last_metrics", None),
    ("last_routes", None),
    ("osm_G",        None),
    ("osm_sources",  None),
    ("osm_shelters", None),
    ("osm_routes",   None),
    ("osm_metrics",  None),
    ("osm_pos",      None),
    ("osm_base_G",     None),
    ("osm_last_params", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─────────────────────────────────────────────────────────────────────────────
#  TOP-LEVEL TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_sim, tab_exp, tab_osm = st.tabs(["🚨 Simulator", "🔬 Experiments", "🗺️ OSM Real Streets"])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 – SIMULATOR  (original code, unchanged)
# ══════════════════════════════════════════════════════════════════════════════
with tab_sim:

    with st.sidebar:
        st.header("⚙️ Controls Panel")
        algorithm    = st.selectbox("Algorithm", ["Dijkstra", "Max Flow (Edmonds-Karp)", "MCMF"])
        st.divider()
        st.subheader("Network Parameters")
        grid_size    = st.slider("Grid Size (n x n)",   min_value=5,   max_value=50,     step=5,  value=10)
        population   = st.number_input("Population Size", min_value=100, max_value=100000, value=100)
        num_shelters = st.slider("# Shelters",           min_value=1,   max_value=10,     step=1,  value=2)
        st.divider()
        run_sim = st.button("Run Simulation", type="primary", use_container_width=True)

    st.title("🚨 Evacuation Routing Simulator")

    # ══════════════════════════════════════════════════
    # PHASE 1 — COMPUTE (only when button is clicked)
    # ══════════════════════════════════════════════════
    if run_sim:
        st.write(f"Running **{algorithm}**...")
        current_params = (grid_size, num_shelters, population)

        if st.session_state.base_graph is None or st.session_state.last_params != current_params:
            with st.spinner("Generating new city grid..."):
                G, sources, shelters = generate_city_grid(
                    n=grid_size,
                    num_shelters=num_shelters,
                    num_sources=_scale_sources(grid_size),
                    population=population,
                )
                st.session_state.base_graph  = G
                st.session_state.sources     = sources
                st.session_state.shelters    = shelters
                st.session_state.last_params = current_params
        else:
            st.toast("Reusing the same city layout for direct algorithm comparison!")

        G_working = st.session_state.base_graph.copy()

        with st.spinner(f"Calculating routes using {algorithm}..."):
            G_routed, metrics = run_routing(G_working, algorithm, population)

        # Persist everything needed for the display phase
        st.session_state.last_G       = G_routed
        st.session_state.last_metrics = metrics
        st.session_state.last_routes  = extract_active_routes(G_routed)

    # ══════════════════════════════════════════════════
    # PHASE 2 — DISPLAY (survives ALL widget interactions)
    # ══════════════════════════════════════════════════
    if st.session_state.last_G is not None:
        G_routed = st.session_state.last_G
        metrics  = st.session_state.last_metrics
        routes   = st.session_state.last_routes
        sources  = st.session_state.sources
        shelters = st.session_state.shelters

        st.success(f"✅ City loaded! {len(sources)} Hazard Zones (Red) and {len(shelters)} Shelters (Green).")

        # ── Metrics ──────────────────────────────────────────────────────────
        st.subheader("📊 Simulation Metrics")
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Throughput",      f"{metrics.get('throughput', 0)} veh/time")
        col2.metric("Makespan",        f"{metrics.get('makespan', 0)} time units")
        cong     = metrics.get("max_congestion", 0)
        cong_str = f"⚠️ {cong}x Cap" if cong > 1 else f"✅ {cong}x Cap"
        col3.metric("Max Congestion",  cong_str)
        col4.metric("Avg Travel Time", f"{metrics.get('avg_travel_time', 0)} time units")
        pct      = metrics.get("pct_evacuated", 0)
        stranded = int(metrics.get("evacuees_stranded", 0))
        col5.metric("% Evacuated",     f"{'✅' if pct >= 100 else '⚠️'} {pct}%")
        col6.metric("Stranded",        f"{stranded:,} people")

        st.divider()

        # ── Map + Route filter ────────────────────────────────────────────────
        st.subheader("🗺️ Live Evacuation Map")
        map_col, ctrl_col = st.columns([3, 1])

        with ctrl_col:
            st.markdown("#### 🔍 Route Filter")
            st.caption("Isolate a single path for your presentation.")

            if not routes:
                st.info("No active routes to filter.")
                selected_idx = None
            else:
                route_labels = ["— Show all routes —"] + [
                    f"Route {i+1}: {r['start']} ➔ … ➔ {r['end']}  ({r['volume']:.0f} ppl)"
                    for i, r in enumerate(routes)
                ]
                chosen = st.selectbox(
                    "Select route",
                    options=range(len(route_labels)),
                    format_func=lambda i: route_labels[i],
                    key="route_filter_select",
                )
                selected_idx = None if chosen == 0 else chosen - 1

                if selected_idx is not None:
                    r = routes[selected_idx]
                    path_str = " ➔ ".join(str(n) for n in r["path"])
                    st.markdown("**Full path:**")
                    st.code(path_str, language=None)
                    st.metric("Volume", f"{r['volume']:.0f} evacuees")
                    st.metric("Hops",   len(r["path"]) - 1)
                    st.caption(f"From Hazard **{r['start']}** → Shelter **{r['end']}**")
                    if st.button("🖨️ Copy path string", use_container_width=True):
                        st.toast("Path shown in the code block above — select all & copy!")

        with map_col:
            st.caption(
                "Press **▶ Play Routing Animation** below the map to see traffic flow. "
                "Use the filter on the right to isolate one route."
            )
            if selected_idx is None:
                fig = plot_animated_network(G_routed)
            else:
                fig = plot_filtered_network(G_routed, routes[selected_idx])
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ── Routing logs ─────────────────────────────────────────────────────
        with st.expander(f"📋 View Detailed Routing Logs ({len(routes)} distinct paths found)"):
            if not routes:
                st.info("No active routes found.")
            else:
                for i, route in enumerate(routes):
                    path_str   = " ➔ ".join(str(n) for n in route["path"])
                    is_selected = (selected_idx == i)
                    prefix      = "👉 " if is_selected else ""
                    st.markdown(
                        f"{prefix}**Route {i+1}** (Volume: `{route['volume']}` evacuees)"
                        + ("  ← *currently selected*" if is_selected else "")
                    )
                    st.write(f"🚦 **Path:** {path_str}")
                    st.caption(f"From Hazard {route['start']} to Shelter {route['end']}")
                    st.divider()

        # ── Shelter utilization ───────────────────────────────────────────────
        with st.expander("🏥 Shelter Utilization"):
            for shelter in shelters:
                node_data = G_routed.nodes[shelter]
                cap       = node_data.get("shelter_capacity",  0)
                remaining = node_data.get("shelter_remaining", cap)
                used      = cap - remaining
                if cap > 0:
                    fill_pct = used / cap
                    if fill_pct >= 1.0:
                        label = f"🔴 Shelter {shelter}: {used:,}/{cap:,} — FULL"
                    elif fill_pct >= 0.7:
                        label = f"🟡 Shelter {shelter}: {used:,}/{cap:,} ({fill_pct*100:.0f}% full)"
                    else:
                        label = f"🟢 Shelter {shelter}: {used:,}/{cap:,} ({fill_pct*100:.0f}% full)"
                    st.progress(fill_pct, text=label)
                else:
                    st.write(f"Shelter {shelter}: no capacity data")

    else:
        st.write("👈 Adjust your parameters in the sidebar and click **Run Simulation** to begin.")

# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 – EXPERIMENTS
# ══════════════════════════════════════════════════════════════════════════════
with tab_exp:

    st.title("🔬 Full Experiment Suite")
    st.markdown(
        "Run all combinations of grid size × population × shelters × algorithm "
        "with multiple random seeds and compare results across the board."
    )

    # ── 2-A  Experiment configuration ─────────────────────────────────────────
    st.subheader("⚙️ Experiment Configuration")
    cfg_col1, cfg_col2 = st.columns(2)

    with cfg_col1:
        sel_grids  = st.multiselect("Grid Sizes",   GRID_SIZES,     default=GRID_SIZES,
                                    help="Each value is n in an n×n grid.")
        sel_pops   = st.multiselect("Populations",  POPULATIONS,    default=POPULATIONS,
                                    format_func=lambda x: f"{x:,}")
        sel_algos  = st.multiselect("Algorithms",   ALGORITHMS,     default=ALGORITHMS)

    with cfg_col2:
        sel_shelters = st.multiselect("Shelter Counts", SHELTER_COUNTS, default=SHELTER_COUNTS)
        sel_seeds    = st.number_input(
            "Seeds per combination", min_value=1, max_value=NUM_SEEDS, value=NUM_SEEDS,
            help="Reduce to 1–3 for a quick preview run to verify everything works."
        )
        total_planned = (
            len(sel_grids) * len(sel_pops) * len(sel_shelters) * len(sel_algos) * int(sel_seeds)
        )
        st.info(f"⏱ Planned runs: **{total_planned:,}**  (timeout {TIMEOUT_SEC}s each)")

    st.caption(
        "⚠️ 100×100 grids with MCMF and large populations are likely to hit the timeout. "
        "Those rows are kept in the results with status `timeout` so they don't block the rest."
    )

    # ── 2-B  Run button ────────────────────────────────────────────────────────
    run_exp = st.button(
        "🚀 Run Experiments", type="primary",
        disabled=not (sel_grids and sel_pops and sel_shelters and sel_algos),
    )

    if run_exp:
        n_seeds    = int(sel_seeds)
        total_runs = len(sel_grids) * len(sel_pops) * len(sel_shelters) * len(sel_algos) * n_seeds

        progress_bar = st.progress(0.0)
        status_text  = st.empty()
        raw_results  = []

        gen = experiment_generator(
            grid_sizes     = sel_grids,
            populations    = sel_pops,
            shelter_counts = sel_shelters,
            algorithms     = sel_algos,
            num_seeds      = n_seeds,
        )

        for completed, total, result in gen:
            raw_results.append(result)
            progress_bar.progress(completed / total)

            icon = {"success": "✅", "timeout": "⏱️"}.get(result["status"], "❌")
            status_text.markdown(
                f"{icon} `[{completed}/{total}]` "
                f"**{result['algorithm']}** | "
                f"Grid {result['grid_size']} | "
                f"Pop {result['population']:,} | "
                f"Shelters {result['num_shelters']} | "
                f"Seed {result['seed']}  →  `{result['status']}`"
            )

        progress_bar.progress(1.0)
        status_text.success(f"✅ All {total_runs:,} experiments complete!")

        df_raw     = pd.DataFrame(raw_results)
        df_summary = summarize_results(df_raw)

        st.session_state.exp_results = df_raw
        st.session_state.exp_summary = df_summary

    # ── 2-C  Results (persists across re-renders via session state) ────────────
    if st.session_state.exp_results is not None:
        df_raw     = st.session_state.exp_results
        df_summary = st.session_state.exp_summary

        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Runs",     len(df_raw))
        m2.metric("✅ Successful",  (df_raw["status"] == "success").sum())
        m3.metric("⏱️ Timed Out",   (df_raw["status"] == "timeout").sum())
        m4.metric("❌ Errors",      df_raw["status"].str.startswith("error").sum())

        # ── Summary table ──────────────────────────────────────────────────────
        st.subheader("📋 Aggregated Results  (mean ± std across seeds)")
        if not df_summary.empty:
            st.dataframe(df_summary, use_container_width=True)
        else:
            st.warning("No successful runs to summarize.")

        # ── CSV downloads ──────────────────────────────────────────────────────
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "⬇️ Download Raw Results (CSV)",
                df_raw.to_csv(index=False).encode(),
                "evacuation_raw_results.csv", "text/csv",
            )
        with dl2:
            if not df_summary.empty:
                st.download_button(
                    "⬇️ Download Summary (CSV)",
                    df_summary.to_csv(index=False).encode(),
                    "evacuation_summary.csv", "text/csv",
                )

        # ── Charts ─────────────────────────────────────────────────────────────
        st.divider()
        st.subheader("📊 Comparison Charts")

        df_ok = df_raw[df_raw["status"] == "success"].copy()

        if df_ok.empty:
            st.warning("No successful results to chart.")
        else:
            # Chart filter controls
            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                chart_pop = st.selectbox(
                    "Fix Population (for grid-size charts)",
                    sorted(df_ok["population"].unique()), index=0,
                )
            with chart_col2:
                chart_shelters = st.selectbox(
                    "Fix Shelter Count (for grid-size charts)",
                    sorted(df_ok["num_shelters"].unique()), index=0,
                )

            # Mean across seeds for each combination
            group_cols = ["grid_size", "nodes", "population", "num_shelters", "algorithm"]
            agg = (
                df_ok.groupby(group_cols)[
                    ["throughput", "makespan", "max_congestion",
                    "avg_travel_time", "runtime_sec",
                    "pct_evacuated", "evacuees_safe", "evacuees_stranded"]   # ← add these
                ]
                .mean()
                .reset_index()
            )

            agg_fixed = agg[
                (agg["population"]   == chart_pop) &
                (agg["num_shelters"] == chart_shelters)
            ].sort_values("nodes")

            COLORS = px.colors.qualitative.Set2

            st.markdown("#### Chart 7 — % Population Evacuated vs Population  *(primary objective)*")
            st.caption("100% = full evacuation achieved. Shows where each algorithm starts failing.")
            agg_pct = (
                df_ok.groupby(["grid_size", "population", "algorithm"])["pct_evacuated"]
                .mean().reset_index().sort_values("population")
            )
            if not agg_pct.empty:
                st.plotly_chart(
                    px.line(agg_pct, x="population", y="pct_evacuated",
                            color="algorithm", facet_col="grid_size",
                            markers=True, color_discrete_sequence=COLORS,
                            labels={"pct_evacuated": "% Evacuated", "population": "Population"})
                    .add_hline(y=100, line_dash="dash", line_color="green",
                            annotation_text="Full evacuation (100%)")
                    .update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=420),
                    use_container_width=True,
                )

            # ── Chart 1: Throughput vs Grid Size ──────────────────────────────
            st.markdown("#### Chart 1 — Throughput vs Grid Size")
            st.caption(f"Population = {chart_pop:,} | Shelters = {chart_shelters}")
            if not agg_fixed.empty:
                st.plotly_chart(
                    px.line(agg_fixed, x="grid_size", y="throughput", color="algorithm",
                            markers=True, color_discrete_sequence=COLORS,
                            labels={"throughput": "Throughput (veh/time)", "grid_size": "Grid Size"})
                    .update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"),
                    use_container_width=True,
                )

            # ── Chart 2: Makespan vs Grid Size ────────────────────────────────
            st.markdown("#### Chart 2 — Makespan vs Grid Size")
            st.caption(f"Population = {chart_pop:,} | Shelters = {chart_shelters}")
            if not agg_fixed.empty:
                st.plotly_chart(
                    px.line(agg_fixed, x="grid_size", y="makespan", color="algorithm",
                            markers=True, color_discrete_sequence=COLORS,
                            labels={"makespan": "Makespan (time units)", "grid_size": "Grid Size"})
                    .update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"),
                    use_container_width=True,
                )

            # ── Chart 3: Max Congestion vs Grid Size ──────────────────────────
            st.markdown("#### Chart 3 — Max Congestion Ratio vs Grid Size")
            st.caption(f"Population = {chart_pop:,} | Shelters = {chart_shelters}  |  Values > 1.0 = over capacity ⚠️")
            if not agg_fixed.empty:
                st.plotly_chart(
                    px.bar(agg_fixed, x="grid_size", y="max_congestion", color="algorithm",
                           barmode="group", color_discrete_sequence=COLORS,
                           labels={"max_congestion": "Max Congestion Ratio", "grid_size": "Grid Size"})
                    .add_hline(y=1.0, line_dash="dash", line_color="red",
                               annotation_text="Capacity limit (1.0×)")
                    .update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"),
                    use_container_width=True,
                )

            # ── Chart 4: Makespan vs Population — faceted by grid size ─────────
            st.markdown("#### Chart 4 — Makespan vs Population  *(faceted by grid size)*")
            agg_pop = (
                df_ok.groupby(["grid_size", "population", "algorithm"])["makespan"]
                .mean().reset_index().sort_values("population")
            )
            if not agg_pop.empty:
                st.plotly_chart(
                    px.line(agg_pop, x="population", y="makespan",
                            color="algorithm", facet_col="grid_size",
                            markers=True, log_x=True, color_discrete_sequence=COLORS,
                            labels={"makespan": "Makespan (time units)", "population": "Population"})
                    .update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=420),
                    use_container_width=True,
                )

            # ── Chart 5: Runtime vs Grid Size (log y — scalability) ────────────
            st.markdown("#### Chart 5 — Algorithm Runtime vs Grid Size  *(scalability, log scale)*")
            if not agg_fixed.empty:
                st.plotly_chart(
                    px.line(agg_fixed, x="grid_size", y="runtime_sec", color="algorithm",
                            markers=True, log_y=True, color_discrete_sequence=COLORS,
                            labels={"runtime_sec": "Runtime (seconds)", "grid_size": "Grid Size"})
                    .update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"),
                    use_container_width=True,
                )

            # ── Chart 6: Avg Travel Time — MCMF vs Edmonds-Karp ───────────────
            st.markdown("#### Chart 6 — Avg Travel Time: MCMF vs Edmonds-Karp")
            st.caption(
                "Both algorithms achieve identical makespan and throughput. "
                "This chart reveals MCMF's route-efficiency advantage."
            )
            agg_flow = agg_fixed[agg_fixed["algorithm"].isin(["Max Flow (Edmonds-Karp)", "MCMF"])]
            if not agg_flow.empty:
                st.plotly_chart(
                    px.bar(agg_flow, x="grid_size", y="avg_travel_time", color="algorithm",
                           barmode="group", color_discrete_sequence=px.colors.qualitative.Pastel,
                           labels={"avg_travel_time": "Avg Travel Time (time units)", "grid_size": "Grid Size"})
                    .update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"),
                    use_container_width=True,
                )
            else:
                st.info("Include both flow algorithms to see this comparison.")

    else:
        st.info("Configure the parameters above and click **Run Experiments** to start.")

# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3 – OSM REAL-STREET ROUTING
# ══════════════════════════════════════════════════════════════════════════════
with tab_osm:
    st.title("🗺️ Real-Street Evacuation via OpenStreetMap")
    st.markdown(
        "Downloads a live street network from OpenStreetMap, places hazard zones "
        "and shelters on real intersections, then routes a small population to safety."
    )

    if not OSM_AVAILABLE:
        st.error("**osmnx** is not installed. Run `pip install osmnx` and restart the app.")
        st.stop()

    # ── Configuration ──────────────────────────────────────────────────────────
    osm_col1, osm_col2 = st.columns(2)
    with osm_col1:
        osm_location  = st.selectbox("📍 Location", list(PRESET_LOCATIONS.keys()))
        osm_algorithm = st.selectbox("Algorithm ", ["Dijkstra", "Max Flow (Edmonds-Karp)", "MCMF"],
                                     key="osm_algo")
    with osm_col2:
        osm_shelters = st.slider("# Shelters",    min_value=1, max_value=5,   value=2, key="osm_sh")
        osm_sources  = st.slider("# Hazard Zones", min_value=2, max_value=10, value=5, key="osm_src")
        osm_pop      = st.number_input("Population", min_value=10, max_value=500, value=100, key="osm_pop")

    run_osm = st.button("🚀 Download & Route", type="primary")

    # ── PHASE 1 — compute ──────────────────────────────────────────────────────
    if run_osm:
        current_osm_params = (osm_location, osm_shelters, osm_sources, int(osm_pop))

        # ── Step 1: only re-download if location/structure changed ────────────
        if (st.session_state.osm_base_G is None or
                st.session_state.osm_last_params != current_osm_params):

            with st.spinner(f"Downloading street network for **{osm_location}** from OSM…"):
                try:
                    G_osm, osm_src_nodes, osm_sh_nodes, osm_pos = load_osm_graph(
                        location_key=osm_location,
                        num_shelters=osm_shelters,
                        num_sources=osm_sources,
                        population=int(osm_pop),
                        seed=42,
                    )
                    st.session_state.osm_base_G      = G_osm
                    st.session_state.osm_sources     = osm_src_nodes
                    st.session_state.osm_shelters    = osm_sh_nodes
                    st.session_state.osm_pos         = osm_pos
                    st.session_state.osm_last_params = current_osm_params
                except Exception as e:
                    st.error(f"Failed to load OSM graph: {e}")
                    st.stop()
        else:
            st.toast("Same location & config — reusing street network for fair algorithm comparison!")

        # ── Step 2: always re-route on the same base graph ────────────────────
        with st.spinner(f"Running **{osm_algorithm}**…"):
            G_working = st.session_state.osm_base_G.copy()   # ← fresh copy each time
            G_osm_routed, osm_metrics = run_routing(
                G_working, osm_algorithm, int(osm_pop)
            )
            st.session_state.osm_G       = G_osm_routed
            st.session_state.osm_metrics = osm_metrics
            st.session_state.osm_routes  = extract_active_routes(G_osm_routed)

    # ── PHASE 2 — display ─────────────────────────────────────────────────────
    if st.session_state.osm_G is not None:
        G_r      = st.session_state.osm_G
        metrics  = st.session_state.osm_metrics
        routes   = st.session_state.osm_routes
        node_pos = st.session_state.osm_pos
        shelters = st.session_state.osm_shelters
        sources  = st.session_state.osm_sources

        loc      = PRESET_LOCATIONS[osm_location]
        st.success(
            f"✅ **{osm_location}** — {len(node_pos):,} intersections | "
            f"{G_r.number_of_edges():,} road segments | "
            f"{len(sources)} hazard zones | {len(shelters)} shelters"
        )

        # Metrics row
        st.subheader("📊 Routing Metrics")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Throughput",      f"{metrics.get('throughput', 0)} veh/t")
        c2.metric("Makespan",        f"{metrics.get('makespan', 0)} t-units")
        cong = metrics.get("max_congestion", 0)
        c3.metric("Max Congestion",  f"{'⚠️' if cong > 1 else '✅'} {cong}×")
        c4.metric("Avg Travel Time", f"{metrics.get('avg_travel_time', 0)} t-units")
        pct = metrics.get("pct_evacuated", 0)
        c5.metric("% Evacuated",     f"{'✅' if pct >= 100 else '⚠️'} {pct}%")
        c6.metric("Stranded",        f"{int(metrics.get('evacuees_stranded', 0)):,} people")

        st.divider()
        st.subheader("🗺️ Street-Level Evacuation Map")

        map_c, flt_c = st.columns([3, 1])

        with flt_c:
            st.markdown("#### 🔍 Route Filter")
            if not routes:
                st.info("No active routes.")
                osm_sel = None
            else:
                labels = ["— Show all routes —"] + [
                    f"Route {i+1}: ({r['volume']:.0f} ppl)"
                    for i, r in enumerate(routes)
                ]
                chosen = st.selectbox("Select route", range(len(labels)),
                                      format_func=lambda i: labels[i],
                                      key="osm_route_select")
                osm_sel = None if chosen == 0 else chosen - 1

                if osm_sel is not None:
                    r = routes[osm_sel]
                    st.metric("Volume", f"{r['volume']:.0f} evacuees")
                    st.metric("Hops",   len(r["path"]) - 1)
                    st.caption(f"Hazard **{r['start']}** → Shelter **{r['end']}**")

        with map_c:
            st.caption(
                "🟢 Green = free-flowing  🟡 Yellow = near capacity  🔴 Red = over capacity  "
                "| 🔴 nodes = hazard zones  🟢 nodes = shelters"
            )
            if osm_sel is None:
                fig = plot_osm_network(G_r, node_pos)
            else:
                fig = plot_osm_filtered(G_r, node_pos, routes[osm_sel])
            st.plotly_chart(fig, use_container_width=True)

        # Shelter utilization
        with st.expander("🏥 Shelter Utilization"):
            for sh in shelters:
                nd  = G_r.nodes[sh]
                cap = nd.get("shelter_capacity", 0)
                rem = nd.get("shelter_remaining", cap)
                if cap > 0:
                    used = cap - rem
                    pct  = used / cap
                    lbl  = (f"🔴 Shelter {sh}: {used}/{cap} — FULL" if pct >= 1
                            else f"{'🟡' if pct >= 0.7 else '🟢'} Shelter {sh}: {used}/{cap} ({pct*100:.0f}%)")
                    st.progress(pct, text=lbl)

        # Route log
        with st.expander(f"📋 Routing Log ({len(routes)} paths)"):
            for i, r in enumerate(routes):
                st.markdown(f"**Route {i+1}** — {r['volume']:.0f} evacuees")
                st.caption(f"Hazard {r['start']} → Shelter {r['end']}  |  {len(r['path'])-1} hops")
                st.divider()
    else:
        st.info("Select a location and click **Download & Route** to begin.")