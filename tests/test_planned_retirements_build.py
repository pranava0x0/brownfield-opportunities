from __future__ import annotations

import hashlib
import json

from scripts.build_planned_retirements import _EIA_CACHE_FILENAME


def test_planned_retirements_uses_connector_cache_key() -> None:
    expected = hashlib.sha256(
        json.dumps({"src": "eia_860m_retired"}, sort_keys=True).encode()
    ).hexdigest()[:16] + ".bin"

    assert _EIA_CACHE_FILENAME == expected
