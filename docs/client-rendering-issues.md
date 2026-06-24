# Client rendering issues

Problems on the client side that our layout deliberately does NOT work around.
We lay out for the format (BPMN / PNML) and emit standard-correct geometry; the
clients render it imperfectly. Collected here as we work through the layout step
by step, so they can be fixed client-side or passed on. Keep compact and
problem-oriented.

## PNML clients (WoPeD fat client, woped-next)
- Show the raw element id (e.g. `SILENTFROMxTOy`) as the label for **unnamed**
  nodes (silent places, operator helper transitions). Our output leaves them
  unnamed, as the standard net does; a client should render no label for a
  nameless node, not its internal id.

## woped-next (PNML)
- Parses our arc bend points (`getArcWaypoints` -> `arc.waypoints`) but renders
  them only in `manual` routing mode; on import it sets no mode, so the default
  `'direct'` draws every arc as a straight line -- our loop and multi-layer
  waypoints are read and then ignored. One-line fix: set
  `routingMode = waypoints.length ? 'manual' : 'direct'` when parsing arcs.

## BPMN clients (woped-web / bpmn-js)
- Event and gateway labels render *outside* the shape (`isLabelExternal`), so a
  long event/gateway name can overflow toward a neighbour. We size those nodes
  to the fixed bpmn-js box (a label-wide box would distort the circle/diamond),
  so we deliberately do not reserve label width for them. Rare in practice
  (events sit at the ends, gateway labels fit the column gaps); a client-side
  label-placement concern, not ours to size around.
