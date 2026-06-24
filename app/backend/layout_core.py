"""Layered (Sugiyama) node placement + orthogonal edge routing, format-agnostic.

Pure graph math: nodes are ``{id: {"w", "h"}}`` and edges
``[{"source", "target"}]``; the output is node positions plus waypoint polylines.
The BPMN and PNML writers feed this and turn the result into their own diagram
vocabulary.
"""

from collections import deque, defaultdict


def _assign_layers(real_ids, successors):
    """Stage 1 -- assign every node a layer (column).

    Breaks cycles with a DFS (an edge back to a node still on the stack is a
    *back edge*, drawn as a loop later), then runs longest-path (Kahn) layering
    over the acyclic skeleton. Returns ``(node_layer, back_edges)``.

    Without the cycle break, every node on a rework loop (e.g. "reopen claim ->
    reassess") never reaches in-degree zero and gets scattered into a trailing
    column, wrecking the diagram.
    """
    _WHITE, _GRAY, _BLACK = 0, 1, 2
    color = {nid: _WHITE for nid in real_ids}
    back_edges: set[tuple[str, str]] = set()
    for root_node in real_ids:
        if color[root_node] != _WHITE:
            continue
        color[root_node] = _GRAY
        dfs_stack = [(root_node, iter(successors[root_node]))]
        while dfs_stack:
            node, succ_iter = dfs_stack[-1]
            for nxt in succ_iter:
                if color[nxt] == _GRAY:
                    back_edges.add((node, nxt))
                elif color[nxt] == _WHITE:
                    color[nxt] = _GRAY
                    dfs_stack.append((nxt, iter(successors[nxt])))
                    break
            else:
                color[node] = _BLACK
                dfs_stack.pop()

    # Longest-path layering (Kahn) over the acyclic skeleton. Relaxing each edge
    # only after its source is dequeued keeps the longest-path layers correct.
    acyclic_succ = {
        nid: [t for t in successors[nid] if (nid, t) not in back_edges]
        for nid in real_ids
    }
    indeg = {nid: 0 for nid in real_ids}
    for nid in real_ids:
        for tgt in acyclic_succ[nid]:
            indeg[tgt] += 1
    topo_queue: deque[str] = deque(nid for nid in real_ids if indeg[nid] == 0)
    indeg_work = dict(indeg)
    node_layer: dict[str, int] = {nid: 0 for nid in real_ids}
    while topo_queue:
        node = topo_queue.popleft()
        for nxt in acyclic_succ[node]:
            node_layer[nxt] = max(node_layer[nxt], node_layer[node] + 1)
            indeg_work[nxt] -= 1
            if indeg_work[nxt] == 0:
                topo_queue.append(nxt)
    return node_layer, back_edges


def _insert_dummies(flows, node_layer, node_w, node_h):
    """Stage 2 -- split every forward edge spanning >= 2 layers into unit hops.

    Inserts a size-0 *dummy* node in each layer the edge passes over (mutating
    ``node_layer``/``node_w``/``node_h``), which claims a slot there and so
    reserves a clear lane for the edge instead of letting it run across the
    nodes it skips. Returns ``(chains, is_dummy)``: one node chain per flow
    (index-aligned with *flows*) and the set of dummy ids.
    """
    is_dummy: set[str] = set()
    chains: list[list[str]] = []  # one node chain per flow, index-aligned
    dummy_seq = 0
    for flow in flows:
        src, tgt = flow.get("source", ""), flow.get("target", "")
        if src not in node_layer or tgt not in node_layer:
            # Missing endpoint: keep a direct chain; the absent shape surfaces
            # as a KeyError in _add_diagram (mapped to invalid_model upstream).
            chains.append([src, tgt])
            continue
        span = node_layer[tgt] - node_layer[src]
        if span >= 2:
            chain = [src]
            for layer in range(node_layer[src] + 1, node_layer[tgt]):
                dummy = f"__dummy_{dummy_seq}"
                dummy_seq += 1
                node_w[dummy] = 0
                node_h[dummy] = 0
                node_layer[dummy] = layer
                is_dummy.add(dummy)
                chain.append(dummy)
            chain.append(tgt)
            chains.append(chain)
        else:
            chains.append([src, tgt])
    return chains, is_dummy


