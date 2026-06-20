#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core foundational glue for scitex-clew.

Groups the package's cross-cutting, dependency-free primitives that the
rest of the codebase builds on: configuration loading (`_config`),
logging setup (`_logging`), and DAG-node type classification
(`_node_class`). Kept in one subpackage per PS-108b so the package root
stays under the flat-file threshold.

The public surface is re-exported here so callers can write
``from scitex_clew._core import load_config, getLogger`` without reaching
into the private leaf modules.
"""

from __future__ import annotations

from ._config import ENV_DIR, PKG_SHORT, load_config
from ._logging import getLogger
from ._node_class import (
    NODE_CLASSES,
    auto_classify,
    infer_node_class,
    migrate_add_node_class,
    set_node_class,
)

__all__ = [
    "ENV_DIR",
    "PKG_SHORT",
    "load_config",
    "getLogger",
    "NODE_CLASSES",
    "auto_classify",
    "infer_node_class",
    "migrate_add_node_class",
    "set_node_class",
]
