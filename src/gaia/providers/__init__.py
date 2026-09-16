from .base import AdapterContext, HazardAdapter, PollingAdapter, StreamingAdapter
from .catalogue import seed_catalogue
from .emsc import EmscAdapter
from .firms import FirmsAdapter
from .gdacs import GdacsAdapter
from .geofon import GeofonAdapter
from .isigmet import IsigmetAdapter
from .usgs import UsgsAdapter

ADAPTERS = {
    "emsc": EmscAdapter,
    "usgs": UsgsAdapter,
    "geofon": GeofonAdapter,
    "gdacs": GdacsAdapter,
    "firms": FirmsAdapter,
    "isigmet": IsigmetAdapter,
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
    "seed_catalogue",
]