def _order_layers(node_layer, chains, is_dummy):
    """Stage 3 -- order nodes within each layer to reduce edge crossings.

    Builds the per-layer node lists, then runs barycenter sweeps: each node is
    pulled toward the mean rank of its neighbours in the adjacent layer. Returns
    ``(layers, up_adj, down_adj)`` -- the ordered layers and the layer-adjacency
    used here and again by coordinate assignment.
    """
    layers: dict[int, list[str]] = {}
    for nid, lyr in node_layer.items():
        layers.setdefault(lyr, []).append(nid)
    # Deterministic start order: real nodes by id, dummies after.
    for lyr in layers:
        layers[lyr].sort(key=lambda n: (n in is_dummy, n))

    up_adj: dict[str, list[str]] = {nid: [] for nid in node_layer}
    down_adj: dict[str, list[str]] = {nid: [] for nid in node_layer}
    for chain in chains:
        for a, b in zip(chain, chain[1:]):
            if (
                a in node_layer
                and b in node_layer
                and node_layer[b] == node_layer[a] + 1
            ):
                down_adj[a].append(b)
                up_adj[b].append(a)

    max_layer = max(layers)
    rank: dict[str, int] = {}
    for lyr in layers:
        for i, nid in enumerate(layers[lyr]):
            rank[nid] = i

    def _sweep(layer_indices, neighbours):
        for lyr in layer_indices:
            nodes = layers.get(lyr)
            if not nodes:
                continue
            scored = []
            for nid in nodes:
                ne = neighbours[nid]
                bary = sum(rank[x] for x in ne) / len(ne) if ne else rank[nid]
                scored.append((bary, rank[nid], nid))
            scored.sort()
            layers[lyr] = [nid for _, _, nid in scored]
            for i, nid in enumerate(layers[lyr]):
                rank[nid] = i

    for _ in range(4):
        _sweep(range(1, max_layer + 1), up_adj)  # top-down using upper neighbours
        _sweep(range(max_layer - 1, -1, -1), down_adj)  # bottom-up using lower

    return layers, up_adj, down_adj


def _isotonic_fit(values):
    """Least-squares non-decreasing fit of *values* (pool-adjacent-violators).

    The optimal way to push an ordered run of desired positions into a monotone
    sequence with the least total movement -- the core of coordinate assignment.
    """
    blocks: list[list[float]] = []  # [sum, count] per pooled block
    for v in values:
        s, c = v, 1
        while blocks and blocks[-1][0] / blocks[-1][1] > s / c:
            ps, pc = blocks.pop()
            s += ps
            c += pc
        blocks.append([s, c])
    out: list[float] = []
    for s, c in blocks:
        out.extend([s / c] * c)
    return out


def _place_in_layer(ids, desired, node_h, v_gap):
    """Set an ordered layer's node centres as close to *desired* as the non-
    overlap constraint (>= ``v_gap`` between boxes) allows.

    Subtracting each node's cumulative minimum offset turns the separation
    constraint into plain monotonicity, solved exactly by :func:`_isotonic_fit`.
    """
    if not ids:
        return {}
    prefix = [0.0] * len(ids)
    for i in range(1, len(ids)):
        sep = node_h[ids[i - 1]] / 2 + v_gap + node_h[ids[i]] / 2
        prefix[i] = prefix[i - 1] + sep
    fit = _isotonic_fit([desired[ids[i]] - prefix[i] for i in range(len(ids))])
    return {ids[i]: fit[i] + prefix[i] for i in range(len(ids))}


