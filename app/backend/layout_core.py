"""Layered (Sugiyama) node placement + orthogonal edge routing, format-agnostic.

Pure graph math: nodes are ``{id: {"w", "h"}}`` and edges
``[{"source", "target"}]``; the output is node positions plus waypoint polylines.
The BPMN and PNML writers feed this and turn the result into their own diagram
vocabulary.

The three placement stages each use their textbook-grade variant:

1. :func:`_assign_layers` -- DFS cycle break + longest-path layering, then a
   balancing (tightening) relaxation that pulls slack nodes toward their
   neighbours, the coordinate-descent counterpart of network-simplex's
   total-edge-length objective.
2. :func:`_order_layers` -- weighted-median sweeps + adjacent transpose, keeping
   the lowest-crossing ordering seen (the Gansner/STT heuristic).
3. :func:`_assign_coordinates` -- Brandes-Köpf cross-axis alignment (four runs
   averaged, which stays overlap-free) so straight runs stay aligned without the
   diagonal drift of a single-corner placement.

Edges spanning more than one layer (forward skips and reversed back-edges) are
broken into unit segments through interior *dummy vertices* -- one per skipped
layer -- by :func:`_insert_dummies`. The dummies take part in ordering and
coordinate assignment like any node, so a long edge threads cleanly between the
shapes of the layers it crosses (the formal Sugiyama long-edge model) instead of
detouring around the diagram. :func:`_route_edges` then routes *every* unit
segment of the proper graph by one rule -- a real adjacent edge and a link of a
dummy chain are indistinguishable -- so long and short edges from a split share
the same trunk. Only the degenerate cases a dummy cannot help -- self-loops
and back-edges between adjacent (or the same) layers, where no interior layer
exists -- still fall back to a horizontal lane below the diagram in
:func:`_route_edges`.
"""

from collections import deque, defaultdict


