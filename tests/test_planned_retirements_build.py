from __future__ import annotations

import hashlib
import json

from scripts.build_planned_retirements import _EIA_CACHE_FILENAME


def test_planned_retirements_uses_connector_cache_key() -> None:
    expected = hashlib.sha256(
        json.dumps(__import__("connectors.eia860m_source", fromlist=["EIA_CACHE_KEY"]).EIA_CACHE_KEY, sort_keys=True).encode()
    ).hexdigest()[:16] + ".bin"

    assert _EIA_CACHE_FILENAME == expected
