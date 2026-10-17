# Diagrams

Verified against `src/baton/graph/schema.py` (labels, relationship types) and
`src/baton/hooks/events.py` (handlers, `HANDLERS` map), plus the Cypher in
`src/baton/core/sessions.py` for what each hook writes.

## Data model

Each session is represented by a `Task` with `session = true` (created at session start, id
`sess_<hash>`); the `Actor` node is created alongside it. `Decision.kind` is one of
note/rename/interface/config/storage/other. Task status: open/claimed/done/released. Decision status:
open/superseded/retracted/tainted.

```mermaid
graph LR
    Actor -->|DECIDED| Decision
    Task -->|DEPENDS_ON| Task
    Task -->|TOUCHES| Artifact
    Decision -->|ABOUT| Artifact
    Decision -->|BASED_ON| Decision
    Decision -->|BASED_ON| Finding
    Decision -->|SUPERSEDES| Decision
    Handoff -->|INCLUDES| Task
    Handoff -->|INCLUDES| Decision
    Handoff -->|INCLUDES| Finding
    Handoff -->|INCLUDES| Artifact
```

## Hook flow

Six handlers in `HANDLERS`, wired in `plugin/hooks/hooks.json` to SessionStart, UserPromptSubmit,
PreToolUse and PostToolUse (matcher Write|Edit|MultiEdit|NotebookEdit|Bash), Stop and SessionEnd.
If the store is unreachable the hooks print nothing (fail open).

```mermaid
flowchart TD
    SS[SessionStart: session-start] -->|begin_session: MERGE session Task + Actor| G[(FalkorDB graph baton_workspace)]
    SS -->|briefing: live sessions, latest handoff| OUT1[context to session]
    UP[UserPromptSubmit: prompt] -->|set_goal on first prompt| G
    UP -->|duplicate_sessions by goal_key| DUP{same request live elsewhere?}
    DUP -->|earliest started: proceed / later: stand down| OUT2[context to session]
    PRE[PreToolUse: pre-tool] -->|check_conflicts: leases + decisions on same file| G
    PRE -->|recent_changes_nearby: imported or sibling files| G
    PRE --> POL{policy}
    POL -->|warn| OUT3[additionalContext warning]
    POL -->|ask or deny| OUT4[permissionDecision]
    POST[PostToolUse: post-tool] -->|touch: Task TOUCHES Artifact, renew lease| G
    POST -->|derive decisions from edit payload, no model call| G
    POST -->|Bash mv: rename Decision| G
    STOP[Stop: stop] -->|export_session_handoff + last test run| G
    END[SessionEnd: session-end] -->|end_session: Task done, lease 0| G
```
