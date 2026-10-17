# Submission checklist

Rules re-checked on 2026-10-17 against the live pages
(`wemakedevs.org/hackathons/falkordb`, `/rules`, `/schedule`). Page text was read through a
summarising fetch tool, so wording is paraphrase. Anything not stated on those pages is marked
**NOT PUBLISHED** or **UNVERIFIED**. Re-open the pages yourself before submitting.

## What the live pages say
- Deadline: **October 18, 2026, 11:59 PM IST** (schedule page and event page agree). Hacking began
  October 15, 12:01 AM IST.
- Tracks (name the ones you enter at submission): 1 Agents That Act on Connected Data, 2 Agent
  Memory and Coordination (PS5 with GTA VI), 3 Company Brain. Teams may enter any or all.
- Required items: public source repository; README with setup steps and the graph data model; the
  Cypher queries or graph algorithms the product depends on; demo video; live deployment (preferred)
  or full local setup instructions (a working demo video is then required); the track(s).
- Schedule page also lists "project information" among the materials.
- **Judging criteria: NOT PUBLISHED** (event, rules and schedule pages). Judging and announcement
  dates: NOT PUBLISHED.
- **Submission form fields: NOT PUBLISHED.** The pages do not describe the form; where and how it is
  submitted is UNVERIFIED (registration is via the WeMakeDevs panel; the form may appear only after
  login). Ask in the Discord or contact@wemakedevs.org if you cannot find it.
- **Blog post prize** (AirPods 5, one winner): the pages only say to write a blog post about your
  project. Length, platform, deadline and how to submit the link: NOT PUBLISHED. Publish it publicly
  and put the link in the project information (and in the README) to be safe.
- Differences from our earlier notes: none found. The earlier notes said "AI-assistance: must be
  disclosed"; the rules page confirms that and adds that you must be able to explain the graph model,
  queries, architecture and decisions. The event-page FAQ (as summarised) says you remain responsible
  for the code, architecture, security and correctness. One fetch of the event page reported "no
  explicit disclosure rule"; the rules page does state one. Treat disclosure as required.

## Checklist

| # | Item | Status | Where |
|---|---|---|---|
| 1 | Public source repo | USER: make the repo public (first commit is 2026-10-15 13:27 IST, after the start) | GitHub |
| 2 | README with setup + graph data model | Done (data model table, key Cypher, quickstart). Lead to merge final README, add LICENSE line and links | README.md |
| 3 | Cypher queries the product depends on | Done: README excerpts, `src/baton/graph/queries.py`, `demo/queries.cypher` | repo |
| 4 | Demo video | Script ready; USER records | docs/VIDEO-SCRIPT.md |
| 5 | Live deployment or local setup | Local setup only (docker compose + pip). No hosted deployment exists; the video is therefore required | README |
| 6 | Track(s) | Track 2 (see below) | form |
| 7 | Project information (form fields) | Text proposed below | form |
| 8 | Blog post | Draft ready; USER publishes it (dev.to, Medium, personal site) and picks the link | docs/BLOG.md |
| 9 | LICENSE | Done (MIT, holder placeholder "baton authors", lead to confirm) | LICENSE |
| 10 | AI-assistance disclosure | In README; repeat in form and blog | README, blog |

## What the user must do personally
1. Make the GitHub repo public and confirm no secrets or private paths are in history.
2. Record and upload the demo video (YouTube unlisted or similar, publicly viewable); paste the link.
3. Publish the blog post somewhere public; paste the link.
4. Find and fill in the submission form (not described on the pages we could read), name Track 2,
   paste the fields below, and submit before 11:59 PM IST on Oct 18. Do not leave it to the last hour.
5. Confirm team membership, and confirm who owns the IP if there is more than one person.
6. Confirm the copyright holder name in LICENSE.
7. Re-read the rules page once more on submission day (the page says rules may change).

## Proposed form text

**Project name:** baton

**One-line pitch:** A FalkorDB graph that parallel Claude Code sessions share, so they see each
other's work, decisions and handoffs before they collide.

