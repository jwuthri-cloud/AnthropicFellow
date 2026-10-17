"""structlog setup for the CLI and the MCP server: rich console output, or JSON lines."""

from __future__ import annotations

import logging
import sys

import structlog


def configure(level: str = "INFO", *, json_logs: bool = False) -> None:
    """Configure structlog for the current process, writing to stderr (stdout carries MCP)."""
    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
