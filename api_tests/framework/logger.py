# api_tests/framework/logger.py
"""Simplified logger — drop-in replacement for luna logger.

Exposes the same public API as luna.framework.common.logger:
  LOGGER    — standard Python logger
  LogStream — Register/Unregister file handlers per test
"""

import itertools
import logging
import sys

LOGGER = logging.getLogger("api_tests")
LOGGER.setLevel(logging.DEBUG)

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s [%(process)d] %(levelname)-5s %(message)s"))
LOGGER.addHandler(_handler)


class LogStream:
    """Registers a stream so that it receives log messages.

    Port of luna LogStream. Used by TestCase.setUp/tearDown to capture
    per-test log output to a file.
    """

    __STREAMS: dict[int, logging.Handler] = {}
    __ID = itertools.count()

    @classmethod
    def Register(cls, stream) -> int:
        """Attach stream to LOGGER. Returns an ID for Unregister."""
        handler = logging.StreamHandler(stream)
        handler.setFormatter(_handler.formatter)
        LOGGER.addHandler(handler)
        _id = next(cls.__ID)
        cls.__STREAMS[_id] = handler
        return _id

    @classmethod
    def Unregister(cls, _id: int) -> None:
        """Detach the stream registered under _id."""
        handler = cls.__STREAMS.pop(_id, None)
        if handler:
            LOGGER.removeHandler(handler)