def _assign_coordinates(
    layers, up_adj, down_adj, node_w, node_h, is_dummy, h_gap, v_gap, x_offset, y_offset
):
    """Stage 4 -- assign pixel coordinates to the ordered layers.

    Columns go left to right (column width = widest node in the layer). The
    vertical (cross-axis) coordinate is what makes edges straight: each node is
    iteratively pulled toward the mean centre of its neighbours, and
    :func:`_place_in_layer` resolves the resulting overlaps while keeping each
    node as close to that target as the ``v_gap`` separation allows. Returns
    ``(positions, centers, col_x, col_w)`` -- ``positions`` are top-left corners
    of the real nodes; ``centers`` covers dummies too (for routing).
    """
    sorted_layers = sorted(layers)
    col_w = {
        lyr: max((node_w[n] for n in layers[lyr]), default=0) for lyr in sorted_layers
    }
    col_x: dict[int, int] = {}
    x = x_offset
    for lyr in sorted_layers:
        col_x[lyr] = x
        x += col_w[lyr] + h_gap

    # Initial centres: simple top-to-bottom stacking per layer.
    yc: dict[str, float] = {}
    for lyr in sorted_layers:
        y = 0.0
        for nid in layers[lyr]:
            y += node_h[nid] / 2
            yc[nid] = y
            y += node_h[nid] / 2 + v_gap

    # Iteratively align each node with the mean centre of its neighbours (both
    # adjacent layers), resolving overlaps after every layer. Alternating the
    # sweep direction lets alignment propagate both ways; a few passes converge.
    neighbours = {nid: up_adj[nid] + down_adj[nid] for nid in yc}
    for sweep in range(8):
        order = sorted_layers if sweep % 2 == 0 else sorted_layers[::-1]
        for lyr in order:
            ids = layers[lyr]
            desired = {
                nid: sum(yc[m] for m in neighbours[nid]) / len(neighbours[nid])
                if neighbours[nid]
                else yc[nid]
                for nid in ids
            }
            yc.update(_place_in_layer(ids, desired, node_h, v_gap))

    # Normalise so the topmost node sits at y_offset.
    shift = y_offset - min((yc[n] - node_h[n] / 2 for n in yc), default=0.0)

    positions: dict[str, dict] = {}
    centers: dict[str, tuple] = {}
    for lyr in sorted_layers:
        for nid in layers[lyr]:
            w, h = node_w[nid], node_h[nid]
            elem_x = col_x[lyr] + (col_w[lyr] - w) // 2
            cy = yc[nid] + shift
            centers[nid] = (elem_x + w / 2, cy)
            if nid not in is_dummy:
                positions[nid] = {
                    "x": int(elem_x),
                    "y": int(round(cy - h / 2)),
                    "w": w,
                    "h": h,
                }
    return positions, centers, col_x, col_w


