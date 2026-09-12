"""Application logging setup.

Locally (``uvicorn --reload``) this just gives our own log records a level
and a plain-text format so they're readable in a terminal.

On Lambda, ``ALLOWED_LOG_LEVEL``/``LOGGING_FORMAT`` don't do anything by
themselves — the Lambda *platform* (via its Advanced Logging Controls,
configured on the CDK-defined function in infra/lib/astrology-stack.ts:
``loggingFormat: LoggingFormat.JSON``) intercepts everything the standard
``logging`` module writes and re-emits it to CloudWatch as structured JSON
with ``timestamp``/``level``/``message``/``requestId`` keys automatically.
So the app-level job here is only:

  1. make sure our logger actually has a level set (Python's default root
     logger level is WARNING, which would silently drop our INFO records)
  2. avoid handing Lambda a *second* stream handler with its own formatter,
     which would double-print every line once as our text and once as the
     platform's JSON — Lambda already attaches its own handler to the root
     logger before our code runs.
"""

from __future__ import annotations

import logging
import os
import sys


def _running_on_lambda() -> bool:
    # Set by the Lambda runtime for every invocation; absent locally.
    return "AWS_LAMBDA_FUNCTION_NAME" in os.environ


def configure_logging() -> None:
    """Set up logging once. Safe to call more than once (e.g. under pytest
    re-importing the app module across test files)."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    if _running_on_lambda():
        # Lambda's runtime already attached a handler to the root logger
        # that ships stdout to CloudWatch (and, with loggingFormat=JSON on
        # the function, wraps it as structured JSON). Adding our own handler
        # here would duplicate every log line. Just fix the level.
        return

    # Local/plain-text path: give the root logger a single readable handler,
    # replacing anything uvicorn or a previous call may have installed.
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.addHandler(handler)
