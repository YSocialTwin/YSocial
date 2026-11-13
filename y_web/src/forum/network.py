"""Initial follow network of a forum client (the same models and parameters as the other platforms' client forms).

YForum reads ``population.network_file``: one ``follower,followed`` pair per line. The pure functions here build or
filter the pairs; the route writes the file.
"""

from typing import Dict, Iterable, List, Mapping, Optional, Tuple

MODELS = ("BA", "ER", "WS", "PLC", "C", "SBM", "LFR")

DEFAULTS = {
    "network_m": 2,
    "network_p": 0.1,
    "network_k": 4,
    "network_ws_p": 0.3,
    "network_plc_m": 2,
    "network_plc_p": 0.5,
    "network_blocks": 3,
    "network_p_in": 0.3,
    "network_p_out": 0.05,
    "network_tau1": 2.5,
    "network_tau2": 1.5,
    "network_mu": 0.1,
    "network_avg_degree": 5,
}
_INTS = {
    "network_m",
    "network_k",
    "network_plc_m",
    "network_blocks",
    "network_avg_degree",
}


class NetworkError(ValueError):
    """The network settings or file cannot be used."""


def parse_parameters(form: Mapping[str, str]) -> Dict[str, float]:
    """The numeric parameters of the form, with the defaults of the other platforms."""
    out: Dict[str, float] = {}
    for key, default in DEFAULTS.items():
        raw = form.get(key)
        if raw in (None, ""):
            out[key] = default
            continue
        try:
            out[key] = int(raw) if key in _INTS else float(raw)
        except (TypeError, ValueError):
            raise NetworkError(f"{key} must be a number") from None
    return out


def generate_edges(
    model: str, names: List[str], params: Optional[Mapping[str, float]] = None
) -> List[Tuple[str, str]]:
    """Directed ``(follower, followed)`` pairs of a synthetic network over ``names`` (both directions of each edge)."""
    import networkx as nx

    if model not in MODELS:
        raise NetworkError(f"unknown network model {model!r}")
    p = {**DEFAULTS, **(params or {})}
    n = len(names)
    if n < 3:
        raise NetworkError("the population is too small for a network")
    try:
        if model == "BA":
            g = nx.barabasi_albert_graph(n, m=int(p["network_m"]))
        elif model == "ER":
            g = nx.erdos_renyi_graph(n, p=p["network_p"])
        elif model == "WS":
            g = nx.watts_strogatz_graph(n, k=int(p["network_k"]), p=p["network_ws_p"])
        elif model == "PLC":
            g = nx.powerlaw_cluster_graph(
                n, m=int(p["network_plc_m"]), p=p["network_plc_p"]
            )
        elif model == "C":
            g = nx.complete_graph(n)
        elif model == "SBM":
            blocks = max(1, int(p["network_blocks"]))
            sizes = [n // blocks] * blocks
            sizes[-1] += n % blocks
            probs = [
                [
                    p["network_p_in"] if i == j else p["network_p_out"]
                    for j in range(blocks)
                ]
                for i in range(blocks)
            ]
            g = nx.stochastic_block_model(sizes, probs)
        else:  # LFR
            g = nx.LFR_benchmark_graph(
                n=n,
                tau1=p["network_tau1"],
                tau2=p["network_tau2"],
                mu=p["network_mu"],
                average_degree=int(p["network_avg_degree"]),
                min_community=min(max(5, n // 10), n // 3),
            )
    except (nx.NetworkXError, nx.ExceededMaxIterations, ValueError) as exc:
        raise NetworkError(f"the {model} network cannot be built: {exc}") from None
    edges: List[Tuple[str, str]] = []
    for a, b in g.edges:
        edges.append((names[a], names[b]))
        edges.append((names[b], names[a]))
    return edges


def filter_uploaded(
    text: str, names: Iterable[str]
) -> Tuple[List[Tuple[str, str]], List[str]]:
    """The pairs of an uploaded two-column csv whose names are in the population, and the lines that were not."""
    known = set(names)
    edges: List[Tuple[str, str]] = []
    skipped: List[str] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            if line.strip():
                skipped.append(line.strip())
            continue
        if parts[0] in known and parts[1] in known and parts[0] != parts[1]:
            edges.append((parts[0], parts[1]))
        else:
            skipped.append(line.strip())
    return edges, skipped
