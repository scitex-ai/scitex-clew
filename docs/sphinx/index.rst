SciTeX Clew
===========

.. image:: _static/scitex-logo.png
   :alt: SciTeX
   :align: center
   :width: 400px

.. raw:: html

   <p align="center"><b>Verifiable knowledge graph for scientific experiments</b></p>
   <br>

SciTeX Clew records every artifact produced during research — code, data, figures,
statistics — into a **hash-linked DAG** (directed acyclic graph). This creates a
**verifiable knowledge graph** of scientific experiments, which can be explored by
humans or AI agents.

Named after the thread Ariadne gave Theseus to trace his path through the
labyrinth, Clew serves two purposes:

1. **Reproducibility verification** — confirm that outputs have not changed and
   that every step in the pipeline remains intact.
2. **Research logic comprehension** — visualize and navigate the structural
   skeleton of a research project, from raw data through analysis to manuscript
   claims.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   installation
   quickstart

.. toctree::
   :maxdepth: 2
   :caption: Concepts

   concepts
   grouping
   cli
   mcp

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/scitex_clew

.. toctree::
   :maxdepth: 2
   :caption: Examples

   examples

Quick Example
-------------

.. code-block:: python

   import scitex_clew as clew

   # Git-status-like overview
   clew.status()

   # Verify a run (hash check)
   result = clew.run("session_20250301_143022")

   # Trace a file's provenance chain
   chain = clew.chain("output/figure.png")

   # Verify the full DAG
   dag_result = clew.dag(["output/figure.png"])

.. figure:: _static/dag.png
   :alt: DAG verification example
   :align: center
   :width: 80%

   **Figure 1.** Example DAG visualization. Green nodes indicate verified sessions;
   red nodes indicate hash mismatches. Clew traces the dependency graph backward
   from target files to raw data sources.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
