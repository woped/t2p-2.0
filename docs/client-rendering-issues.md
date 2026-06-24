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
