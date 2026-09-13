"""VAA bulletin parser tests.

The parser must never raise and must never silently invent geometry.
"""

from __future__ import annotations

from datetime import UTC, datetime

from gaia.providers.vaac import (
    parse_coordinate,
    parse_dtg,
    parse_levels,
    parse_movement,
    parse_polygon,
    parse_vaa,
    split_sections,
)

BULLETIN = """FVFE01 RJTD 132359
VA ADVISORY
DTG: 20260913/2359Z
VAAC: TOKYO
VOLCANO: KANLAON 272030
PSN: N1025 E12320
AREA: PHILIPPINES
SUMMIT ELEV: 2435M
ADVISORY NR: 2026/004
INFO SOURCE: HIMAWARI-9
AVIATION COLOUR CODE: ORANGE
ERUPTION DETAILS: VA CONTINUOUSLY OBS ON SATELLITE IMAGERY
OBS VA DTG: 13/2340Z
OBS VA CLD: SFC/FL300 N1030 E12325 - N1035 E12340 - N1020 E12335 - N1025 E12320 MOV SE 20KT
FCST VA CLD +6HR: 14/0540Z SFC/FL300 N1040 E12400 - N1045 E12420 - N1030 E12415 - N1040 E12400
FCST VA CLD +12HR: 14/1140Z NO VA EXP
FCST VA CLD +18HR: 14/1740Z NO VA EXP
RMK: VA PLUME EXTENDS SE
NXT ADVISORY: 20260914/0600Z
"""


def test_sections_are_split_without_loss():
    sections = split_sections(BULLETIN)
    assert sections["VAAC"] == "TOKYO"
    assert sections["AREA"] == "PHILIPPINES"
    assert sections["AVIATION COLOUR CODE"] == "ORANGE"
    assert "SE" in sections["RMK"]


def test_coordinate_degrees_minutes():
    # N1025 is 10 degrees 25 minutes, not 10.25 degrees.
    assert parse_coordinate("N", "1025") == 10 + 25 / 60
    assert parse_coordinate("E", "12320") == 123 + 20 / 60
    assert parse_coordinate("S", "1025") == -(10 + 25 / 60)
    assert parse_coordinate("W", "12320") == -(123 + 20 / 60)


def test_coordinate_degrees_minutes_seconds_and_decimal():
    assert parse_coordinate("N", "102530") == 10 + 25 / 60 + 30 / 3600
    assert parse_coordinate("N", "10.25") == 10.25


def test_coordinate_rejects_out_of_range():
    assert parse_coordinate("N", "9930") is None


def test_polygon_is_closed_and_lon_lat_ordered():
    polygon = parse_polygon("SFC/FL300 N1030 E12325 - N1035 E12340 - N1020 E12335")
    assert polygon is not None
    ring = polygon["coordinates"][0]
    assert ring[0] == ring[-1], "ring must be closed"
    lon, lat = ring[0]
    assert 120 < lon < 125, "longitude must come first"
    assert 9 < lat < 12


def test_polygon_returns_none_when_too_few_points():
    assert parse_polygon("SFC/FL300 N1030 E12325") is None


def test_levels_and_movement():
    assert parse_levels("SFC/FL300 ...") == (0, 300)
    assert parse_levels("FL100/FL300 ...") == (100, 300)
    assert parse_levels("VA TO FL150") == (None, 150)

    movement = parse_movement("N1030 E12325 MOV SE 20KT")
    assert movement["direction_text"] == "SE"
    assert movement["direction_degrees"] == 135.0
    assert movement["speed_knots"] == 20.0


def test_dtg_full_and_short_forms():
    assert parse_dtg("20260913/2359Z") == datetime(2026, 9, 13, 23, 59, tzinfo=UTC)

    reference = datetime(2026, 9, 13, 23, 59, tzinfo=UTC)
    assert parse_dtg("13/2340Z", reference=reference) == datetime(
        2026, 9, 13, 23, 40, tzinfo=UTC
    )


def test_full_bulletin():
    result = parse_vaa(BULLETIN)

    assert result["vaac"] == "TOKYO"
    assert result["volcano_name"] == "KANLAON"
    assert result["volcano_number"] == "272030"
    assert result["colour_code"] == "ORANGE"
    assert result["status"] == "ACTIVE"
    assert result["issue_time"] == datetime(2026, 9, 13, 23, 59, tzinfo=UTC)
    assert result["top_flight_level"] == 300
    assert result["bottom_flight_level"] == 0
    assert result["movement"]["direction_text"] == "SE"

    # One observed frame plus one forecast; the two NO VA EXP forecasts add none.
    kinds = [f["kind"] for f in result["frames"]]
    assert kinds == ["OBSERVED", "FORECAST"]
    assert result["frames"][1]["lead_hours"] == 6.0
    assert not result["warnings"]

    # Raw text is always retained.
    assert result["raw_text"] == BULLETIN


def test_unparseable_bulletin_still_returns_a_record():
    result = parse_vaa("TOTAL GARBAGE WITH NO STRUCTURE")

    assert result["frames"] == []
    assert "NO_RECOGNISED_SECTIONS" in result["warnings"]
    assert result["raw_text"] == "TOTAL GARBAGE WITH NO STRUCTURE"


def test_missing_geometry_is_flagged_not_invented():
    bulletin = BULLETIN.replace(
        "OBS VA CLD: SFC/FL300 N1030 E12325 - N1035 E12340 - N1020 E12335 - N1025 E12320 MOV SE 20KT",  # noqa: E501
        "OBS VA CLD: SFC/FL300 GEOMETRY UNREADABLE MOV SE 20KT",
    )
    result = parse_vaa(bulletin)

    assert "OBSERVED_GEOMETRY_UNPARSED" in result["warnings"]
    assert all(f["kind"] != "OBSERVED" for f in result["frames"])


def test_cancelled_advisory_detected():
    assert parse_vaa(BULLETIN.replace("RMK: VA PLUME EXTENDS SE", "RMK: CANCEL"))[
        "status"
    ] == "CANCELLED"
