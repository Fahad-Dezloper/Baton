"""`baton` console command: `baton doctor` runs the install check, `baton gc` prunes old data, anything else is a hook event."""

from __future__ import annotations

import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "doctor":
        from baton.doctor import main as doctor_main

        return doctor_main(argv[1:])
    if argv and argv[0] == "gc":
        from baton.gc import main as gc_main

        return gc_main(argv[1:])
    from baton.hooks.cli import main as hook_main

    return hook_main(argv)


if __name__ == "__main__":
    sys.exit(main())
