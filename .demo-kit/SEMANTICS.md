# Semantic conventions

Kit-wide rules for colors, tokens, and icons.

## Token meanings

Color is meaning across every demo. A lane, its destination border, and its count share one token.

| Token | Meaning | Typical elements |
|---|---|---|
| `--accent` | Expanso control and decided lanes | Expanso edge nodes, Cloud control plane, decided routes |
| `--ok` | Landed, saved, acknowledged | Landed rows, archive borders, success counts, saved costs |
| `--warn` | Raw, pending, candidate, waiting | Ingest backlog, pending candidates, unindexed raw queues |
| `--err` | Cut, down, bypass cost | Severed links, offline nodes, bypass expenses, error states |
| `--kept` | Retained locally | First-pass data kept on device, local buffer storage |

## Icon assignments

The concepts below take their icons from `showcase/icons.svg`; other icons and subject graphics follow the sourcing ladder in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md#icons-and-illustrations--showcaseiconssvg-first). Place each icon beside the label it qualifies at `1em` in `currentColor`. Use the same icon for the same concept everywhere.

| Concept | Icon ID | Usage |
|---|---|---|
| Cloud | `cloud` | Expanso Cloud control pills and cloud destinations |
| Edge | `bolt` | Expanso Edge nodes and processing steps |
| Index | `database` | Search index, operational database destinations |
| Archive | `save` | Object storage and long-term archive sinks |
| Money | `cost` | Annual cost shelf, cloud egress expense |
| Link | `signal` | RF links, peer mesh connectivity, network status |
| Anomaly | `alert` | Sensor anomalies, rule violations, priority events |
| Look closer | `scan` | Vision ROI zoom, high-resolution inspection |
| Window | `clock` | Scheduled link windows, countdown timers |
