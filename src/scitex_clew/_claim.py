#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility shim — superseded by the ``_claim/`` package.

The claim layer was split into a package (``_claim/``:
``_model`` / ``_register`` / ``_export`` / ``_verify`` / ``_mutate``) because
the former single file grew past the size limit. A package shadows a same-named
module, so ``import scitex_clew._claim`` resolves to ``_claim/__init__.py`` and
**this file is never executed at runtime**.

It is retained only so ``tests/scitex_clew/test__claim.py`` and
``tests/scitex_clew/test__claim_verify_all.py`` keep a same-basename source
mirror (PS-204 orphan-test rule), matching the repo's existing
``_chain.py`` / ``_chain/`` convention. Do not add logic here — edit the
package modules under ``_claim/`` instead.
"""

from __future__ import annotations

# EOF
