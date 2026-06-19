"""Connector registry. To add a new data source:

1. Create `connectors/<my_source>.py` with a class that inherits from `Connector`
2. Add `register("<my-source>", MySource)` below.
3. `python refresh.py --source <my-source>` runs it.
"""
from __future__ import annotations

from connectors.ai_summary import AiSummary
from connectors.base import Connector
from connectors.eia_retired_plants import EiaRetiredPlants
from connectors.dod_brac import DodBrac
from connectors.epa_acres_cleanup import EpaAcresCleanup
from connectors.dod_fuds import DodFuds
from connectors.epa_acres import EpaAcres
from connectors.epa_echo import EpaEcho
from connectors.epa_redev import EpaRedev
from connectors.epa_superfund_docs import EpaSuperfundDocs
from connectors.fema_nri import FemaNri
from connectors.infra_proximity import InfraProximity
from connectors.ira_energy_community import IraEnergyCommunity
from connectors.iso_rto import IsoRto
from connectors.opportunity_zone import OpportunityZone
from connectors.parcel_owner import ParcelOwner
from connectors.superfund_npl import SuperfundNPL
from connectors.climate_zone import ClimateZone

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
register("epa-acres", EpaAcres)
register("dod-fuds", DodFuds)
register("dod-brac", DodBrac)
register("epa-redev", EpaRedev)
register("epa-superfund-docs", EpaSuperfundDocs)
register("infra-proximity", InfraProximity)
register("opportunity-zone", OpportunityZone)
register("ira-energy-community", IraEnergyCommunity)
register("fema-nri", FemaNri)
register("climate-zone", ClimateZone)
register("eia-retired-plants", EiaRetiredPlants)
register("iso-rto", IsoRto)
register("epa-echo", EpaEcho)
register("acres-cleanup", EpaAcresCleanup)
register("ai-summary", AiSummary)
register("parcel-owner", ParcelOwner)
