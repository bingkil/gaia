"""Seeded public hazard webcams.

Two kinds of entry here, gated by whether the source can actually be
hotlinked:

- Indonesia (PVMBG/MAGMA Indonesia): CCTV images require a session/CSRF
  token (see krb_maps.py's docstring), so these entries link out to the
  volcano's camera page on MAGMA Indonesia via ``source_url`` rather than
  embedding a live image. The Webcam model and its UI already treat a
  webcam with only a ``source_url`` as a valid "link out" entry.
  List and per-volcano camera counts confirmed against
  https://magma.esdm.go.id/v1/gunung-api/cctv (2026-09).
- Hawaii (USGS Hawaiian Volcano Observatory): HVO publishes plain,
  periodically refreshed JPEG stills with no auth, so these embed
  directly. Confirmed reachable via HEAD request against
  https://volcanoes.usgs.gov/cams/{code}/images/M.jpg (2026-09).

``Runtime.seed_webcams()`` inserts this list once, only if the webcam
table is still empty (same convention as the volcano catalogue seed in
``catalogue.py``) — an operator who deletes a seeded webcam is not
fighting it forever.
"""

from __future__ import annotations

from ..domain.enums import HazardType
from ..domain.models import Webcam
from ..store.repo import new_id

MAGMA_CCTV_BASE = "https://magma.esdm.go.id/v1/gunung-api/cctv"
MAGMA_ATTRIBUTION = "Pusat Vulkanologi dan Mitigasi Bencana Geologi (PVMBG), Badan Geologi, Kementerian ESDM"

# (volcano name, latitude, longitude, MAGMA CCTV code, camera count)
_INDONESIA: list[tuple[str, float, float, str, int]] = [
    ("Bromo", -7.94, 112.95, "BRO", 5),
    ("Dempo", -4.02, 103.13, "DEM", 2),
    ("Dieng", -7.20, 109.90, "DIE", 2),
    ("Guntur", -7.14, 107.84, "GUN", 1),
    ("Ibu", 1.49, 127.63, "IBU", 4),
    ("Ijen", -8.06, 114.24, "IJE", 3),
    ("Kerinci", -1.70, 101.26, "KER", 1),
    ("Anak Krakatau", -6.10, 105.42, "KRA", 6),
    ("Papandayan", -7.32, 107.73, "PAP", 1),
    ("Sinabung", 3.17, 98.39, "SIN", 4),
    ("Semeru", -8.11, 112.92, "SMR", 5),
]

HVO_ATTRIBUTION = "U.S. Geological Survey, Hawaiian Volcano Observatory (HVO)"

# (volcano name, latitude, longitude, camera code, camera label, official webcams page)
_HAWAII: list[tuple[str, float, float, str, str, str]] = [
    (
        "Kilauea",
        19.42,
        -155.29,
        "K2cam",
        "Kīlauea Caldera from Uēkahuna bluff",
        "https://www.usgs.gov/volcanoes/kilauea/webcams",
    ),
    (
        "Mauna Loa",
        19.48,
        -155.61,
        "MOcam",
        "Mokuʻāweoweo Caldera from South Rim",
        "https://www.usgs.gov/volcanoes/mauna-loa/webcams",
    ),
]


def seed_webcams() -> list[Webcam]:
    """Public reference webcams to pre-populate an empty install with."""
    webcams: list[Webcam] = []

    for name, lat, lon, code, count in _INDONESIA:
        camera_word = "camera" if count == 1 else "cameras"
        webcams.append(
            Webcam(
                id=new_id("webcam"),
                name=f"{name} ({count} {camera_word})",
                latitude=lat,
                longitude=lon,
                hazard_types=[HazardType.VOLCANO],
                source_url=f"{MAGMA_CCTV_BASE}/{code}",
                attribution=MAGMA_ATTRIBUTION,
            )
        )

    for name, lat, lon, code, label, page_url in _HAWAII:
        webcams.append(
            Webcam(
                id=new_id("webcam"),
                name=f"{name} \u2013 {label}",
                latitude=lat,
                longitude=lon,
                hazard_types=[HazardType.VOLCANO],
                image_url=f"https://volcanoes.usgs.gov/cams/{code}/images/M.jpg",
                source_url=page_url,
                attribution=HVO_ATTRIBUTION,
            )
        )

    return webcams
