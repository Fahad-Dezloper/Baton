# Parallel coding sessions need a shared graph, and our test said it only half works

*Written for the WeMakeDevs x FalkorDB "Graph Hacks: Context for AI Agents" hackathon, Track 2 (Agent Memory and Coordination).*

If you run two or three Claude Code sessions on one repository at the same time, they will step on each other. Not dramatically. Quietly. One session changes `get_order(order_id)` to take an extra flag. Another is writing an endpoint against the old signature. A third picks the same ticket as the first because both were pasted the same text. The next morning, a fresh session knows none of this.

baton is my attempt at the smallest useful fix: a shared graph in FalkorDB that every session writes to and reads from, delivered through Claude Code hooks so nobody has to remember a command. This post covers what the graph holds, why it needs to be a graph, one example from the demo, and the part I think matters more than the tool: what happened when I tried to measure whether it helps.

## What the graph models

One graph per workspace. Six node types and seven relationships:

- `Actor`, and a `Task` per session (a leased claim on "what I am doing"). `Task -[:TOUCHES]-> Artifact` records the files a session is editing.
- `Decision` nodes, such as "added parameter include_cancelled to get_order" or "added dependency sqlite3", linked `-[:ABOUT]->` the file they concern. `Actor -[:DECIDED]-> Decision` records authorship.
- `Finding` nodes for facts a decision rests on, and `Decision -[:BASED_ON]-> Decision|Finding` for provenance. `SUPERSEDES` links replacements.
- `Handoff -[:INCLUDES]->` the tasks, decisions, findings and files a next session should know about.

Decisions are not typed by a human. On each file edit, a hook looks at the edit payload and derives interface, config, dependency and rename changes with plain code, no model call. Model output never becomes Cypher; all queries are named and parameterized.

## Why FalkorDB, and why a graph

The questions I wanted to ask are graph-shaped:

- Who holds a live lease on a file I am about to edit? One hop, `TOUCHES`.
- What did others change in files near, or imported by, this one? `Decision -> Artifact`, filtered by path neighbourhood.
- What was this decision based on, and what breaks if that fact is wrong? A variable-length traversal over `BASED_ON`.
- Which tasks are ready? Tasks whose `DEPENDS_ON` neighbours are all done.

The third is the one a flat table is worst at. A finding turns out wrong; every decision derived from it, transitively, should be flagged. That is `MATCH (f:Finding {id: $id})<-[:BASED_ON*1..8]-(d:Decision) RETURN DISTINCT d`.

FalkorDB also gave me something I needed for coordination: writes to one graph are serialized, so a claim written as a single `MATCH ... WHERE ... SET ... RETURN` statement has at most one winner. I verified this with a race test and, importantly, a negative control (see `docs/SPIKES.md`). It also runs in one Docker container, which kept the hackathon setup honest.

## One concrete example from the demo

`demo/run_demo.py` drives the real hook handlers with real payload shapes, without a model. Two sessions start on the same checkout. Session A edits `shop/db.py`, changes the signature of `get_order`, and imports sqlite3. Nobody types anything; two decisions appear in the graph.

Session B then goes to edit `shop/api.py`, a different file that imports `db`. Before the edit, the hook queries for recent decisions on files B's file imports, and B is told that A changed `get_order` and the storage engine. If B instead edits `db.py`, it gets a same-file notice that A holds a live lease. When A stops, it writes a handoff, and a new session the next day starts with a briefing built from the graph. Finally the demo records a finding ("orders must survive restarts"), two decisions derived from it, then retracts the finding. The `BASED_ON` traversal marks both decisions as tainted. You can see all of it in the FalkorDB Browser with the queries in `demo/queries.cypher`.

## Did it work? Mixed, and the details matter

I tested with real parallel sessions of a cheap model: sessions start at the same moment on one shared checkout, with overlapping tickets, scored by a scripted checker for collision-free results. Five trials per cell, three rounds, seven levels of increasing difficulty. Everything is in `docs/RESULTS.md`.

- **Round 1: no improvement.** The plugin got 9/25 collision-free trials against 12/25 for the baseline on levels 1-5. Hooks fired, sessions acknowledged the warnings, and outcomes did not improve. Delivery is not the same as help.
- **Why, from the logs:** sessions start together so briefings were empty; warnings only fired on the same file, but many failures were cross-file contract mismatches; the duplicate-ticket warning told sessions to "coordinate", which they cannot do.
- **Rounds 2 and 3:** I fixed those (cross-file digest, a designated session for duplicate tickets, better wording, keeping the end of long prompts so the ticket is not cut off). Final: 14/25 against 12/25 collision-free (Fisher p = 0.78, not significant). Failed checks per trial on the three hardest levels fell each round, 1.87, 1.60, 1.20, 0.87, with a final p of 0.045, but that is after three rounds of tuning on the same tasks, so I treat it as suggestive.
- **Negative results I want on the record:** duplicate-ticket tasks are still 0/5. Level 2 got worse (3/5 against 5/5), and I did not investigate. In round 2, sessions sometimes read a collision warning as "this ticket is taken" and did nothing, losing a whole session's work in two trials. One level (L6) was edited after I saw results, so it no longer counts as held out. The seventh level, untouched, went 5/5 against 5/5.

## What it taught me about measuring multi-session tools

Run-to-run variance was large: the same baseline on level 1 had no clashes in an earlier in-process run and 4/5 in the containerised one. With five trials a cell, you cannot see modest effects. Counting "failed checks" is more sensitive than pass/fail, but it is also a second metric you can pick after the fact. Written tasks and scorer by the same person, and tuning on the tested levels, both inflate results; the only protection I found was writing held-out levels and their checkers before seeing results, and then not editing them. Finally, a tool can work perfectly as a mechanism (zero hook errors in 40 v3 trials, 50-130 ms per hook) and still not change outcomes, so I would not accept "warnings were delivered" as evidence from anyone, including me.

## Limits

One model, one fixture project, small samples, three tuning rounds on the same tasks, text-pattern counting for abstention. It is not a general long-term memory system, and the only interface beyond FalkorDB Browser is the plugin. The warnings are advice; a session can ignore them (policy `ask` or `deny` exists but was not what I evaluated).

## Try it

```sh
docker compose up -d
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python demo/run_demo.py
```

Open http://localhost:3000, choose graph `baton_demo`, and run `demo/queries.cypher`. To use it in Claude Code: `claude --plugin-dir ./plugin`. Tests need a running FalkorDB. Repo: `<REPO_URL>`.

## Disclosure

This project was designed and built with substantial help from an AI coding assistant (Claude Code), including code, tests, evaluation harness and documentation. I directed the work and reviewed the results; the numbers above come from runs recorded in the repository, and all data is synthetic or generated by the runs themselves.
