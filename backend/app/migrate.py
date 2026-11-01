"""Run Alembic against the configured database, e.g. from backend/:

    python -m app.migrate upgrade head
    python -m app.migrate current
    python -m app.migrate downgrade 0001

`upgrade` also adopts pre-Alembic databases in place, exactly like backend startup.
"""

import asyncio
import sys

from alembic import command

from app.database import _adopt_legacy_database, alembic_config


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("upgrade", "downgrade", "current", "history"):
        print(__doc__)
        return 2
    cfg = alembic_config()
    cmd, rest = argv[0], argv[1:]
    if cmd == "upgrade":
        asyncio.run(_adopt_legacy_database())
        command.upgrade(cfg, rest[0] if rest else "head")
    elif cmd == "downgrade":
        command.downgrade(cfg, rest[0])
    elif cmd == "current":
        command.current(cfg, verbose=True)
    else:
        command.history(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
