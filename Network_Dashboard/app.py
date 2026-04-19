import streamlit as st
import pandas as pd
import plotly.express as px

# ── Our backend modules ───────────────────────────────────────────────────────
from core.graph_engine import generate_city_grid
from core.routing      import run_routing, extract_active_routes
from core.visualizer   import plot_animated_network
from core.experiments  import (
    experiment_generator,
    summarize_results,
    GRID_SIZES, POPULATIONS, SHELTER_COUNTS, ALGORITHMS, NUM_SEEDS,
    TIMEOUT_SEC,
    _scale_sources
)

st.set_page_config(layout="wide", page_title="Evacuation Routing Simulator")

# ─────────────────────────────────────────────────────────────────────────────
#  SHARED SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
for key, default in [
    ("base_graph",  None),
    ("sources",     None),
    ("shelters",    None),
    ("last_params", None),
    ("exp_results", None),   # raw DataFrame from last experiment run
    ("exp_summary", None),   # aggregated DataFrame
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─────────────────────────────────────────────────────────────────────────────
#  TOP-LEVEL TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_sim, tab_exp = st.tabs(["🚨 Simulator", "🔬 Experiments"])


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
        population   = st.number_input("Population Size", min_value=100, max_value=100000, value=1000)
        num_shelters = st.slider("# Shelters",           min_value=1,   max_value=10,     step=1,  value=2)
        st.divider()
        run_sim = st.button("Run Simulation", type="primary", use_container_width=True)

    st.title("🚨 Evacuation Routing Simulator")

    if run_sim:
        st.write(f"Running **{algorithm}**...")

        current_params = (grid_size, num_shelters, population)

        if st.session_state.base_graph is None or st.session_state.last_params != current_params:
            with st.spinner("Generating new city grid..."):
                G, sources, shelters = generate_city_grid(
                    n=grid_size,
                    num_shelters=num_shelters,
                    num_sources=_scale_sources(grid_size),
                    population=population
                )
                st.session_state.base_graph  = G
                st.session_state.sources     = sources
                st.session_state.shelters    = shelters
                st.session_state.last_params = current_params
        else:
            st.toast("Reusing the same city layout for direct algorithm comparison!")

        G_working = st.session_state.base_graph.copy()
        sources   = st.session_state.sources
        shelters  = st.session_state.shelters

        st.success(f"✅ City loaded! {len(sources)} Hazard Zones (Red) and {len(shelters)} Shelters (Green).")

        with st.spinner(f"Calculating routes using {algorithm}..."):
            G_routed, metrics = run_routing(G_working, algorithm, population)

        st.subheader("🗺️ Live Evacuation Map")
        st.caption("Press 'Play Routing Animation' below the map to see traffic flow.")
        st.plotly_chart(plot_animated_network(G_routed), use_container_width=True)

        st.subheader("📊 Simulation Metrics")
        col1, col2, col3, col4, col5, col6 = st.columns(6)

        col1.metric("Throughput",      f"{metrics.get('throughput', 0)} veh/time")
        col2.metric("Makespan",        f"{metrics.get('makespan', 0)} time units")
        cong     = metrics.get("max_congestion", 0)
        cong_str = f"⚠️ {cong}x Cap" if cong > 1 else f"✅ {cong}x Cap"
        col3.metric("Max Congestion",  cong_str)
        col4.metric("Avg Travel Time", f"{metrics.get('avg_travel_time', 0)} time units")

        pct       = metrics.get("pct_evacuated", 0)
        stranded  = int(metrics.get("evacuees_stranded", 0))
        pct_icon  = "✅" if pct >= 100 else "⚠️"
        col5.metric("% Evacuated",    f"{pct_icon} {pct}%")
        col6.metric("Stranded",       f"{stranded:,} people")

        st.divider()
        routes = extract_active_routes(G_routed)
        with st.expander(f"📋 View Detailed Routing Logs ({len(routes)} distinct paths found)"):
            if not routes:
                st.info("No active routes found.")
            else:
                for i, route in enumerate(routes):
                    path_str = " ➔ ".join(str(n) for n in route["path"])
                    st.markdown(f"**Route {i+1}** (Volume: `{route['volume']}` evacuees)")
                    st.write(f"🚦 **Path:** {path_str}")
                    st.caption(f"From Hazard {route['start']} to Shelter {route['end']}")
                    st.divider()
        
        # Shelter utilization panel
        with st.expander("🏥 Shelter Utilization"):
            for shelter in shelters:
                node_data = G_routed.nodes[shelter]
                cap       = node_data.get("shelter_capacity",  0)
                remaining = node_data.get("shelter_remaining", cap)
                used      = cap - remaining

                if cap > 0:
                    fill_pct = used / cap
                    # Color label based on how full the shelter is
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