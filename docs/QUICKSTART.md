# Quickstart

Needs: Docker, Python 3.10+, Claude Code. Takes about 2 minutes.

```sh
git clone <repo-url> baton && cd baton
docker compose up -d && python3 -m venv .venv && .venv/bin/pip install -e .   # FalkorDB + baton
.venv/bin/baton doctor && .venv/bin/python demo/run_demo.py                    # check, then scripted demo
```

Then open http://localhost:3000, pick graph `baton_demo`, and run the queries in
`demo/queries.cypher`.

To use it with Claude Code (any project, no other setup):

```sh
claude --plugin-dir /path/to/baton/plugin
```

The plugin launchers find the repo's `.venv` on their own. If that fails, hooks stay silent (they
never block a session) and the MCP tools report an error; run `baton doctor` to see why.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `doctor`: FalkorDB not reachable | container not running, or port 6379 taken by another Redis | `docker compose up -d`; if 6379 is busy, stop the other server or edit the left side of the port in `docker-compose.yml` and set `BATON_FALKORDB_PORT` |
| `doctor`: package not importable | pip install not run, or wrong venv | `python3 -m venv .venv && .venv/bin/pip install -e .` and run `.venv/bin/baton doctor` |
| `pip install` says requires Python >=3.10 | old `python3` | use `python3.11` (or newer) to create the venv |
| `baton: command not found` | venv not activated | use `.venv/bin/baton` or `source .venv/bin/activate` |
| Plugin loaded but nothing happens, no graph appears | hooks failed open (store down, or no Python with baton) | `baton doctor`; set `BATON_DEBUG_LOG=/tmp/baton.log` and look for `error` lines |
| Demo prints nothing about Browser graphs | Browser shows only existing graphs | run the demo first, then reload http://localhost:3000 |
| Demo clobbers my graph `baton_demo` | the demo drops and recreates its workspace | `BATON_DEMO_WORKSPACE=mydemo .venv/bin/python demo/run_demo.py` |
| Hooks use the wrong Python | several interpreters on the machine | `export BATON_PYTHON=/path/to/python` (needs baton + falkordb installed) |

Launcher order for finding Python: `$BATON_PYTHON`, `<repo>/.venv`, the interpreter of the `baton`
command on PATH, then `python3`/`python` if they can import baton and falkordb.

## Add baton to an existing project

Nothing is installed into the project. Start Claude Code in it with the plugin directory:

```sh
cd ~/my-project
claude --plugin-dir /path/to/baton/plugin
```

Each project directory gets its own graph (`baton_<dirname>-<hash>`). Optional per-project settings
go in `.baton.json` (`policy`: `warn` | `ask` | `deny`, `lease_seconds`, `capture`, `enabled`). To
see what fired: `BATON_DEBUG_LOG=/tmp/baton.log claude --plugin-dir ...` and read the file; one line per
hook event.

## Turn it off

- One session: start Claude Code without `--plugin-dir`.
- One project: put `{"enabled": false}` in `.baton.json`.
- Everywhere, for a shell: `export BATON_DISABLED=1`.
- Remove data: delete the graph in the Browser, or `docker compose down -v`.

## Remote FalkorDB

```sh
export BATON_FALKORDB_HOST=db.example.com
export BATON_FALKORDB_PORT=6379
.venv/bin/baton doctor
```

Set these in the environment Claude Code is started from; hooks and the MCP server inherit them.
Connections are plain Redis protocol with short timeouts (1 s connect for hooks); passwords and TLS
are not configurable yet, so use a private network or a tunnel (`ssh -L 6379:localhost:6379 host`).
