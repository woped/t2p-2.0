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
detouring around the diagram, and the edge's polyline is simply the path through
its dummy centres. Only the degenerate cases a dummy cannot help -- self-loops
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


def _bk_run(layer_order, upper_adj, node_h, v_gap):
    """One Brandes-Köpf alignment + compaction for a given graph orientation.

    *layer_order* is the layer stack top-to-bottom in this run's vertical
    direction; *upper_adj* maps each node to its neighbours in the previous
    layer of that orientation. Each node aligns to its median upper neighbour
    (left to right, so alignments never cross). Returns a cross-axis coordinate
    per node.
    """
    pos = {v: j for row in layer_order for j, v in enumerate(row)}
    upper = {
        v: sorted(upper_adj.get(v, ()), key=lambda u: pos[u])
        for row in layer_order
        for v in row
    }

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
                    if r < pos[u]:
                        align[u] = v
                        root[v] = root[u]
                        align[v] = root[u]
                        r = pos[u]
    return _bk_compaction(layer_order, root, align, node_h, v_gap)


def _brandes_koepf(layers, up_adj, down_adj, node_h, v_gap):
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
        {v: sign * val for v, val in _bk_run(o, adj, node_h, v_gap).items()}
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
    layers, up_adj, down_adj, node_w, node_h, h_gap, v_gap, x_offset, y_offset
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

    yc = _brandes_koepf(layers, up_adj, down_adj, node_h, v_gap)

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


def _orthogonalize(pts):
    """Square off any diagonal segment into a horizontal+vertical pair, bending
    at the mid-x (which, between adjacent columns, falls in the column gap so the
    vertical leg clears every shape). A no-op on already-orthogonal routes."""
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if abs(x0 - x1) > 1 and abs(y0 - y1) > 1:
            mx = (x0 + x1) / 2
            out.append((mx, y0))
            out.append((mx, y1))
        out.append((x1, y1))
    return out