**Tracks:** Track 2, Agent Memory and Coordination. (Not entering 1 or 3.)

**Long description:**
Parallel coding sessions on one repository collide silently: one changes a function signature while
another builds on the old one, and the next session starts from nothing. baton is a Claude Code
plugin (hooks plus an MCP server) that keeps one FalkorDB graph per workspace holding sessions as
leased Tasks, the files they touch (Artifacts), the Decisions they make, the Findings those rest on,
and Handoffs. Before an edit, a hook queries the graph for live leases on the file and for recent
interface, config and storage decisions on nearby or imported files, and tells the session. After an
edit, decisions are derived from the edit payload without a model call. A retraction walks BASED_ON
edges to mark everything derived from a wrong fact as tainted. Task claims are single atomic Cypher
statements, relying on FalkorDB serialising writes per graph (verified with a race test and a
negative control, docs/SPIKES.md). We also evaluated it honestly: across three rounds of 5 trials
per cell it did not significantly change how often parallel sessions finished collision-free (14/25
vs 12/25, p = 0.78), and failed checks per trial fell from 1.87 to 0.87 on the hardest tasks (post-hoc
p = 0.045 after tuning on the same tasks, so suggestive only). Full numbers and caveats: docs/RESULTS.md.

**Graph model summary:** Nodes Actor, Task, Decision, Finding, Artifact, Handoff. Relationships
DEPENDS_ON, TOUCHES, DECIDED, ABOUT, BASED_ON, SUPERSEDES, INCLUDES. See README and
docs/ARCHITECTURE-DIAGRAM.md.

**Why FalkorDB is central:** the product's answers are graph queries (live lease on a file, decisions
about nearby files, variable-length BASED_ON traversal for why/retract, ready-task frontier over
DEPENDS_ON, atomic claim). Without the graph there is nothing to ask.

**Tech used:** FalkorDB (v4.22.1 pinned; also passed tests on 6.0.2), Cypher, Python, Docker Compose,
MCP, Claude Code plugin hooks, Harbor (evaluation harness).

**Links (placeholders):** Repo: `<REPO_URL>` | Video: `<VIDEO_URL>` | Blog: `<BLOG_URL>` | Live
deployment: none (local setup in README).

**AI-assistance disclosure:** This project was designed and built with substantial help from an AI
coding assistant (Claude Code), including code, tests, evaluation harness and documentation. The
author directed the work, reviewed the results, and can explain the graph model, queries and
architecture. Evaluation numbers come from runs recorded in the repository.

## Rules that could disqualify us
- **AI assistance:** allowed but must be disclosed, and "entirely AI-generated" projects may be
  rejected. Disclosure is written; the author must genuinely be able to explain the model, queries
  and decisions (rehearse this before the video). The meaning of "meaningful contribution" is not
  defined on the pages.
- **FalkorDB central:** "if the product works without FalkorDB, the graph is decoration." Risk: hook
  output is short text; a judge could ask whether SQLite would do. Answer with the traversals
  (BASED_ON blast radius, nearby-file decisions) and the per-graph write serialisation spike.
- **New work:** main coding must start after Oct 15 12:01 AM IST. The git history starts
  2026-10-15 13:27 IST (31 commits), consistent with this. Do not rewrite history.
- **Data:** only public, synthetic or your own. All data is the synthetic `shop` fixture or generated
  by runs. Check `evals/` outputs and the video for real file paths, tokens or personal data before
  publishing. The evaluation used a subscription token; make sure none is in the repo or recording.
- **Plagiarism / manipulating judging:** cite FalkorDB docs and any borrowed ideas; no vote or
  score manipulation.
- **Evaluation honesty:** not a stated rule, but overstating results is the easiest way to lose
  credibility. Keep claims within docs/RESULTS.md.
- **License:** FalkorDB server is SSPLv1; baton only talks to it over the network and ships no
  FalkorDB code, so MIT for baton is fine. Not a rule on the pages; noted from FalkorDB's published license.