def _assign_layers(real_ids, successors):
    """Stage 1 -- assign every node a layer (column).

    Breaks cycles with a DFS (an edge back to a node still on the stack is a
    *back edge*, drawn as a loop later), runs longest-path (Kahn) layering over
    the acyclic skeleton, then balances slack nodes. Returns
    ``(node_layer, back_edges)``.

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

    # Balancing (tightening) pass. Longest-path anchors every node at its
    # earliest feasible layer (ASAP); nodes with slack then sit far from their
    # neighbours, inflating edge spans. Relax each interior node to the median of
    # its neighbours' layers, clamped to the window that still respects
    # precedence -- a coordinate-descent on the same total-edge-length objective
    # network-simplex solves exactly, without the simplex machinery.
    # Sources/sinks stay anchored so the layer count never grows.
    acyclic_pred: dict[str, list[str]] = {nid: [] for nid in real_ids}
    for nid in real_ids:
        for tgt in acyclic_succ[nid]:
            acyclic_pred[tgt].append(nid)
    for _ in range(8):
        moved = False
        for nid in real_ids:
            preds, succs = acyclic_pred[nid], acyclic_succ[nid]
            if not preds or not succs:
                continue
            lo = max(node_layer[p] for p in preds) + 1
            hi = min(node_layer[s] for s in succs) - 1
            if hi < lo:
                continue
            neigh = sorted(
                [node_layer[p] for p in preds] + [node_layer[s] for s in succs]
            )
            median = neigh[len(neigh) // 2]
            target = min(max(median, lo), hi)
            if target != node_layer[nid]:
                node_layer[nid] = target
                moved = True
        if not moved:
            break

    return node_layer, back_edges


def _median(positions):
    """Weighted median of *positions* (sorted), or ``-1`` when empty.

    The standard median heuristic value: the middle neighbour for odd counts,
    and for even counts the interpolation between the two middle neighbours
    weighted by the gaps on either side (Gansner et al.). Nodes that score
    ``-1`` keep their current slot during a sweep.
    """
    m = len(positions)
    if m == 0:
        return -1.0
    mid = m // 2
    if m % 2 == 1:
        return float(positions[mid])
    if m == 2:
        return (positions[0] + positions[1]) / 2.0
    left = positions[mid - 1] - positions[0]
    right = positions[m - 1] - positions[mid]
    if left + right == 0:
        return (positions[mid - 1] + positions[mid]) / 2.0
    return (positions[mid - 1] * right + positions[mid] * left) / (left + right)


def _inversions(seq):
    """Number of out-of-order pairs in *seq* -- the crossing count contribution."""
    cnt = 0
    for i in range(len(seq)):
        si = seq[i]
        for j in range(i + 1, len(seq)):
            if si > seq[j]:
                cnt += 1
    return cnt


def _order_layers(node_layer, flows):
    """Stage 2 -- order nodes within each layer to reduce edge crossings.

    Weighted-median sweeps (alternating direction) reposition each node toward
    the median slot of its neighbours in the adjacent layer; an adjacent-
    transpose pass then greedily swaps neighbours whenever that lowers the
    crossing count. The lowest-crossing ordering seen across iterations is kept
    (median + transpose are not monotone on their own). Returns
    ``(layers, up_adj, down_adj)`` -- the ordered layers and the layer-adjacency
    (built from the adjacent-layer flows only) reused by coordinate assignment.
    """
    layers: dict[int, list[str]] = {}
    for nid, lyr in node_layer.items():
        layers.setdefault(lyr, []).append(nid)
    for lyr in layers:
        layers[lyr].sort()  # deterministic start order

    up_adj: dict[str, list[str]] = {nid: [] for nid in node_layer}
    down_adj: dict[str, list[str]] = {nid: [] for nid in node_layer}
    for flow in flows:
        a, b = flow.get("source"), flow.get("target")
        if a in node_layer and b in node_layer and node_layer[b] == node_layer[a] + 1:
            down_adj[a].append(b)
            up_adj[b].append(a)

    sorted_layers = sorted(layers)
    if len(sorted_layers) < 2:
        return layers, up_adj, down_adj

    def _positions():
        return {nid: i for lyr in sorted_layers for i, nid in enumerate(layers[lyr])}

    def _pair_crossings(upper, lower, pos):
        """Crossings on the edges between two adjacent layers, given *pos*."""
        seq = []
        for u in upper:
            seq.extend(sorted(pos[w] for w in down_adj[u]))
        return _inversions(seq)

    def _total_crossings(pos):
        return sum(
            _pair_crossings(layers[sorted_layers[i]], layers[sorted_layers[i + 1]], pos)
            for i in range(len(sorted_layers) - 1)
        )

    def _wmedian(iteration):
        if iteration % 2 == 0:  # top-down, order each layer by its upper neighbours
            indices, adj = range(1, len(sorted_layers)), up_adj
        else:  # bottom-up, by lower neighbours
            indices, adj = range(len(sorted_layers) - 2, -1, -1), down_adj
        for li in indices:
            # Refresh positions per layer so each layer orders against the
            # already-swept neighbour (Gauss-Seidel); a single snapshot per
            # sweep would order against a stale configuration and barely cut
            # crossings.
            pos = _positions()
            row = layers[sorted_layers[li]]
            med = {v: _median(sorted(pos[x] for x in adj[v])) for v in row}
            movable = iter(
                sorted((v for v in row if med[v] >= 0), key=lambda v: med[v])
            )
            result = [v if med[v] < 0 else None for v in row]
            for i in range(len(result)):
                if result[i] is None:
                    result[i] = next(movable)
            layers[sorted_layers[li]] = result

    def _transpose():
        improved = True
        while improved:
            improved = False
            cur = _total_crossings(_positions())
            for li in range(len(sorted_layers)):
                row = layers[sorted_layers[li]]
                for i in range(len(row) - 1):
                    row[i], row[i + 1] = row[i + 1], row[i]
                    new = _total_crossings(_positions())
                    if new < cur:
                        cur = new
                        improved = True
                    else:
                        row[i], row[i + 1] = row[i + 1], row[i]

    best_order = {lyr: list(layers[lyr]) for lyr in sorted_layers}
    best_cross = _total_crossings(_positions())
    for iteration in range(8):
        _wmedian(iteration)
        _transpose()
        cross = _total_crossings(_positions())
        if cross < best_cross:
            best_cross = cross
            best_order = {lyr: list(layers[lyr]) for lyr in sorted_layers}
            if best_cross == 0:
                break
    layers = best_order

    return layers, up_adj, down_adj


def _bk_compaction(order, root, align, node_h, v_gap):
    """Place aligned blocks along the cross axis, packed to the minimum gap.

    Each block (a maximal chain linked by ``align``) gets one coordinate stored
    at its ``root``; blocks are pushed as close together as the ``v_gap``
    separation between same-layer neighbours allows, then class offsets
    (``shift``) merge the block classes. Standard Brandes-Köpf compaction.
    """
    inf = float("inf")
    x: dict[str, float] = {}
    sink: dict[str, str] = {}
    shift: dict[str, float] = {}
    pred_in_layer: dict[str, str] = {}
    for row in order:
        for j in range(1, len(row)):
            pred_in_layer[row[j]] = row[j - 1]
    for row in order:
        for v in row:
            sink[v] = v
            shift[v] = inf

    def place(v):
        if v in x:
            return
        x[v] = 0.0
        w = v
        while True:
            if w in pred_in_layer:
                above = pred_in_layer[w]
                u = root[above]
                place(u)
                if sink[v] == v:
                    sink[v] = sink[u]
                delta = node_h[w] / 2 + v_gap + node_h[above] / 2
                if sink[v] == sink[u]:
                    x[v] = max(x[v], x[u] + delta)
                else:
                    shift[sink[u]] = min(shift[sink[u]], x[v] - x[u] - delta)
            w = align[w]
            if w == v:
                break

    for row in order:
        for v in row:
            if root[v] == v:
                place(v)
    for row in order:
        for v in row:
            x[v] = x[root[v]]
            s = shift[sink[root[v]]]
            if s < inf:
                x[v] += s
    return x


def _bk_run(layer_order, upper_adj, node_h, v_gap, dummies):
    """One Brandes-Köpf alignment + compaction for a given graph orientation.

    *layer_order* is the layer stack top-to-bottom in this run's vertical
    direction; *upper_adj* maps each node to its neighbours in the previous
    layer of that orientation. Each node aligns to its median upper neighbour
    (left to right, so alignments never cross). Returns a cross-axis coordinate
    per node.

    *Inner segments* -- edges between two dummy vertices, i.e. consecutive links
    of a long edge's chain -- get priority via Brandes-Köpf type-1 conflict
    marking: a non-inner segment that crosses an inner one is marked and skipped
    during alignment, so a long edge's dummy chain aligns into a single straight
    vertical block instead of stepping (the staircase a naive alignment produces
    on long edges in dense graphs).
    """
    pos = {v: j for row in layer_order for j, v in enumerate(row)}
    upper = {
        v: sorted(upper_adj.get(v, ()), key=lambda u: pos[u])
        for row in layer_order
        for v in row
    }

    # Mark type-1 conflicts (Brandes-Köpf, Algorithm 1). For each adjacent layer
    # pair, walk the lower layer between successive inner segments; any segment
    # whose upper endpoint sits outside the [k0, k1] window the inner segments
    # bound is a non-inner segment crossing an inner one -- mark it to skip.
    marked: set[tuple[str, str]] = set()
    for i in range(1, len(layer_order)):
        lower = layer_order[i]
        upper_len = len(layer_order[i - 1])
        k0 = 0
        scan = 0
        last = len(lower) - 1
        for l1, v in enumerate(lower):
            inner_u = (
                next((u for u in upper[v] if u in dummies), None)
                if v in dummies
                else None
            )
            if l1 == last or inner_u is not None:
                k1 = pos[inner_u] if inner_u is not None else upper_len - 1
                while scan <= l1:
                    for u in upper[lower[scan]]:
                        if pos[u] < k0 or pos[u] > k1:
                            marked.add((u, lower[scan]))
                    scan += 1
                k0 = k1

    root = {v: v for row in layer_order for v in row}
    align = {v: v for row in layer_order for v in row}
    for i in range(1, len(layer_order)):
        r = -1
        for v in layer_order[i]:
            ups = upper[v]
            d = len(ups)
            if d == 0:
                continue
            for m in ((d - 1) // 2, d // 2):  # one (odd) or two (even) medians
                if align[v] == v:
                    u = ups[m]
                    if (u, v) not in marked and r < pos[u]:
                        align[u] = v
                        root[v] = root[u]
                        align[v] = root[u]
                        r = pos[u]
    return _bk_compaction(layer_order, root, align, node_h, v_gap)


def _brandes_koepf(layers, up_adj, down_adj, node_h, v_gap, dummies):
    """Cross-axis (y) coordinate per node via Brandes-Köpf, four runs averaged.

    Runs the alignment from all four corners -- {align upward, downward} x
    {pack leftward, rightward} -- and averages them, which cancels each single
    corner's diagonal drift while keeping straight runs aligned. Averaging is
    deliberate over Brandes-Köpf's median-of-two combination: the median can
    take its two middle values from *different* runs for two adjacent nodes,
    distorting their separation, whereas the mean treats the four uniformly.

    A final legalization sweep then enforces the within-layer gap in row order.
    The class-offset compaction in a single run can occasionally under-separate
    (even reorder) two same-layer neighbours, and the average inherits that; the
    sweep guarantees an overlap-free result. It is a no-op on every layer the
    runs already separated -- the common case -- so it does not perturb the
    aligned, symmetric placements.
    """
    sorted_layers = sorted(layers)
    order = [layers[lyr] for lyr in sorted_layers]
    if not order:
        return {}

    def reflect(rows):
        return [row[::-1] for row in rows]

    runs = [
        (order, up_adj, 1),  # align up,   pack one way
        (reflect(order), up_adj, -1),  # align up,   pack the other
        (order[::-1], down_adj, 1),  # align down, pack one way
        (reflect(order[::-1]), down_adj, -1),  # align down, pack the other
    ]
    coords = [
        {v: sign * val for v, val in _bk_run(o, adj, node_h, v_gap, dummies).items()}
        for o, adj, sign in runs
    ]
    yc = {v: sum(c[v] for c in coords) / len(coords) for row in order for v in row}

    for row in order:
        for above, below in zip(row, row[1:]):
            need = node_h[above] / 2 + v_gap + node_h[below] / 2
            if yc[below] - yc[above] < need:
                yc[below] = yc[above] + need
    return yc


def _assign_coordinates(
    layers, up_adj, down_adj, node_w, node_h, h_gap, v_gap, x_offset, y_offset, dummies
):
    """Stage 3 -- assign pixel coordinates to the ordered layers.

    Columns go left to right (column width = widest node in the layer). The
    vertical (cross-axis) coordinate comes from :func:`_brandes_koepf`, which
    keeps straight runs aligned. Returns ``(positions, centers, col_x, col_w)``
    -- ``positions`` are top-left corners and ``centers`` are node centres (the
    latter reused for edge routing).
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

    yc = _brandes_koepf(layers, up_adj, down_adj, node_h, v_gap, dummies)

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
            positions[nid] = {
                "x": int(elem_x),
                "y": int(round(cy - h / 2)),
                "w": w,
                "h": h,
            }
    return positions, centers, col_x, col_w


