"""Hook entry points called by the host. Phase 3.

Subcommands (planned): session-start, pre-edit, post-edit, stop.
Policy: fail open. Never block the host because baton is unavailable.
"""

import sys

SUBCOMMANDS = ("session-start", "pre-edit", "post-edit", "stop")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in SUBCOMMANDS:
        print("usage: baton {%s}" % "|".join(SUBCOMMANDS), file=sys.stderr)
        return 2
    # Phase 3 implements these. Until then every hook is a no-op that succeeds.
    return 0


if __name__ == "__main__":
    sys.exit(main())
