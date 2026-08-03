"""Lunaris Live's API region.

This directory is the **only** part of ``apps/api`` allowed to import ``lunaris_live`` — the Python
mirror of the web's ``components/live/**`` exemption in ``apps/web/eslint.config.js``. Studio's app
mounts ``router`` and otherwise never names Live, so the one-way product boundary holds even though
both products are served by one FastAPI app. Enforced by ``tests/test_product_boundary.py``.
"""

from .router import router

__all__ = ["router"]