def _insert_dummies(node_layer, flows):
    """Turn the layered graph into a *proper* one: every segment joins adjacent
    layers.

    For each flow spanning more than one layer -- a forward skip or a back-edge
    (which spans backwards) -- insert one dummy vertex per interior layer and
    chain unit segments through them, always low-layer to high-layer so the
    chain runs with the left-to-right flow. The dummies then take part in
    ordering and coordinate assignment like any node, which is what lets the
    edge thread between the shapes it crosses (the formal Sugiyama model).

    Adjacent forward hops (span 1) join the ``unit_edges`` directly; adjacent
    back-edges, same-layer edges and self-loops have no interior layer to thread
    and are left for :func:`_route_edges` to lane.

    Returns ``(unit_edges, dummy_layer, chains)``: the adjacent-layer segment
    list, the ``{dummy_id: layer}`` map of the inserted zero-area points, and
    ``{flow_index: [dummy_id, ...]}`` ordered by ascending layer.
    """
    unit_edges: list[dict] = []
    dummy_layer: dict[str, int] = {}
    chains: dict[int, list[str]] = {}
    for idx, flow in enumerate(flows):
        a, b = flow.get("source"), flow.get("target")
        if a not in node_layer or b not in node_layer:
            continue
        span = node_layer[b] - node_layer[a]
        if abs(span) <= 1:
            if span == 1:  # adjacent forward hop; back/same-layer go to a lane
                unit_edges.append({"source": a, "target": b})
            continue
        lo_node, hi_node = (a, b) if span > 0 else (b, a)
        lo, hi = node_layer[lo_node], node_layer[hi_node]
        chain: list[str] = []
        prev = lo_node
        for lyr in range(lo + 1, hi):
            d = f"__d{idx}_{lyr}"
            dummy_layer[d] = lyr
            unit_edges.append({"source": prev, "target": d})
            chain.append(d)
            prev = d
        unit_edges.append({"source": prev, "target": hi_node})
        chains[idx] = chain
    return unit_edges, dummy_layer, chains