def _route_edges(positions, ctx, flows, strategy):
    """Compute waypoint polylines for *flows*, keyed by flow index.

    Returns ``{index: [(x, y), ...]}``; each polyline includes its end anchors.
    ``strategy``:
      * ``"full_ortho"`` -- route every adjacent-layer edge orthogonally (BPMN's
        convention). Vertical risers live in the gaps between columns (one
        channel per riser) and edges sharing a split source or join target
        bundle onto a shared channel.
      * ``"sparse"`` -- route only what a straight line cannot draw cleanly:
        adjacent-layer edges whose endpoints sit at different heights (a
        split/join fan, which a straight line would draw as a diagonal). Flat
        adjacent-layer edges stay straight (``[]``) -- correct and native for
        PNML.
    Edges spanning more than one layer thread through their dummy chain
    (``ctx["chains"]``): the polyline is their dummy centres, which ordering and
    coordinate assignment placed between the shapes the edge crosses. Only
    degenerate loops a dummy cannot help -- back-edges between adjacent (or the
    same) layers and self-loops -- go through a horizontal lane below the
    diagram, regardless of strategy.

    Two passes finish every route, in both strategies: each long edge's diagonal
    ramps are squared into Manhattan segments (verticals fall in the column gaps,
    so an arc never cuts through a shape its dummy was placed to clear), then any
    bend point collinear with its neighbours is dropped, so no route stores a
    segment the client would draw on its own.
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

    # Single adjacent-layer hops (span 1). Their height-changing members each get
    # a vertical channel in the column gap; the rest are straight lines. Spans of
    # >= 2 layers and loops route through lanes below (handled further down).
    hop_by_flow: dict[int, dict] = {}
    for idx, flow in enumerate(flows):
        if _span(flow) == 1:
            src, tgt = flow["source"], flow["target"]
            hop_by_flow[idx] = {
                "a": src,
                "b": tgt,
                "layer": node_layer[src],
                "y1": centers[src][1],
                "y2": centers[tgt][1],
                "channel": None,
            }

    def _routed_hop(idx):
        """Whether single-hop flow *idx* gets a route, vs being left straight."""
        hop = hop_by_flow.get(idx)
        if hop is None:
            return False
        if strategy == "full_ortho":
            return True
        # Route a single hop only when it changes height (a split/join fan); a
        # flat hop is a clean straight line, left to ``[]``.
        return abs(hop["y1"] - hop["y2"]) >= 1

    # Every height-changing routed hop needs a vertical channel in its column
    # gap; collect them per gap (skipping hops left straight).
    risers_by_gap: dict[int, list] = defaultdict(list)
    for idx, hop in hop_by_flow.items():
        if _routed_hop(idx) and abs(hop["y1"] - hop["y2"]) >= 1:
            risers_by_gap[hop["layer"]].append(hop)

    for lyr, hops in risers_by_gap.items():
        gap_lo = col_x[lyr] + col_w[lyr]
        gap_hi = col_x[lyr + 1]
        # Edges sharing a target (a join) or a source (a split) collapse onto one
        # shared channel, so they turn at the same x and meet at a single point
        # instead of stair-stepping. Other hops each get their own.
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
        # Lay channels left-to-right: splits near their source, joins near their
        # target, singletons between; break ties by mean height.
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

    def _dummy_route(idx, span, flow):
        """Polyline of a long edge: its dummy centres, plus the end anchors.

        Dummy ids in ``chains[idx]`` run low-layer to high-layer; a back-edge
        (span < 0) walks them in reverse so the polyline still reads source to
        target. The edge exits the side of the source that faces the target and
        enters the matching side of the target.
        """
        src, tgt = flow["source"], flow["target"]
        sp, tp = positions[src], positions[tgt]
        seq = chains[idx] if span > 0 else list(reversed(chains[idx]))
        if span > 0:
            exit_pt = (sp["x"] + sp["w"], centers[src][1])
            entry_pt = (tp["x"], centers[tgt][1])
        else:
            exit_pt = (sp["x"], centers[src][1])
            entry_pt = (tp["x"] + tp["w"], centers[tgt][1])
        return [exit_pt, *(centers[d] for d in seq), entry_pt]

    routes: dict[int, list] = {}
    for idx, flow in enumerate(flows):
        span = _span(flow)
        if span is None:
            routes[idx] = []
        elif abs(span) >= 2:
            # Long edge: thread through its dummy chain (forward skip or loop).
            routes[idx] = _dummy_route(idx, span, flow)
        elif span <= 0:
            # Degenerate loop / same-layer: U through its lane below the diagram.
            routes[idx] = (
                _loop_waypoints(
                    positions[flow["source"]], positions[flow["target"]], loop_lane[idx]
                )
                if idx in loop_lane
                else []
            )
        elif not _routed_hop(idx):
            routes[idx] = []  # flat adjacent hop, left straight (sparse)
        else:
            src, tgt = flow["source"], flow["target"]
            hop = hop_by_flow[idx]
            exit_pt = (positions[src]["x"] + positions[src]["w"], centers[src][1])
            entry_pt = (positions[tgt]["x"], hop["y2"])
            if abs(hop["y1"] - hop["y2"]) < 1:
                routes[idx] = [exit_pt, entry_pt]
            else:
                channel = hop["channel"]
                routes[idx] = [
                    exit_pt,
                    (channel, hop["y1"]),
                    (channel, hop["y2"]),
                    entry_pt,
                ]

    # Square off each long edge's diagonal ramps into its routing lane: a direct
    # diagonal can cut straight through the very shape the dummy was placed to
    # clear, whereas Manhattan legs keep verticals in the column gaps and
    # horizontals at the (cleared) dummy-lane heights. Risers and loops are
    # orthogonal already, so only the dummy chains need it. Then drop every bend
    # point collinear with its neighbours, so no route carries a segment the
    # client would draw on its own (a straightened skip keeps no interior points).
    for idx, pts in routes.items():
        if idx in chains:
            pts = _orthogonalize(pts)
        routes[idx] = _simplify(pts)
    return routes
