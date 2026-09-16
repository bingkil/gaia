"""Runtime configuration.

Local-first: all state lives under a single data directory. No cloud services,
no secret manager. The FIRMS map key is the one optional credential and is read
from the environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


def _default_data_dir() -> Path:
    # A PyInstaller bundle's own directory is a temp extraction that can be
    # wiped between runs, so a packaged build needs a real per-user location.
    if not getattr(sys, "frozen", False):
        return REPO_ROOT / "data"
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "GAIA"


class ProviderSettings(BaseModel):
    enabled: bool = True
    poll_seconds: float = 60.0
    stale_after_seconds: float = 300.0


class EmscSettings(ProviderSettings):
    websocket_url: str = "wss://www.seismicportal.eu/standing_order/websocket"
    backfill_url: str = "https://www.seismicportal.eu/fdsnws/event/1/query"
    stale_after_seconds: float = 900.0
    reconnect_max_seconds: float = 60.0
    attribution: str = "EMSC-CSEM, CC BY 4.0"


class UsgsSettings(ProviderSettings):
    feed_url: str = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
    poll_seconds: float = 60.0
    stale_after_seconds: float = 600.0
    attribution: str = "U.S. Geological Survey"


class GeofonSettings(ProviderSettings):
    base_url: str = "https://geofon.gfz-potsdam.de/fdsnws/event/1/query"
    poll_seconds: float = 120.0
    lookback_minutes: int = 60
    stale_after_seconds: float = 900.0
    attribution: str = "GEOFON / GFZ Potsdam"


class GdacsSettings(ProviderSettings):
    event_list_url: str = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    poll_seconds: float = 300.0
    stale_after_seconds: float = 3600.0
    attribution: str = "Global Disaster Awareness and Coordination System, GDACS"


class FirmsSettings(ProviderSettings):
    base_url: str = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
    # Set GAIA_PROVIDERS__FIRMS__MAP_KEY in the environment. Free key from NASA FIRMS.
    map_key: str = ""
    # Two satellites, because agreement between them is what promotes a fire.
    # Suomi NPP delivery ends 2026-11-01, so NOAA-21 is the second one.
    products: list[str] = Field(
        default_factory=lambda: ["VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"]
    )
    poll_seconds: float = 1800.0
    day_range: int = 1
    stale_after_seconds: float = 21600.0
    # A detection must fall within this distance of a catalogued volcano to be correlated.
    volcano_radius_km: float = 10.0
    attribution: str = "NASA FIRMS"


class IsigmetSettings(ProviderSettings):
    feed_url: str = "https://aviationweather.gov/api/data/isigmet"
    poll_seconds: float = 300.0
    stale_after_seconds: float = 3600.0
    attribution: str = "NOAA Aviation Weather Center, international SIGMET"


class OpenSkySettings(BaseModel):
    # OAuth2 client credentials from https://opensky-network.org/my-opensky/account.
    # Set GAIA_OPENSKY__CLIENT_ID / GAIA_OPENSKY__CLIENT_SECRET. Anonymous access
    # is used (400 credits/day, easily exhausted) if left blank.
    client_id: str = ""
    client_secret: str = ""


class Providers(BaseModel):
    emsc: EmscSettings = EmscSettings()
    usgs: UsgsSettings = UsgsSettings()
    geofon: GeofonSettings = GeofonSettings()
    gdacs: GdacsSettings = GdacsSettings()
    firms: FirmsSettings = FirmsSettings(enabled=False)
    isigmet: IsigmetSettings = IsigmetSettings()


class CorrelationSettings(BaseModel):
    """Earthquake candidate matching windows and scoring, per spec section 11.1."""

    max_time_delta_seconds: float = 120.0
    max_distance_km: float = 150.0
    max_magnitude_delta: float = 1.2
    weight_time: float = 0.45
    weight_distance: float = 0.35
    weight_magnitude: float = 0.15
    weight_provider_link: float = 0.05
    auto_link_score: float = 0.72
    candidate_score: float = 0.55


class ModelSettings(BaseModel):
    """Seismic travel-time model. MVP constant velocities, per spec section 12.1."""

    p_velocity_km_s: float = 6.0
    s_velocity_km_s: float = 3.5
    delivery_margin_seconds: float = 3.0
    version: str = "constant-velocity/1.0.0"
    # Widen the reported arrival interval to avoid implying false precision.
    uncertainty_fraction: float = 0.15


class AlertSettings(BaseModel):
    min_magnitude: float = 4.5
    min_confidence: float = 0.55
    cooldown_seconds: float = 300.0
    magnitude_change_threshold: float = 0.3
    quiet_hours_enabled: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GAIA_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=_default_data_dir)
    host: str = "127.0.0.1"
    port: int = 8000
    # Retain events in the active map view for this long after origin time.
    active_window_hours: float = 48.0
    ingest_enabled: bool = True

    providers: Providers = Providers()
    correlation: CorrelationSettings = CorrelationSettings()
    seismic_model: ModelSettings = ModelSettings()
    alerts: AlertSettings = AlertSettings()
    opensky: OpenSkySettings = OpenSkySettings()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "gaia.sqlite3"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
