import time
import random
import threading
import pandas as pd
from core.graph_engine import generate_city_grid
from core.routing import run_routing

# ── Experiment dimensions ────────────────────────────────────────────────────
GRID_SIZES     = [10, 30, 100]
POPULATIONS = [100, 300, 600, 1200]
SHELTER_COUNTS = [2, 5, 10]
ALGORITHMS     = ["Dijkstra", "Max Flow (Edmonds-Karp)", "MCMF"]
NUM_SEEDS      = 10

# Per-run wall-clock timeout (seconds).
# 100×100 MCMF with large populations can be very slow; this prevents hangs.
TIMEOUT_SEC = 120


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scale_sources(grid_size: int) -> int:
    """Return a source-node count that scales sensibly with the grid."""
    # ~5 % of nodes, clamped between 5 and 20 so tiny grids and huge grids
    # both get a reasonable number of hazard zones.
    return min(max(5, int(grid_size * grid_size * 0.05)), 20)


def _worker(grid_size, population, num_shelters, algorithm, seed, holder):
    """Thread target: build graph, run routing, store metrics in *holder*."""
    try:
        random.seed(seed)

        G, sources, shelters = generate_city_grid(
            n=grid_size,
            num_shelters=num_shelters,
            num_sources=_scale_sources(grid_size),
            population=population,
        )

        t0 = time.perf_counter()
        _, metrics = run_routing(G, algorithm, population)
        elapsed = round(time.perf_counter() - t0, 4)

        holder["ok"] = True
        holder["metrics"] = metrics
        holder["runtime"] = elapsed

    except Exception as exc:
        holder["ok"] = False
        holder["error"] = str(exc)


# ── Public API ────────────────────────────────────────────────────────────────

def run_single_experiment(
    grid_size: int,
    population: int,
    num_shelters: int,
    algorithm: str,
    seed: int,
) -> dict:
    """
    Run one experiment in a daemon thread with a hard timeout.

    Returns a flat dict with all result fields so it can be appended
    directly to a list and converted to a DataFrame.
    """
    base = {
        "grid_size":    f"{grid_size}×{grid_size}",
        "nodes":        grid_size * grid_size,
        "population":   population,
        "num_shelters": num_shelters,
        "algorithm":    algorithm,
        "seed":         seed,
    }

    holder: dict = {}
    thread = threading.Thread(
        target=_worker,
        args=(grid_size, population, num_shelters, algorithm, seed, holder),
        daemon=True,
    )
    thread.start()
    thread.join(TIMEOUT_SEC)

    # ── Timed out ────────────────────────────────────────────────────────────
    if thread.is_alive():
        return {
            **base,
            "throughput": None, "makespan": None,
            "max_congestion": None, "avg_travel_time": None,
            "runtime_sec": TIMEOUT_SEC,
            "status": "timeout",
        }

    # ── Errored ──────────────────────────────────────────────────────────────
    if not holder.get("ok"):
        return {
            **base,
            "throughput": None, "makespan": None,
            "max_congestion": None, "avg_travel_time": None,
            "runtime_sec": None,
            "status": f"error: {holder.get('error', 'unknown')}",
        }

    # ── Success ───────────────────────────────────────────────────────────────
    m = holder["metrics"]
    return {
        **base,
        "throughput":          m.get("throughput"),
        "makespan":            m.get("makespan"),
        "max_congestion":      m.get("max_congestion"),
        "avg_travel_time":     m.get("avg_travel_time"),
        "evacuees_safe":       m.get("evacuees_safe"),
        "evacuees_stranded":   m.get("evacuees_stranded"),
        "pct_evacuated":       m.get("pct_evacuated"),
        "feasible":            m.get("feasible"),
        "runtime_sec":         holder["runtime"],
        "status":              "success",
    }


def experiment_generator(
    grid_sizes:     list,
    populations:    list,
    shelter_counts: list,
    algorithms:     list,
    num_seeds:      int = NUM_SEEDS,
):
    """
    Generator that yields ``(completed, total, result_dict)`` for every run.

    Designed to be consumed by Streamlit so the progress bar can update
    after each individual experiment rather than waiting for the whole suite.

    Usage::

        for completed, total, result in experiment_generator(...):
            progress_bar.progress(completed / total)
            results.append(result)
    """
    combos = [
        (gs, pop, ns, algo, seed)
        for gs    in grid_sizes
        for pop   in populations
        for ns    in shelter_counts
        for algo  in algorithms
        for seed  in range(num_seeds)
    ]
    total = len(combos)

    for i, (gs, pop, ns, algo, seed) in enumerate(combos):
        result = run_single_experiment(gs, pop, ns, algo, seed)
        yield i + 1, total, result


def summarize_results(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate raw results into mean ± std across seeds.

    Returns one row per (grid_size, population, num_shelters, algorithm)
    combination, with ``_mean`` and ``_std`` columns for every numeric metric,
    plus an ``n_runs`` column showing how many seeds succeeded.
    """
    numeric = [
        "throughput", "makespan", "max_congestion",
        "avg_travel_time", "runtime_sec",
        "evacuees_safe", "evacuees_stranded", "pct_evacuated",
    ]
    groups  = ["grid_size", "nodes", "population", "num_shelters", "algorithm"]

    ok = df[df["status"] == "success"].copy()
    if ok.empty:
        return pd.DataFrame()

    agg = (
        ok.groupby(groups)[numeric]
        .agg(["mean", "std"])
        .round(3)
    )
    agg.columns = [f"{col}_{stat}" for col, stat in agg.columns]

    counts = ok.groupby(groups).size().rename("n_runs")
    feasible_rate = ok.groupby(groups)["feasible"].mean().rename("feasible_rate")
    summary = agg.join(counts).join(feasible_rate).reset_index()

    # Re-order columns for readability
    front = groups + ["n_runs"]
    rest  = [c for c in summary.columns if c not in front]
    return summary[front + rest]