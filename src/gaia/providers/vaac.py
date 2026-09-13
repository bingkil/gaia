"""Volcanic Ash Advisory bulletin parser.

Spec section 13.2: never discard unparsed text. A bulletin whose geometry
cannot be read is still a valid advisory record carrying the raw text and
``geometry_quality = UNAVAILABLE``; it is not dropped and not guessed at.

Handles the ICAO VAA text layout common to the VAACs. Coordinates arrive as
degrees/minutes (``N1025 E12320``), occasionally degrees/minutes/seconds or
decimal degrees.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

FEET_TO_METRES = 0.3048

PARSER_VERSION = "vaa-parser/1.0.0"

_LABELS = [
    "DTG",
    "VAAC",
    "VOLCANO",
    "PSN",
    "AREA",
    "SUMMIT ELEV",
    "ADVISORY NR",
    "INFO SOURCE",
    "AVIATION COLOUR CODE",
    "ERUPTION DETAILS",
    "OBS VA DTG",
    "OBS VA CLD",
    "FCST VA CLD +6HR",
    "FCST VA CLD +12HR",
    "FCST VA CLD +18HR",
    "RMK",
    "NXT ADVISORY",
]

_LABEL_RE = re.compile(
    r"^(" + "|".join(re.escape(label) for label in _LABELS) + r")\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)

_COORD_RE = re.compile(
    r"([NS])\s*(\d{2,6}(?:\.\d+)?)\s+?([EW])\s*(\d{3,7}(?:\.\d+)?)",
    re.IGNORECASE,
)

_MOVEMENT_RE = re.compile(
    r"MOV\s+([NSEW]{1,3})\s+(?:(\d{1,3})\s*-\s*)?(\d{1,3})\s*KT",
    re.IGNORECASE,
)

_LEVEL_RE = re.compile(r"(SFC|FL\d{2,3})\s*/\s*(?:FL)?(\d{2,3})", re.IGNORECASE)

_DTG_RE = re.compile(r"(\d{8})/(\d{4})Z")
_SHORT_DTG_RE = re.compile(r"(\d{2})/(\d{4})Z")

_COMPASS = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
    "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
    "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
    "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}

_NO_ASH_MARKERS = (
    "NO VA EXP",
    "NOT AVBL",
    "NOT IDENTIFIABLE",
    "NO VA",
    "VA NOT IDENTIFIABLE",
)


def split_sections(text: str) -> dict[str, str]:
    """Split the bulletin into label -> value, preserving everything."""
    sections: dict[str, str] = {}
    matches = list(_LABEL_RE.finditer(text))
    for index, match in enumerate(matches):
        label = match.group(1).upper()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[label] = text[start:end].strip()
    return sections


def parse_coordinate(hemisphere: str, digits: str) -> float | None:
    is_lat = hemisphere.upper() in ("N", "S")
    sign = -1.0 if hemisphere.upper() in ("S", "W") else 1.0

    if "." in digits:
        return sign * float(digits)

    width = len(digits)
    deg_width = 2 if is_lat else 3
    if width < deg_width:
        return None

    degrees = float(digits[:deg_width])
    rest = digits[deg_width:]
    minutes = float(rest[:2]) if len(rest) >= 2 else 0.0
    seconds = float(rest[2:4]) if len(rest) >= 4 else 0.0

    value = sign * (degrees + minutes / 60.0 + seconds / 3600.0)
    limit = 90.0 if is_lat else 180.0
    return value if -limit <= value <= limit else None


def parse_polygon(text: str) -> dict[str, Any] | None:
    """Extract a closed polygon ring from a VA CLD section."""
    coords: list[list[float]] = []
    for hemi_lat, lat_digits, hemi_lon, lon_digits in _COORD_RE.findall(text):
        lat = parse_coordinate(hemi_lat, lat_digits)
        lon = parse_coordinate(hemi_lon, lon_digits)
        if lat is None or lon is None:
            continue
        coords.append([lon, lat])

    if len(coords) < 3:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def parse_levels(text: str) -> tuple[int | None, int | None]:
    """Return (bottom_flight_level, top_flight_level); SFC is flight level 0."""
    match = _LEVEL_RE.search(text)
    if not match:
        single = re.search(r"\bFL(\d{2,3})\b", text, re.IGNORECASE)
        return (None, int(single.group(1))) if single else (None, None)

    bottom_token = match.group(1).upper()
    bottom = 0 if bottom_token == "SFC" else int(bottom_token.removeprefix("FL"))
    return bottom, int(match.group(2))


def parse_movement(text: str) -> dict[str, Any]:
    match = _MOVEMENT_RE.search(text)
    if not match:
        return {}
    direction_text = match.group(1).upper()
    return {
        "direction_text": direction_text,
        "direction_degrees": _COMPASS.get(direction_text),
        "speed_knots": float(match.group(3)),
    }


def parse_dtg(text: str, reference: datetime | None = None) -> datetime | None:
    """Parse ``YYYYMMDD/HHMMZ`` or the day-only ``DD/HHMMZ`` form."""
    match = _DTG_RE.search(text)
    if match:
        date_part, time_part = match.groups()
        try:
            return datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M").replace(tzinfo=UTC)
        except ValueError:
            return None

    short = _SHORT_DTG_RE.search(text)
    if short and reference:
        day, time_part = short.groups()
        try:
            candidate = reference.replace(
                day=int(day), hour=int(time_part[:2]), minute=int(time_part[2:]),
                second=0, microsecond=0,
            )
        except ValueError:
            return None
        # A day number lower than the reference means the advisory rolls into next month.
        if int(day) < reference.day - 15:
            month = reference.month + 1
            year = reference.year + (month > 12)
            candidate = candidate.replace(year=year, month=month if month <= 12 else 1)
        return candidate
    return None


def flight_level_to_metres(level: int | None) -> float | None:
    return None if level is None else level * 100 * FEET_TO_METRES


def parse_vaa(text: str) -> dict[str, Any]:
    """Parse a VAA bulletin. Always returns a record; never raises."""
    warnings: list[str] = []
    sections = split_sections(text)
    if not sections:
        warnings.append("NO_RECOGNISED_SECTIONS")

    issue_time = parse_dtg(sections.get("DTG", ""))
    if issue_time is None:
        warnings.append("MISSING_ISSUE_TIME")

    volcano_field = sections.get("VOLCANO", "")
    volcano_match = re.match(r"([A-Z][A-Z0-9 '\-\.]+?)\s+(\d{6}|UNKNOWN)?\s*$", volcano_field)
    volcano_name = (volcano_match.group(1).strip() if volcano_match else volcano_field).strip()
    volcano_number = volcano_match.group(2) if volcano_match and volcano_match.group(2) else None

    summit_lat = summit_lon = None
    psn_match = _COORD_RE.search(sections.get("PSN", ""))
    if psn_match:
        summit_lat = parse_coordinate(psn_match.group(1), psn_match.group(2))
        summit_lon = parse_coordinate(psn_match.group(3), psn_match.group(4))
    else:
        warnings.append("MISSING_VOLCANO_POSITION")

    obs_time = parse_dtg(sections.get("OBS VA DTG", ""), reference=issue_time)
    obs_section = sections.get("OBS VA CLD", "")
    frames: list[dict[str, Any]] = []

    observed_polygon = parse_polygon(obs_section)
    obs_no_ash = any(marker in obs_section.upper() for marker in _NO_ASH_MARKERS)
    bottom_level, top_level = parse_levels(obs_section)

    if observed_polygon:
        frames.append(
            {
                "kind": "OBSERVED",
                "lead_hours": 0.0,
                "valid_time": obs_time or issue_time,
                "geometry": observed_polygon,
                "bottom_flight_level": bottom_level,
                "top_flight_level": top_level,
            }
        )
    elif obs_section and not obs_no_ash:
        warnings.append("OBSERVED_GEOMETRY_UNPARSED")

    for lead in (6, 12, 18):
        section = sections.get(f"FCST VA CLD +{lead}HR", "")
        if not section:
            continue
        if any(marker in section.upper() for marker in _NO_ASH_MARKERS):
            continue
        polygon = parse_polygon(section)
        if not polygon:
            warnings.append(f"FORECAST_{lead}H_GEOMETRY_UNPARSED")
            continue
        f_bottom, f_top = parse_levels(section)
        frames.append(
            {
                "kind": "FORECAST",
                "lead_hours": float(lead),
                "valid_time": parse_dtg(section, reference=issue_time),
                "geometry": polygon,
                "bottom_flight_level": f_bottom,
                "top_flight_level": f_top,
            }
        )

    movement = parse_movement(obs_section)
    status = "ACTIVE"
    upper_text = text.upper()
    if "FINAL ADVISORY" in upper_text:
        status = "FINAL"
    elif "CANCEL" in upper_text:
        status = "CANCELLED"
    elif obs_no_ash and not frames:
        status = "NO_ASH"

    return {
        "advisory_number": sections.get("ADVISORY NR"),
        "vaac": sections.get("VAAC"),
        "volcano_name": volcano_name or None,
        "volcano_number": volcano_number,
        "latitude": summit_lat,
        "longitude": summit_lon,
        "area": sections.get("AREA"),
        "summit_elevation": sections.get("SUMMIT ELEV"),
        "colour_code": sections.get("AVIATION COLOUR CODE"),
        "eruption_details": sections.get("ERUPTION DETAILS"),
        "info_source": sections.get("INFO SOURCE"),
        "issue_time": issue_time,
        "observation_time": obs_time,
        "next_advisory": parse_dtg(sections.get("NXT ADVISORY", "")),
        "status": status,
        "bottom_flight_level": bottom_level,
        "top_flight_level": top_level,
        "bottom_metres": flight_level_to_metres(bottom_level),
        "top_metres": flight_level_to_metres(top_level),
        "movement": movement,
        "frames": frames,
        "remarks": sections.get("RMK"),
        "raw_text": text,
        "parser_version": PARSER_VERSION,
        "warnings": warnings,
    }
