"""Compatibility entry: the implementation lives in `manager.py` and sibling modules."""

from manager import GameServer

__all__ = ["GameServer"]


def _cli_main() -> None:
    import asyncio
    import logging

    logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(message)s")
    server = GameServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logging.info("Server shutting down")


if __name__ == "__main__":
    _cli_main()
