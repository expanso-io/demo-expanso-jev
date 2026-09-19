# Agent notes — demo-expanso-jev

Read this before touching credentials, the CLI, or `start.sh`.

## Never put an Expanso secret in a flag

`expanso-cli` and `expanso-edge` both read credentials from the environment.
Use that. A flag value is visible to `ps` under the same uid on macOS, and is
world-readable via `/proc/<pid>/cmdline` on Linux.

```
uv run -s tools/expanso-agent-help.py           # the table, from the installed binaries
uv run -s tools/expanso-agent-help.py --json    # same, machine readable
uv run -s tools/expanso-agent-help.py --probe   # prove it against the live network
```

The three this demo needs, all in `.env` (gitignored, mode 600):

| Variable | Replaces | Note |
|---|---|---|
| `EXPANSO_CLI_ENDPOINT` | `--endpoint` | load-bearing, see below |
| `EXPANSO_CLI_AUTH_API_KEY` | `--api-key` | **not** `EXPANSO_CLI_API_KEY` |
| `EXPANSO_EDGE_BOOTSTRAP_TOKEN` | `bootstrap --token` | |

## The names do not match the flags

`--api-key` is `EXPANSO_CLI_AUTH_API_KEY`, because the env name is derived from
the config key `auth.api_key`, not from the flag. `EXPANSO_CLI_API_KEY` is
silently ignored. Neither name appears in `--help`, and
`EXPANSO_CLI_AUTH_API_KEY` appears nowhere in the published docs either.

This has been reported to Expanso, with a request for an `agent-help` command in
the binaries themselves. Until that ships,
`tools/expanso-agent-help.py` is the stand-in — and it introspects the binary
on PATH rather than hardcoding, so it tracks whatever version is installed.

## A wrong env var does not fail, it answers from the wrong network

This is the trap worth internalising. With an unrecognised env var and no
`--endpoint`, `expanso-cli` falls back to
`~/.expanso/cli-client/profiles/current` — whichever Cloud network was selected
last — and prints a normal-looking `No nodes found`. Nothing warns you.

That is exactly how this demo shipped broken: `start.sh` ran a bare
`expanso-cli job deploy`, the job landed in an unrelated network, sat
`queued / waiting for matching nodes` forever, nothing bound `:8080` locally,
and the readiness probe went green in one second because the *cloud* answered.

Two rules follow:

- **`EXPANSO_CLI_ENDPOINT` is mandatory**, not a convenience. It is what keeps
  the CLI off the global profile.
- **Never assert a negative from a control plane that answered.** Prove the
  instrument sees a known positive first. `start.sh` waits for *our* node id in
  the node list, then POSTs a real probe event and requires `:8080` to answer,
  before the generator fires.

## Credentials stay in this repo

Never write Expanso credentials to `~/.expanso`, and never use a globally
selected CLI profile. The edge agent bootstraps into `.expanso/edge/` here
(`EXPANSO_EDGE_HOME`), which is gitignored along with `.env`.

`expanso-cli` has no equivalent knob — `cli-client` is a hardcoded constant —
which is why the env vars are the only isolation mechanism available on the CLI
side. That gap has been reported too.