def _sugiyama_layout(
    elements_by_id, flows, h_gap=80, v_gap=50, x_offset=50, y_offset=50
):
    """Compute a layered (Sugiyama-style) node placement.

    Runs the placement stages, each delegated to a helper, to keep nodes from
    stacking on top of one another:

    1. :func:`_assign_layers` -- cycle break + longest-path layering + balance.
    2. :func:`_order_layers` -- median sweeps + transpose to reduce crossings.
    3. :func:`_assign_coordinates` -- columns left to right, Brandes-Köpf y.

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
        ``{id: {"x", "y", "w", "h"}}`` (top-left corners) and *ctx* carries the
        routing metadata (``centers``, ``col_x``/``col_w`` column geometry,
        ``node_layer`` and the ``back_edges`` set of cycle-closing
        ``(source, target)`` pairs).
    """
    empty_ctx = {
        "centers": {},
        "col_x": {},
        "col_w": {},
        "node_layer": {},
        "back_edges": set(),
        "chains": {},
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

    # Make the graph proper: long edges become unit segments through dummy
    # vertices, so ordering and coordinate assignment see only adjacent-layer
    # edges and the dummies thread the long edges between the shapes they cross.
    unit_edges, dummy_layer, chains = _insert_dummies(node_layer, flows)
    aug_layer = {**node_layer, **dummy_layer}

    node_w = {nid: elements_by_id[nid]["w"] for nid in real_ids}
    node_h = {nid: elements_by_id[nid]["h"] for nid in real_ids}
    for d in dummy_layer:  # dummies are zero-area routing points
        node_w[d], node_h[d] = 0, 0

    layers, up_adj, down_adj = _order_layers(aug_layer, unit_edges)

    positions, centers, col_x, col_w = _assign_coordinates(
        layers,
        up_adj,
        down_adj,
        node_w,
        node_h,
        h_gap,
        v_gap,
        x_offset,
        y_offset,
        set(dummy_layer),
    )

    ctx = {
        "centers": centers,
        "col_x": col_x,
        "col_w": col_w,
        "node_layer": node_layer,
        "back_edges": back_edges,
        "chains": chains,
    }
    return positions, ctx


def _loop_waypoints(src, tgt, lane_y):
    """Route a degenerate loop as a U through the *lane_y* corridor.

    Used only for back-edges between adjacent (or the same) layers and
    self-loops -- the cases with no interior layer for a dummy to thread. A
    straight route would cut back across the columns, so the edge drops into a
    dedicated lane below the diagram; the caller picks a distinct *lane_y* per
    edge so lanes do not overlap.
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


def _simplify(pts):
    """Drop interior points that lie on the straight segment between their
    neighbours -- a bend the client would draw anyway. A straightened skip
    collapses to its two anchors (no interior points at all)."""
    if len(pts) <= 2:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = out[-1]  # last *kept* point
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        if abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) > 1e-6:
            out.append(pts[i])
    out.append(pts[-1])
    return out


def _route_edges(positions, ctx, flows, strategy):
    """Compute waypoint polylines for *flows*, keyed by flow index.

    Returns ``{index: [(x, y), ...]}``; each polyline includes its end anchors.

    Routing follows the *proper graph*: a long edge is a chain of unit segments
    through its dummy vertices (``ctx["chains"]``), and **every** unit segment --
    a real adjacent-layer edge or one link of a dummy chain -- is routed by the
    same rule. A height-changing segment turns through a vertical channel in its
    column gap; segments sharing an endpoint (a split source ``a`` or a join
    target ``b``) bundle onto one channel, so a gateway's whole fan -- short
    branches and long skips alike -- rides a single trunk instead of stacking
    separate overlapping stubs. A flat segment is a straight line.

    ``strategy`` only changes a *flat, single-segment* real edge: ``"sparse"``
    (PNML) leaves it waypoint-free (``[]``) for the client to draw straight,
    ``"full_ortho"`` (BPMN) emits its two anchors explicitly. Degenerate loops a
    dummy cannot help -- self-loops and back-edges between adjacent (or the same)
    layers -- go through a horizontal lane below the diagram.

    A final *port* pass (:func:`_assign_ports`, below) then offsets each
    back-edge's dock off the node centre, so an incoming back-edge never lands on
    the point a node's forward edges use (which rendered as one line with an
    arrowhead at each end). Forward edges keep the centre -- their fan stays a
    single comb.
    """
    centers = ctx["centers"]
    col_x = ctx["col_x"]
    col_w = ctx["col_w"]
    node_layer = ctx["node_layer"]
    chains = ctx["chains"]

    def _span(flow):
        """Layer distance target - source, or None if an endpoint is missing."""
        src, tgt = flow.get("source"), flow.get("target")
        if src not in node_layer or tgt not in node_layer:
            return None
        return node_layer[tgt] - node_layer[src]

    # Decompose every routed edge into the proper graph's unit (adjacent-layer)
    # segments: the real endpoints plus the edge's dummy vertices, ordered low
    # layer to high. A span-1 edge is one segment; a long edge (forward skip or
    # back-edge) is its dummy chain. ``seg_lists`` keeps each flow's segments in
    # ascending-layer order for re-assembly; ``segs_by_gap`` groups the
    # height-changing ones by column gap for channel assignment.
    seg_lists: dict[int, list] = {}
    segs_by_gap: dict[int, list] = defaultdict(list)
    for idx, flow in enumerate(flows):
        span = _span(flow)
        if span is None or -1 <= span <= 0:
            continue  # unrouted, or a degenerate loop (laned below)
        src, tgt = flow["source"], flow["target"]
        path = (
            [src, *chains.get(idx, []), tgt]
            if span > 0
            else [tgt, *chains.get(idx, []), src]
        )
        lo_layer = node_layer[path[0]]
        segs = []
        for i, (a, b) in enumerate(zip(path, path[1:])):
            seg = {
                "a": a,
                "b": b,
                "layer": lo_layer + i,
                "y1": centers[a][1],
                "y2": centers[b][1],
                "channel": None,
                # A back-edge is laid out reversed (low->high), so at a node its
                # segment looks like an out-segment but is really the incoming
                # arc. Carry the flag so channel bundling never merges an
                # incoming back-edge with that node's real outgoing arcs.
                "back": span < 0,
            }
            segs.append(seg)
            if abs(seg["y1"] - seg["y2"]) >= 1:
                segs_by_gap[seg["layer"]].append(seg)
        seg_lists[idx] = segs

    # Assign a vertical channel per gap. A gateway's fan (segments sharing a
    # source/split or target/join) bundles onto ONE shared trunk -- this is the
    # clean orthogonal "comb" the fat client produces, for both BPMN and PNML.
    # (Giving every arc its own channel instead staggers the branches into
    # crooked steps, so it is not done.) The key includes the edge's real
    # direction (``back``) so an incoming back-edge never shares a node's
    # outgoing trunk -- which made the node look mid-line instead of an endpoint.
    for lyr, segs in segs_by_gap.items():
        gap_lo = col_x[lyr] + col_w[lyr]
        gap_hi = col_x[lyr + 1]
        out_count: dict[tuple, int] = defaultdict(int)
        in_count: dict[tuple, int] = defaultdict(int)
        for s in segs:
            out_count[(s["a"], s["back"])] += 1
            in_count[(s["b"], s["back"])] += 1
        bundles: dict[tuple, list] = {}
        for s in segs:
            if in_count[(s["b"], s["back"])] > 1:
                key = ("in", s["b"], s["back"])
            elif out_count[(s["a"], s["back"])] > 1:
                key = ("out", s["a"], s["back"])
            else:
                key = ("single", id(s))
            bundles.setdefault(key, []).append(s)
        kind_rank = {"out": 0, "single": 1, "in": 2}

        def _bundle_key(key):
            ys = [(s["y1"] + s["y2"]) / 2 for s in bundles[key]]
            return (kind_rank[key[0]], sum(ys) / len(ys))

        ordered = sorted(bundles, key=_bundle_key)
        count = len(ordered)
        for i, key in enumerate(ordered):
            channel = gap_lo + (i + 1) * (gap_hi - gap_lo) / (count + 1)
            for s in bundles[key]:
                s["channel"] = channel

    def _seg_points(s):
        """Orthogonal points for one segment, low-layer (left) end first."""
        ax = positions[s["a"]]["x"] + positions[s["a"]]["w"]  # right of a
        bx = positions[s["b"]]["x"]  # left of b
        if s["channel"] is None:  # flat -> straight
            return [(ax, s["y1"]), (bx, s["y2"])]
        ch = s["channel"]
        return [(ax, s["y1"]), (ch, s["y1"]), (ch, s["y2"]), (bx, s["y2"])]

    bottom_y = max((p["y"] + p["h"] for p in positions.values()), default=0)

    def _loop_span(idx):
        src = positions[flows[idx]["source"]]
        tgt = positions[flows[idx]["target"]]
        return abs((src["x"] + src["w"]) - tgt["x"])

    # Degenerate loops (self-loops and back-edges between adjacent or the same
    # layer) have no interior layer to thread, so each gets its own lane below
    # the diagram; narrower loops take the shallower lanes so wider ones nest
    # underneath.
    loop_indices = sorted(
        (
            i
            for i, flow in enumerate(flows)
            if (_span(flow) is not None and -1 <= _span(flow) <= 0)
            and flow["source"] in positions
            and flow["target"] in positions
        ),
        key=_loop_span,
    )
    loop_lane = {idx: bottom_y + 50 + k * 45 for k, idx in enumerate(loop_indices)}

    routes: dict[int, list] = {}
    for idx, flow in enumerate(flows):
        span = _span(flow)
        if span is None:
            routes[idx] = []
        elif -1 <= span <= 0:
            # Degenerate loop / same-layer: U through its lane below the diagram.
            routes[idx] = (
                _loop_waypoints(
                    positions[flow["source"]], positions[flow["target"]], loop_lane[idx]
                )
                if idx in loop_lane
                else []
            )
        else:
            segs = seg_lists[idx]
            # A flat single-segment real edge: PNML leaves the straight line to
            # the client; BPMN emits its two anchors (handled by re-assembly).
            if strategy == "sparse" and len(segs) == 1 and segs[0]["channel"] is None:
                routes[idx] = []
                continue
            pts: list = []
            for s in segs:
                seg_pts = _seg_points(s)
                if pts and pts[-1] == seg_pts[0]:  # drop the shared dummy junction
                    seg_pts = seg_pts[1:]
                pts.extend(seg_pts)
            if span < 0:  # back-edge: emit the polyline source -> target
                pts.reverse()
            routes[idx] = pts

    routes = {idx: _simplify(pts) for idx, pts in routes.items()}

    # Port assignment. A back-edge docks unconventionally -- its target on the
    # right, its source on the left -- i.e. on the very side a node's forward
    # edges use, so its end stub lands on the forward edge's stub: one line with
    # an arrowhead at both ends. Offset each back-edge's dock off the node centre
    # (toward the side its route bends to, so no jog) and spread several apart;
    # forward edges keep the centre, so their split/join fan (the comb) is intact.
    back = {i for i, f in enumerate(flows) if (_span(f) is not None and _span(f) <= 0)}

    def _assign_ports(rts):
        pts = {idx: [list(p) for p in r] for idx, r in rts.items()}
        docks: dict[tuple, list] = defaultdict(list)
        for idx in back:
            r = pts.get(idx)
            if not r or len(r) < 2:
                continue
            f = flows[idx]
            for end_i, nb_i, node in ((0, 1, f["source"]), (-1, -2, f["target"])):
                if node not in positions:
                    continue
                box = positions[node]
                side = "R" if r[end_i][0] >= box["x"] + box["w"] / 2 else "L"
                docks[(node, side)].append((idx, end_i, nb_i))
        for (node, _side), ends in docks.items():
            box = positions[node]
            cy = box["y"] + box["h"] / 2
            above = sorted(
                (e for e in ends if pts[e[0]][e[2]][1] <= cy),
                key=lambda e: -pts[e[0]][e[2]][1],
            )
            below = sorted(
                (e for e in ends if pts[e[0]][e[2]][1] > cy),
                key=lambda e: pts[e[0]][e[2]][1],
            )
            for group, sign in ((above, -1), (below, 1)):
                step = min(box["h"] / 2 / (len(group) + 1), 16)
                for k, (idx, end_i, nb_i) in enumerate(group):
                    r = pts[idx]
                    # only the usual horizontal dock stub can shift in y
                    if abs(r[end_i][1] - r[nb_i][1]) < 1 and r[end_i][0] != r[nb_i][0]:
                        ny = cy + sign * (k + 1) * step
                        r[end_i][1] = ny
                        r[nb_i][1] = ny
        return {idx: _simplify([tuple(p) for p in r]) for idx, r in pts.items()}

    # Rework-loop entry. A long back-edge already arcs over (or under) the
    # diagram, but it then drops into the gap beside its target and enters the
    # target on the same side its forward flow leaves -- a needless jog plus two
    # near-parallel stubs. Instead let it run on to the target's centre and drop
    # straight into the target's top (or bottom) edge -- the conventional loop
    # look. Only when that vertical approach is clear of every other node; else
    # the side entry from _assign_ports stays.
    long_back = {
        i for i, f in enumerate(flows) if (_span(f) is not None and _span(f) <= -2)
    }
    boxes = {
        nid: (p["x"], p["x"] + p["w"], p["y"], p["y"] + p["h"])
        for nid, p in positions.items()
        if p["w"] and p["h"]
    }

    def _clear(p, q, skip):
        lox, hix = sorted((p[0], q[0]))
        loy, hiy = sorted((p[1], q[1]))
        for nid, (x0, x1, y0, y1) in boxes.items():
            if nid == skip:
                continue
            if hix <= x0 + 2 or lox >= x1 - 2 or hiy <= y0 + 2 or loy >= y1 - 2:
                continue
            return False
        return True

    def _loop_top_entry(rts):
        out = dict(rts)
        for idx in long_back:
            r = rts.get(idx)
            tgt = flows[idx]["target"]
            if not r or len(r) < 3 or tgt not in positions:
                continue
            box = positions[tgt]
            a, b, d = r[-3], r[-2], r[-1]
            # tail must be lane point A -> vertical drop -> horizontal side stub,
            # with A sitting clear above or below the node (not level with it)
            if not (abs(d[1] - b[1]) < 1 and abs(b[0] - a[0]) < 1):
                continue
            cx = box["x"] + box["w"] / 2
            if box["y"] <= a[1] <= box["y"] + box["h"] or abs(a[0] - cx) < 1:
                continue
            edge_y = box["y"] if a[1] < box["y"] + box["h"] / 2 else box["y"] + box["h"]
            p1, p2 = (cx, a[1]), (cx, edge_y)
            if _clear(a, p1, tgt) and _clear(p1, p2, tgt):
                out[idx] = _simplify(list(r[:-2]) + [p1, p2])
        return out

    return _loop_top_entry(_assign_ports(routes))
