Grouping
========

Large pipelines emit many per-patient, per-fold, or per-seizure files. A raw
DAG drawing all of them is unreadable. The grouping API collapses related
files into a single visual node while **preserving every underlying hash**
via a Merkle root — aggregate verification remains cryptographically
meaningful.

Built-in groupers
-----------------

.. list-table::
   :header-rows: 1

   * - Name
     - Effect
   * - ``identity()``
     - No grouping — every file its own node
   * - ``drop_all_files()``
     - Scripts-only DAG (no file nodes)
   * - ``pattern_grouper(regex)``
     - Collapse files whose basenames match after replacing ``regex``
   * - ``directory_grouper(min_size=10, depth=1)``
     - Collapse ≥N files under a shared parent directory
   * - ``session_bundle_grouper(max_files=3)``
     - Bundle per-role outputs that exceed ``max_files``
   * - ``auto()``
     - Pattern → directory → bundle with sensible defaults
   * - ``compose(*groupers)``
     - Apply in order (first wins per file)

Python API
----------

.. code-block:: python

   import scitex_clew as clew
   from scitex_clew.groupers import pattern_grouper, auto, compose

   # callable
   clew.mermaid(claims=True, grouper=pattern_grouper(r"P\d{2}"))

   # JSON/dict spec
   clew.mermaid(claims=True, grouper={"type": "auto"})

   # fall back to .scitex/clew/config.yaml
   clew.mermaid(claims=True)

Spec schema
-----------

The same ``{"type": ..., **kwargs}`` shape works across Python, CLI
(``--grouper``), MCP (``{"grouper": {...}}``), and the YAML config:

.. code-block:: yaml

   # <project_root>/.scitex/clew/config.yaml
   grouper:
     type: compose
     steps:
       - {type: pattern, regex: 'P\d{2}'}
       - {type: pattern, regex: 'fold_\d+'}
       - {type: directory, min_size: 10, depth: 2}
       - {type: session_bundle, max_files: 3}

``clew.mermaid()`` and ``clew.render_dag()`` auto-load this file by walking
upward from CWD. Explicit ``grouper=`` argument wins.

Custom groupers
---------------

For logic not expressible via built-ins:

.. code-block:: python

   from scitex_clew.groupers import register_grouper

   def my_factory():
       def _g(entries):
           return [...]   # list[FileEntry | Group]
       return _g

   register_grouper("mine", my_factory)

Spec escape hatch (not honored in MCP for safety):

.. code-block:: yaml

   grouper: {type: custom, import: mypkg.groupers:factory}

Merkle roots
------------

Every :class:`scitex_clew.groupers.Group` carries ``root_hash`` = SHA-256
over sorted member hashes. A group renders ``✓`` only if **all** members
verify; ``⚠`` otherwise. Individual hashes are never discarded —
``clew.dag(format="json")`` always exports every file.

Grouping invariants
-------------------

- Grouping never crosses session boundaries.
- Groups are role-homogeneous (``input`` and ``output`` never mix).
- Collapsing is always lossless at the data level; only visual density changes.