def _sugiyama_layout(
    elements_by_id, flows, h_gap=80, v_gap=50, x_offset=50, y_offset=50
):
    """Compute a layered (Sugiyama-style) node placement.

    Runs the classic Sugiyama stages, each delegated to a helper, to keep edges
    from crossing nodes or stacking on top of one another:

    1. :func:`_assign_layers` -- cycle break + longest-path layering -> columns.
    2. :func:`_insert_dummies` -- routing dummies for multi-layer forward edges.
    3. :func:`_order_layers` -- barycenter sweeps to reduce crossings.
    4. :func:`_assign_coordinates` -- columns left to right, stacked + aligned.

    This stage only *places nodes*. It produces no edge waypoints and writes no
    XML: it returns node positions plus the structural metadata (``ctx``) that
    :func:`_route_edges` later turns into waypoints.

    Args:
        elements_by_id: ``{id: {"w": int, "h": int}}`` -- node sizes in pixels.
        flows: list of ``{"source": str, "target": str}`` dicts.
        h_gap: horizontal gap between adjacent layers (pixels).
        v_gap: vertical gap between nodes within a layer (pixels).
        x_offset: left margin (pixels).
        y_offset: top margin (pixels).

    Returns:
        ``(positions, ctx)`` where *positions* is
        ``{real_id: {"x", "y", "w", "h"}}`` (top-left corners, dummy nodes
        excluded) and *ctx* carries the routing metadata (``centers``, per-flow
        ``chains``, ``col_x``/``col_w`` column geometry, ``node_layer``, the
        ``is_dummy`` set and the ``back_edges`` set of cycle-closing
        ``(source, target)`` pairs).
    """
    empty_ctx = {
        "centers": {},
        "chains": [],
        "col_x": {},
        "col_w": {},
        "node_layer": {},
        "is_dummy": set(),
        "back_edges": set(),
    }
    real_ids = list(elements_by_id.keys())
    if not real_ids:
        return {}, empty_ctx

    # Adjacency over the real nodes only (endpoints outside the node set, e.g. a
    # dangling flow, are dropped here and surface downstream).
    successors: dict[str, list[str]] = {nid: [] for nid in real_ids}
    for flow in flows:
        src, tgt = flow.get("source", ""), flow.get("target", "")
        if src in successors and tgt in successors:
            successors[src].append(tgt)

    node_layer, back_edges = _assign_layers(real_ids, successors)

    node_w = {nid: elements_by_id[nid]["w"] for nid in real_ids}
    node_h = {nid: elements_by_id[nid]["h"] for nid in real_ids}
    chains, is_dummy = _insert_dummies(flows, node_layer, node_w, node_h)

    layers, up_adj, down_adj = _order_layers(node_layer, chains, is_dummy)

    positions, centers, col_x, col_w = _assign_coordinates(
        layers,
        up_adj,
        down_adj,
        node_w,
        node_h,
        is_dummy,
        h_gap,
        v_gap,
        x_offset,
        y_offset,
    )

    ctx = {
        "centers": centers,
        "chains": chains,
        "col_x": col_x,
        "col_w": col_w,
        "node_layer": node_layer,
        "is_dummy": is_dummy,
        "back_edges": back_edges,
    }
    return positions, ctx


def _loop_waypoints(src, tgt, lane_y):
    """Route a back-edge / same-layer edge as a U through the *lane_y* corridor.

    Such edges point against the left-to-right flow, so a straight orthogonal
    route would cut back across the columns. Dropping into a dedicated lane
    beneath the diagram keeps them clear of every shape and forward edge; the
    caller picks a distinct *lane_y* per loop so multiple loops do not overlap.
    """
    sx = src["x"] + src["w"]
    sy = src["y"] + src["h"] // 2
    tx = tgt["x"]
    ty = tgt["y"] + tgt["h"] // 2
    margin = 30
    return [
        (sx, sy),
        (sx + margin, sy),
        (sx + margin, lane_y),
        (tx - margin, lane_y),
        (tx - margin, ty),
        (tx, ty),
    ]


