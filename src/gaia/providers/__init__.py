from .base import AdapterContext, HazardAdapter, PollingAdapter, StreamingAdapter
from .catalogue import seed_catalogue
from .emsc import EmscAdapter
from .firms import FirmsAdapter
from .gdacs import GdacsAdapter
from .geofon import GeofonAdapter
from .isigmet import IsigmetAdapter
from .usgs import UsgsAdapter
from .vona import VonaAdapter

ADAPTERS = {
    "emsc": EmscAdapter,
    "usgs": UsgsAdapter,
    "geofon": GeofonAdapter,
    "gdacs": GdacsAdapter,
    "firms": FirmsAdapter,
    "isigmet": IsigmetAdapter,
    "vona": VonaAdapter,
}

__all__ = [
    "ADAPTERS",
    "AdapterContext",
    "EmscAdapter",
    "FirmsAdapter",
    "GdacsAdapter",
    "GeofonAdapter",
    "HazardAdapter",
    "IsigmetAdapter",
    "PollingAdapter",
    "StreamingAdapter",
    "UsgsAdapter",
    "VonaAdapter",
    "seed_catalogue",
]
