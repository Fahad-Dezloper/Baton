# Demo video script (target 2:30)

One person, one screen recorder. Two windows: a terminal (left) and a browser (right) with the
FalkorDB Browser open at http://localhost:3000 on graph `baton_demo`. The demo prints its own
output; read the lines that appear, do not promise exact wording. Speak plainly; no claims beyond
docs/RESULTS.md.

## Pre-flight checklist
- [ ] `docker compose up -d` done; `docker ps` shows falkordb on 6379 and 3000.
- [ ] `.venv` exists and `.venv/bin/pip install -e .` has run.
- [ ] Do a full dry run: `.venv/bin/python demo/run_demo.py` (it drops and rebuilds graph `baton_demo`, so
      you can re-run it live). Note how long it takes; if over 20 seconds, record the run once and cut.
- [ ] Browser tab open on localhost:3000, graph `baton_demo` selected. Paste queries 1, 4 and 5 from
      `demo/queries.cypher` into separate tabs/snippets so you only press run.
- [ ] Terminal font 18-20 pt, window about 100 columns, clear scrollback, dark theme, no notifications.
- [ ] Nothing personal on screen: home path in the prompt, tokens, email, other tabs, bookmarks bar.
- [ ] Have docs/RESULTS.md table ready as the closing slide (a screenshot or a plain markdown preview).
- [ ] Record at 1080p, mic test, close Slack/Messages.

## Shots

| Time | Show | Say |
|---|---|---|
| 0:00-0:15 | Title text: "baton: a shared graph for parallel Claude Code sessions. Track 2." | "When several coding sessions work on one repository, they collide silently. One changes a function signature, another builds on the old one, and the next day's session starts from nothing. baton keeps a FalkorDB graph of who is working on what and what was decided." |
| 0:15-0:30 | Terminal: `.venv/bin/python demo/run_demo.py` (press enter; output scrolls). | "This script drives the same hook handlers the plugin uses, with the same payloads. No model, no API key. Two sessions start on the same checkout." |
| 0:30-0:55 | Output section 2: session A edits `shop/db.py`; the "recorded without anyone typing a command" list. | "Session A changes a function signature and brings in sqlite. Nobody typed a command. The decisions were derived from the edit itself, and stored in the graph." |
| 0:55-1:20 | Output sections 3 and 4: warnings to session B. | "Session B is about to edit a different file that imports db. The hook asked the graph for recent changes to files it imports, and told B. If B goes for the same file as A, it gets a collision notice with A's lease." |
| 1:20-1:40 | Output section 5: next-day session C briefing. | "A stops and writes a handoff. A new session the next day starts with a briefing built from the graph, not from a transcript." |
| 1:40-2:05 | Browser: run query 1 (whole picture), then query 5 (blast radius). Point at the finding, the tainted decisions. Terminal section 6 visible briefly. | "Here is the graph. Sessions touch files, decisions are about files and are based on other decisions or findings. This finding turned out wrong. One variable-length BASED_ON traversal finds everything derived from it, and retract marks those decisions tainted. That is the part that needs a graph." |
| 2:05-2:30 | Evaluation slide: the table from docs/RESULTS.md (Baseline 12/25, v3 14/25; failed checks 1.87 to 0.87). | "Does it help? We ran real parallel sessions, five trials per cell, three rounds. The share of fully collision-free trials did not change significantly: 14 of 25 against 12 of 25. Failed checks per trial fell from 1.87 to 0.87, but after three rounds of tuning on the same tasks, so that is suggestive, not proven. Duplicate tickets are not solved, and one level got worse. The mechanism works; the outcome claim is modest. Everything is in the repo. The code was built with an AI coding assistant, disclosed in the README." |

## 30-second fallback cut
Use if the live demo misbehaves or time is short. Pre-record the terminal output once, then show only:
1. (0:00-0:08) Title and one sentence of the problem.
2. (0:08-0:18) Terminal output sections 3-4 (the warnings), voiceover: "Before an edit, the hook queries
   FalkorDB for live leases and recent decisions on related files, and warns the session."
3. (0:18-0:30) The evaluation table: "In our tests this did not significantly change the
   collision-free rate (14/25 vs 12/25); failed checks per trial fell from 1.87 to 0.87, suggestive
   only. Details in docs/RESULTS.md."

## If something goes wrong on camera
- Script errors with connection refused: FalkorDB is not up; `docker compose up -d`, wait 3 seconds.
- Browser shows no graph: reload and re-select `baton_demo`; the script recreates it on every run.
- Never fake output. If a section prints differently than described here, narrate what is on screen.
