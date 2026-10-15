"""Graph vocabulary and idempotent bootstrap statements.

Pure data: importing this module needs no database driver.
"""

LABELS = ("Actor", "Task", "Decision", "Finding", "Artifact", "Handoff")

REL_TYPES = (
    "DEPENDS_ON",   # Task -> Task
    "TOUCHES",      # Task -> Artifact
    "DECIDED",      # Actor -> Decision
    "ABOUT",        # Decision -> Artifact
    "BASED_ON",     # Decision -> Decision | Finding
    "SUPERSEDES",   # Decision -> Decision
    "INCLUDES",     # Handoff -> Decision | Finding | Artifact | Task
)

TASK_STATUSES = ("open", "claimed", "done", "released")
DECISION_STATUSES = ("open", "superseded", "retracted", "tainted")

# One statement per index. Run each, ignoring "already indexed" errors.
INDEX_STATEMENTS = (
    "CREATE INDEX FOR (a:Actor) ON (a.id)",
    "CREATE INDEX FOR (t:Task) ON (t.id)",
    "CREATE INDEX FOR (t:Task) ON (t.status)",
    "CREATE INDEX FOR (d:Decision) ON (d.id)",
    "CREATE INDEX FOR (d:Decision) ON (d.status)",
    "CREATE INDEX FOR (f:Finding) ON (f.id)",
    "CREATE INDEX FOR (a:Artifact) ON (a.path)",
    "CREATE INDEX FOR (h:Handoff) ON (h.id)",
)

# Added once Phase 1.6 needs duplicate-ticket detection.
FULLTEXT_STATEMENTS: tuple = ()
