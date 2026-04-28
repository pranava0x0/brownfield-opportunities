"""Connector registry. To add a new data source:

1. Create `connectors/<my_source>.py` with a class that inherits from `Connector`
2. Add `register("<my-source>", MySource)` below.
3. `python refresh.py --source <my-source>` runs it.
"""
from __future__ import annotations

from connectors.base import Connector
from connectors.superfund_npl import SuperfundNPL

REGISTRY: dict[str, type[Connector]] = {}


def register(name: str, cls: type[Connector]) -> None:
    if name in REGISTRY:
        raise ValueError(f"connector already registered: {name}")
    REGISTRY[name] = cls


def get(name: str) -> type[Connector]:
    if name not in REGISTRY:
        raise KeyError(f"unknown connector: {name!r}. available: {sorted(REGISTRY)}")
    return REGISTRY[name]


def names() -> list[str]:
    return sorted(REGISTRY)


register("superfund-npl", SuperfundNPL)
