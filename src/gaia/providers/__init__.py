from .base import AdapterContext, HazardAdapter, PollingAdapter, StreamingAdapter
from .catalogue import seed_catalogue
from .emsc import EmscAdapter
from .firms import FirmsAdapter
from .gdacs import GdacsAdapter
from .geofon import GeofonAdapter
from .usgs import UsgsAdapter

ADAPTERS = {
    "emsc": EmscAdapter,
    "usgs": UsgsAdapter,
    "geofon": GeofonAdapter,
    "gdacs": GdacsAdapter,
    "firms": FirmsAdapter,
}

__all__ = [
    "ADAPTERS",
    "AdapterContext",
    "EmscAdapter",
    "FirmsAdapter",
    "GdacsAdapter",
    "GeofonAdapter",
    "HazardAdapter",
    "PollingAdapter",
    "StreamingAdapter",
    "UsgsAdapter",
    "seed_catalogue",
]
