Concepts
========

Five Node Classes
-----------------

Every node in the DAG is classified into one of five semantic roles:

.. list-table:: **Table 1.** Five node classes. Classification is inferred automatically from file extensions and session roles, or set explicitly via ``set_node_class()``.
   :header-rows: 1
   :widths: 15 30 55

   * - Class
     - Role
     - Examples
   * - **Source**
     - Data acquisition scripts
     - ``01_download.py``, ``collect.sh``
   * - **Input**
     - Raw data and configuration
     - ``raw_data.csv``, ``config.yaml``
   * - **Processing**
     - Transform and analysis scripts
     - ``03_analyze.py``, ``train.R``
   * - **Output**
     - Intermediate and final data products
     - ``results.csv``, ``figure1.png``
   * - **Claim**
     - Manuscript assertions tied to evidence
     - ``"Fig 1 shows p<0.05"``, ``"Table 2"``

This classification turns the DAG into a navigable map of the research project.
The key operation is **backpropagation from claims to sources**: starting from a
manuscript assertion (claim), Clew traces backward through outputs, processing
scripts, and inputs to the original raw data — verifying every hash along the way.


Three Verification Modes
-------------------------

.. list-table:: **Table 2.** Three verification modes. Each mode supports both **cache verification** (millisecond hash comparison) and **re-run verification** (sandbox re-execution).
   :header-rows: 1
   :widths: 15 20 25 40

   * - Mode
     - Scope
     - API
     - Description
   * - **Project**
     - Entire pipeline
     - ``clew.dag()``
     - Verifies every session in the database in topological order. *"Is the whole project intact?"*
   * - **Files**
     - Specific outputs
     - ``clew.dag(["output.csv"])``
     - Traces backward from target files through their dependency chain. *"Can I trust this specific file?"*
   * - **Claims**
     - Manuscript assertions
     - ``clew.verify_claim("Fig 1")``
     - Verifies claims linked to source sessions. *"Is this figure still backed by the data?"*


DAG as Research Logic
---------------------

Beyond verification, the DAG itself is valuable: it is the **simplest formal
representation of a project's research logic**. Each node is a concrete artifact
(script, data file, or claim) and each edge is a recorded dependency. This
skeleton structure lets you:

- **Understand** a project at a glance — which scripts produce which outputs
- **Navigate** from any claim back to the raw data that supports it
- **Communicate** project structure to collaborators and reviewers
- **Enable AI agents** to reason about the research pipeline programmatically

The Mermaid diagram (``clew.mermaid()``) renders this logic as a visual flowchart,
making the implicit structure of any research project explicit and inspectable.

.. figure:: _static/dag.png
   :alt: DAG as research logic
   :align: center
   :width: 80%

   **Figure 2.** The DAG is both a verification tool and a structural map of
   research logic — from raw data through processing to manuscript claims.


How It Works
------------

1. **Recording**: During a session, Clew computes SHA-256 hashes of all input
   and output files, storing them alongside session metadata in a local SQLite
   database.

2. **Verification**: At any point, you can verify a session by recomputing
   hashes and comparing them to the recorded values. If any file has changed,
   the verification fails.

3. **DAG Construction**: Sessions are linked by shared files — when one session's
   output is another session's input, Clew infers a dependency edge. This builds
   a complete DAG of the research project.

4. **Provenance Tracing**: Given any file, Clew can trace its complete lineage —
   which sessions produced it, which inputs were consumed, and whether the chain
   is intact.

5. **Claim Verification**: Manuscript assertions (e.g., "Figure 1 shows p < 0.05")
   are linked to the sessions that produced the evidence. Verification ensures the
   claim is still supported by the data.


Architecture
------------

.. code-block:: text

   ┌─────────────────────────────────────────────────┐
   │                 scitex-clew                      │
   ├─────────────────────────────────────────────────┤
   │  Python API (19 functions)                       │
   │    status, run, chain, dag, rerun, mermaid, ...  │
   ├─────────────────────────────────────────────────┤
   │  CLI (Click)           │  MCP (FastMCP)          │
   │    clew status         │    clew mcp start       │
   │    clew verify ...     │    9 tools              │
   ├─────────────────────────────────────────────────┤
   │  Core Engine                                     │
   │    _hash.py    _chain/     _claim/    _attest/   │
   │    _tracker.py _rerun.py   _estimate.py          │
   ├─────────────────────────────────────────────────┤
   │  Storage: SQLite (db.sqlite)                      │
   │    runs, file_hashes, session_parents, claims    │
   └─────────────────────────────────────────────────┘

**Zero dependencies** — pure stdlib + sqlite3. Optional extras: ``click`` (CLI),
``fastmcp`` (MCP server), ``sphinx`` (docs).
