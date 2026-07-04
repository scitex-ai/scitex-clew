The verify_claim Consumer Contract
==================================

This page is the binding call/return contract of
:func:`scitex_clew.verify_claim` for downstream consumers
(scitex-live-paper, scitex-writer). It is audited against the source at
**v0.7.0** (``src/scitex_clew/_claim/_verify.py`` and
``src/scitex_clew/_claim/_model.py``).

Motivation: a consumer once integrated against an imagined API —
``against=`` / ``bundle_root=`` keyword arguments, an assumed internal
git checkout, and a top-level ``result["status"]`` / ``verified_at`` —
and mismatched on all four axes. The actual contract follows.


Signature — one positional, no commit argument, no checkout
-----------------------------------------------------------

.. code-block:: python

   import scitex_clew as clew
   result = clew.verify_claim(claim_id_or_location)   # -> dict

- ``claim_id_or_location`` is a ``claim_id``, a ``"paper.tex:L42"``
  location string, or a bare file path (resolves to the first claim on
  that file).
- There is **no** ``against=``, ``bundle_root=``, or commit argument.
  The only other parameters are internal per-pass performance caches
  (``hash_cache=None`` / ``chain_cache=None``) threaded in by
  ``verify_all_claims``.
- **Clew never runs git.** It re-hashes the claim's ``source_file`` on
  disk, at its *current* state. To verify "as of commit X", the host
  must check out X first, then call ``verify_claim``. This
  git-agnosticism is by design; there is no verify-at-commit helper.
- Side effect: the claim row's ``status`` and ``verified_at`` are
  written back to the database on every resolved verification.


Return shape
------------

An unresolved lookup is the **only** case with a top-level ``status``:

.. code-block:: python

   {"status": "not_found", "message": "No claim found for '...'"}

A resolved claim returns exactly four top-level keys:

.. list-table::
   :header-rows: 1
   :widths: 20 12 68

   * - Key
     - Type
     - Meaning
   * - ``claim``
     - dict
     - ``Claim.to_dict()``: ``claim_id``, ``file_path``, ``line_number``,
       ``claim_type``, ``claim_value``, ``source_session``,
       ``source_file``, ``source_hash``, ``registered_at``,
       ``verified_at``, ``status``
   * - ``source_verified``
     - bool
     - stored ``source_hash`` matches the fresh re-hash of ``source_file``
   * - ``chain_verified``
     - bool
     - upstream ``@stx.session`` provenance chain verifies
   * - ``details``
     - list
     - human-readable notes (hash match/mismatch, chain run counts, errors)

Gotchas:

- ``status`` and ``verified_at`` live inside ``result["claim"]``, never
  at the top level of a resolved result.
- ``result["claim"]["status"]`` is refreshed to this pass's outcome;
  ``result["claim"]["verified_at"]`` is the value as read at resolution
  time (the DB row receives a new timestamp, the returned dict does not).
- ``resolved_status`` / ``color`` / ``display_group`` /
  ``display_color`` are **not** in this return — they are claims.json
  (schema v1.3) enrichment fields written by
  :func:`scitex_clew.export_claims_json`.


Two status vocabularies
-----------------------

**(a)** ``VerificationStatus`` enum
(``src/scitex_clew/_chain/_types.py``) — for runs, files, chains, and
DAGs: ``VERIFIED``, ``MISMATCH``, ``SUSPECT``, ``MISSING``, ``UNKNOWN``.

**(b)** Claim ``status`` strings stored on the claims row:
``registered``, ``verified``, ``suspect``, ``mismatch``, ``missing`` —
plus ``not_found`` as a lookup outcome (never stored).

.. list-table::
   :header-rows: 1
   :widths: 55 45

   * - Outcome of ``verify_claim``
     - Claim ``status``
   * - source file gone
     - ``missing``
   * - stored hash differs from current hash
     - ``mismatch``
   * - hash matches, chain fails
     - ``suspect``
   * - hash matches, chain verifies
     - ``verified``
   * - never verified (initial)
     - ``registered``

**v0.7.0 rename:** the claim status ``partial`` was renamed to
``suspect``. Legacy stored ``"partial"`` rows are normalized to
``"suspect"`` at read time. ``suspect`` now deliberately spans both
vocabularies — one word for "locally valid, upstream not confirmed".

Keep separate: client-side transient UI states (``verifying``,
``error``) are **not** clew statuses, and paper-level badge
vocabularies (e.g. the unified feed's ``badge_state``:
``all_verified`` / ``partial`` / ``failing``) are a separate aggregate
vocabulary.


claims.json v1.3 enrichment and precedence
------------------------------------------

``export_claims_json()`` adds per claim: ``resolved_status``, ``color``
(bare 6-hex, no ``#``), ``chain_has_exception``, ``chain_has_frozen``,
``display_group``, ``display_color``, ``exception_reasons``.

``resolved_status`` follows the precedence
``mismatch``/``missing`` > [**verified claims only**: ``exception`` >
``frozen``] > ``suspect`` > ``verified`` > ``registered``. Chain
overrides never promote an unverified claim — no false-green.

Canonical full-7 palette (``_CLAIM_PALETTE``, bare hex):

.. list-table::
   :header-rows: 1
   :widths: 30 25 45

   * - Status
     - Hex
     - Hue
   * - ``verified``
     - ``2da44e``
     - green
   * - ``suspect``
     - ``d29922``
     - amber
   * - ``mismatch``
     - ``cf222e``
     - red
   * - ``missing``
     - ``a40e26``
     - dark red
   * - ``registered``
     - ``6e7781``
     - grey
   * - ``exception``
     - ``8250df``
     - violet
   * - ``frozen``
     - ``0072b2``
     - blue (Okabe-Ito)

4-bucket display collapse: ``verified``\ +\ ``frozen`` → **verified**;
``suspect``\ +\ ``registered`` → **suspect**;
``mismatch``\ +\ ``missing`` → **failed**; ``exception`` →
**exception**. Consumers holding the pre-v1.3 table (``partial
d29922``, ``missing cf222e``, light/dark variants) have a stale copy —
read ``palette`` / ``display_palette`` / ``display_groups`` from the
exported claims.json instead of hardcoding.


Database selection precedence
-----------------------------

``resolve_db_path()`` (``src/scitex_clew/_db/_core.py``) resolves the
store in three tiers:

1. Explicit ``db_path`` — ``VerificationDB(db_path=...)`` and, new in
   0.7.0, ``render_dag(..., db_path=...)``.
2. The ``SCITEX_CLEW_DB_PATH`` environment variable.
3. Project-root walk from the current working directory (nearest
   ancestor containing ``.git`` or ``pyproject.toml``) →
   ``<root>/.scitex/clew/runtime/db.sqlite``.

Host-side re-verify recipe:

.. code-block:: python

   # HOST owns git: check out the pinned commit, point clew at the bundle DB.
   subprocess.run(["git", "-C", bundle_root, "checkout", pinned_commit], check=True)
   os.environ["SCITEX_CLEW_DB_PATH"] = f"{bundle_root}/.scitex/clew/runtime/db.sqlite"
   result = clew.verify_claim(claim_id)
   claim_status = result.get("claim", {}).get("status")   # not result["status"]

See also the ``scitex-clew`` skill page
``05_verify-claim-contract.md`` for the same contract in skill form.
