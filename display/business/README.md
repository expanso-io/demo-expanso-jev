# display/business — the ops dashboard layer

The working view: live indicator, events/sec, per-route counts, Expanso stages
(SHAPE → COUNT → ROUTE), Jev judgments, chaos controls. Each demo wires its own
`server.py` + `index.html`; shared assets land here.

Selected per run with `DISPLAY_MODE=business` in `.env` (the default).
