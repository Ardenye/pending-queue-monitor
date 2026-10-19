"""Pending Queue Monitor — Hermes Agent dashboard + Desktop plugin.

The visible UI is ``desktop/plugin.js`` (unified package desktop half); the
data comes from ``dashboard/plugin_api.py``, mounted by the web server at
``/api/plugins/pending-queue-monitor/`` once this plugin is in
``plugins.enabled``. ``register()`` exists so the plugin has a standard loader
surface (the agent loader requires it); it registers no tools or hooks and
performs no I/O at import time.
"""

from __future__ import annotations


def register(ctx) -> None:  # noqa: ARG001 — nothing to register for a read-only monitor
    return None