def _route_edges(positions, ctx, flows, strategy):
    """Compute waypoint polylines for *flows*, keyed by flow index.

    Returns ``{index: [(x, y), ...]}``; each polyline includes its end anchors.
    ``strategy``:
      * ``"full_ortho"`` -- route every edge orthogonally. Vertical risers live
        in the gaps between columns (one channel per riser) and edges sharing a
        split source or join target bundle onto a shared channel.
      * ``"loops_only"`` -- route only back-edges; forward edges get ``[]``.
    Back-edges always go through their own lane below the diagram, regardless of
    strategy.
    """
    centers = ctx["centers"]
    chains = ctx["chains"]
    col_x = ctx["col_x"]
    col_w = ctx["col_w"]
    node_layer = ctx["node_layer"]
    is_dummy = ctx["is_dummy"]

    # A real node connects at its right/left border; a routing dummy is a single
    # point at its centre.
    def _exit_x(nid):
        return (
            centers[nid][0]
            if nid in is_dummy
            else positions[nid]["x"] + positions[nid]["w"]
        )

    def _entry_x(nid):
        return centers[nid][0] if nid in is_dummy else positions[nid]["x"]

    def _is_regular(chain):
        """True when *chain* is a forward run of adjacent-layer hops."""
        if not chain or len(chain) < 2:
            return False
        for a, b in zip(chain, chain[1:]):
            if a not in node_layer or b not in node_layer:
                return False
            if node_layer[b] != node_layer[a] + 1:
                return False
        return True

    # Classify every flow into forward hops (grouped by the gap they cross) or a
    # loop (back-edge); collect the risers that need a vertical channel.
    hops_by_flow: dict[int, list] = {}
    risers_by_gap: dict[int, list] = defaultdict(list)
    for idx, flow in enumerate(flows):
        chain = chains[idx]
        if not _is_regular(chain):
            hops_by_flow[idx] = None
            continue
        hop_list = []
        for a, b in zip(chain, chain[1:]):
            hop = {
                "a": a,
                "b": b,
                "layer": node_layer[a],
                "y1": centers[a][1],
                "y2": centers[b][1],
                "channel": None,
            }
            hop_list.append(hop)
            if abs(hop["y1"] - hop["y2"]) >= 1:
                risers_by_gap[node_layer[a]].append(hop)
        hops_by_flow[idx] = hop_list

    if strategy == "full_ortho":
        for lyr, hops in risers_by_gap.items():
            gap_lo = col_x[lyr] + col_w[lyr]
            gap_hi = col_x[lyr + 1]
            # Edges sharing a target (a join) or a source (a split) collapse onto
            # one shared channel, so they turn at the same x and meet at a single
            # point instead of stair-stepping. Other hops each get their own.
            out_count: dict[str, int] = defaultdict(int)
            in_count: dict[str, int] = defaultdict(int)
            for hop in hops:
                out_count[hop["a"]] += 1
                in_count[hop["b"]] += 1
            bundles: dict[tuple, list] = {}
            for hop in hops:
                if in_count[hop["b"]] > 1:
                    key = ("in", hop["b"])
                elif out_count[hop["a"]] > 1:
                    key = ("out", hop["a"])
                else:
                    key = ("single", id(hop))
                bundles.setdefault(key, []).append(hop)
            # Lay channels left-to-right: splits near their source, joins near
            # their target, singletons between; break ties by mean height.
            kind_rank = {"out": 0, "single": 1, "in": 2}

            def _bundle_key(key):
                ys = [(h["y1"] + h["y2"]) / 2 for h in bundles[key]]
                return (kind_rank[key[0]], sum(ys) / len(ys))

            ordered = sorted(bundles, key=_bundle_key)
            count = len(ordered)
            for i, key in enumerate(ordered):
                channel = gap_lo + (i + 1) * (gap_hi - gap_lo) / (count + 1)
                for hop in bundles[key]:
                    hop["channel"] = channel

    bottom_y = max((p["y"] + p["h"] for p in positions.values()), default=0)

    def _loop_span(idx):
        src = positions[flows[idx]["source"]]
        tgt = positions[flows[idx]["target"]]
        return abs((src["x"] + src["w"]) - tgt["x"])

    # Each loop gets its own lane below the diagram; narrower loops take the
    # shallower lanes so wider loops nest cleanly underneath them.
    loop_indices = sorted(
        (
            i
            for i, hops in hops_by_flow.items()
            if hops is None
            and flows[i]["source"] in positions
            and flows[i]["target"] in positions
        ),
        key=_loop_span,
    )
    loop_lane = {idx: bottom_y + 50 + k * 45 for k, idx in enumerate(loop_indices)}

    routes: dict[int, list] = {}
    for idx, flow in enumerate(flows):
        hop_list = hops_by_flow[idx]
        if hop_list is None:
            if idx in loop_lane:
                routes[idx] = _loop_waypoints(
                    positions[flow["source"]],
                    positions[flow["target"]],
                    loop_lane[idx],
                )
            else:
                routes[idx] = []
        elif strategy == "full_ortho":
            chain = chains[idx]
            points = [(_exit_x(chain[0]), centers[chain[0]][1])]
            for hop in hop_list:
                target_pt = (_entry_x(hop["b"]), hop["y2"])
                if abs(hop["y1"] - hop["y2"]) < 1:
                    points.append(target_pt)
                else:
                    channel = hop["channel"]
                    points.append((channel, hop["y1"]))
                    points.append((channel, hop["y2"]))
                    points.append(target_pt)
            routes[idx] = points
        else:
            routes[idx] = []
    return routes
