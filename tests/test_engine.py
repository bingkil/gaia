"""Correlation, fusion, and impact tests.

Covers the scenarios spec section 22.3 calls out as mandatory.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

import nhc_samples
from gaia.config import (
    AlertSettings,
    CorrelationSettings,
    FirmsSettings,
    ModelSettings,
    NhcSettings,
)
from gaia.domain.enums import (
    PROVENANCE_LABELS,
    Action,
    AlertType,
    EventState,
    HazardType,
    ProvenanceClass,
    Quality,
    label_for,
)
from gaia.domain.models import Observation
from gaia.engine.changes import material_changes
from gaia.engine.correlate import best_match, score_pair
from gaia.engine.fusion import build_event, classify_provenance, compute_confidence, derive_state
from gaia.engine.impact import alert_radius_km, earthquake_impact
from gaia.engine.volcano import ThermalCluster, classify_thermal
from gaia.engine.wildfire import FireCluster, classify_fire
from gaia.providers.firms import FirmsAdapter
from gaia.providers.gdacs import GdacsAdapter
from gaia.providers.nhc import NhcAdapter

ORIGIN = datetime(2026, 9, 13, 19, 41, 17, tzinfo=UTC)
CORRELATION = CorrelationSettings()
ALERTS = AlertSettings()
MODEL = ModelSettings()


def make_obs(
    provider: str,
    source_id: str,
    *,
    lon: float = 22.11,
    lat: float = 38.32,
    magnitude: float | None = 6.1,
    depth: float | None = 12.0,
    origin: datetime = ORIGIN,
    revision: str = "1",
    reviewed: bool = False,
    action: Action = Action.UPSERT,
    ingested_offset: float = 0.0,
) -> Observation:
    return Observation(
        message_id=f"obs_{provider}_{source_id}_{revision}",
        provider=provider,
        source_id=source_id,
        source_revision=revision,
        hazard_type=HazardType.EARTHQUAKE,
        action=action,
        observed_at=origin,
        source_issued_at=origin + timedelta(seconds=20),
        ingested_at=origin + timedelta(seconds=20 + ingested_offset),
        parser_version="test/1.0.0",
        normalized={
            "longitude": lon,
            "latitude": lat,
            "magnitude": magnitude,
            "depth_km": depth,
            "magnitude_type": "Mw",
            "place": "Central Greece",
            "reviewed": reviewed,
        },
    )


class TestCorrelation:
    def test_three_sources_describing_one_event_merge(self):
        first = make_obs("EMSC", "e1")
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [first], None)

        # USGS reports the same event 8 km and 4 seconds away.
        second = make_obs(
            "USGS",
            "u1",
            lon=22.20,
            lat=38.34,
            magnitude=6.0,
            origin=ORIGIN + timedelta(seconds=4),
        )
        match = best_match(second, [event], CORRELATION)

        assert match.matched
        assert match.score >= CORRELATION.auto_link_score
        assert any("SPATIAL_MATCH" in r for r in match.reasons)

    def test_close_aftershock_stays_separate(self):
        """Same provider, distinct identifier: two events, never merged."""
        first = make_obs("EMSC", "mainshock")
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [first], None)

        # An aftershock 30 seconds later, 15 km away: within every window.
        aftershock = make_obs(
            "EMSC",
            "aftershock",
            lon=22.25,
            lat=38.38,
            magnitude=5.4,
            origin=ORIGIN + timedelta(seconds=30),
        )
        score, reasons = score_pair(aftershock, event, CORRELATION)

        assert score == 0.0
        assert "SAME_PROVIDER_DISTINCT_ID" in reasons

        assert not best_match(aftershock, [event], CORRELATION).matched

    def test_same_provider_same_id_is_a_revision(self):
        first = make_obs("EMSC", "e1")
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [first], None)

        revised = make_obs("EMSC", "e1", magnitude=6.4, revision="2")
        score, reasons = score_pair(revised, event, CORRELATION)

        assert score == 1.0
        assert reasons == ["PROVIDER_ID_MATCH"]

    def test_distant_event_is_not_matched(self):
        first = make_obs("EMSC", "e1")
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [first], None)

        far = make_obs("USGS", "u1", lon=140.0, lat=35.0)
        assert score_pair(far, event, CORRELATION)[0] == 0.0

    def test_divergent_magnitude_disqualifies(self):
        first = make_obs("EMSC", "e1", magnitude=6.1)
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [first], None)

        mismatch = make_obs("USGS", "u1", magnitude=3.0)
        score, reasons = score_pair(mismatch, event, CORRELATION)
        assert score == 0.0
        assert "MAGNITUDE_DIVERGENCE" in reasons

    def test_ambiguous_candidates_are_not_auto_linked(self):
        a, _ = build_event("evt_a", HazardType.EARTHQUAKE, [make_obs("EMSC", "a")], None)
        b, _ = build_event(
            "evt_b",
            HazardType.EARTHQUAKE,
            [make_obs("GEOFON", "b", lon=22.12, lat=38.33)],
            None,
        )

        incoming = make_obs("USGS", "u1", lon=22.115, lat=38.325)
        match = best_match(incoming, [a, b], CORRELATION)

        assert not match.matched
        assert match.ambiguous


class TestFusion:
    def test_single_source_is_preliminary(self):
        event, changes = build_event("evt_1", HazardType.EARTHQUAKE, [make_obs("EMSC", "e1")], None)

        assert event.provenance_class == ProvenanceClass.SINGLE_SOURCE_RAPID
        assert event.state == EventState.PRELIMINARY
        assert event.quality == Quality.PRELIMINARY
        assert event.confidence == pytest.approx(0.55)
        assert changes == {"created": True}

    def test_multisource_is_confirmed_with_higher_confidence(self):
        observations = [
            make_obs("EMSC", "e1"),
            make_obs("USGS", "u1", magnitude=6.0),
            make_obs("GEOFON", "g1", magnitude=6.2),
        ]
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, observations, None)

        assert event.provenance_class == ProvenanceClass.MULTISOURCE_RAPID
        assert event.state == EventState.CONFIRMED
        assert event.confidence >= 0.95
        assert "THREE_INDEPENDENT_SOURCES" in event.confidence_reasons
        assert sorted(event.providers) == ["EMSC", "GEOFON", "USGS"]

    def test_catalogue_event_never_becomes_authoritative(self):
        """No combination of catalogue feeds may claim early warning."""
        for count in range(1, 4):
            providers = ["EMSC", "USGS", "GEOFON"][:count]
            observations = [make_obs(p, f"{p}1") for p in providers]
            provenance, _ = classify_provenance(HazardType.EARTHQUAKE, observations)
            assert provenance not in (
                ProvenanceClass.AUTHORITATIVE_EEW,
                ProvenanceClass.AUTHORITATIVE_NOTICE,
            )

    def test_reviewed_solution_wins_over_newer_automatic(self):
        reviewed = make_obs("USGS", "u1", magnitude=6.5, reviewed=True, ingested_offset=0)
        automatic = make_obs("EMSC", "e1", magnitude=5.9, ingested_offset=100)

        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [reviewed, automatic], None)

        assert event.summary.magnitude == 6.5
        assert event.quality == Quality.REVIEWED
        assert event.field_provenance["magnitude"] == reviewed.message_id

    def test_field_provenance_is_recorded(self):
        observations = [make_obs("EMSC", "e1"), make_obs("USGS", "u1")]
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, observations, None)

        assert set(event.field_provenance) >= {"longitude", "latitude", "magnitude"}
        known_ids = {o.message_id for o in observations}
        assert all(v in known_ids for v in event.field_provenance.values())

    def test_retraction_moves_to_retracted(self):
        first, _ = build_event("evt_1", HazardType.EARTHQUAKE, [make_obs("EMSC", "e1")], None)
        deleted = make_obs("EMSC", "e1", revision="2", action=Action.DELETE)

        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [deleted], first)
        assert event.state == EventState.RETRACTED

    def test_thermal_only_volcano_is_an_automated_signal(self):
        observation = make_obs("FIRMS", "f1", magnitude=None, depth=None)
        observation.hazard_type = HazardType.VOLCANO
        provenance, reasons = classify_provenance(HazardType.VOLCANO, [observation])

        assert provenance == ProvenanceClass.AUTOMATED_SIGNAL
        assert "THERMAL_SIGNAL_ONLY" in reasons
        assert compute_confidence(HazardType.VOLCANO, [observation])[0] < 0.5

    def test_revision_increments_and_diff_is_reported(self):
        first, _ = build_event(
            "evt_1", HazardType.EARTHQUAKE, [make_obs("EMSC", "e1", magnitude=6.1)], None
        )
        revised = make_obs("EMSC", "e1", magnitude=6.6, revision="2")

        second, changes = build_event("evt_1", HazardType.EARTHQUAKE, [revised], first)

        assert second.revision == 2
        assert changes["magnitude"] == {"from": 6.1, "to": 6.6}


class TestMaterialChange:
    def test_first_observation_is_initial(self):
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [make_obs("EMSC", "e1")], None)
        alert_type, reasons = material_changes(None, event, ALERTS)

        assert alert_type == AlertType.INITIAL
        assert reasons == ["FIRST_OBSERVATION"]

    def test_trivial_revision_does_not_notify(self):
        first, _ = build_event(
            "evt_1", HazardType.EARTHQUAKE, [make_obs("EMSC", "e1", magnitude=6.1)], None
        )
        # A 0.05 magnitude nudge is below the material-change threshold.
        nudged = make_obs("EMSC", "e1", magnitude=6.15, revision="2")
        second, _ = build_event("evt_1", HazardType.EARTHQUAKE, [nudged], first)

        alert_type, reasons = material_changes(first, second, ALERTS)
        assert alert_type is None
        assert reasons == []

    def test_magnitude_increase_escalates(self):
        first, _ = build_event(
            "evt_1", HazardType.EARTHQUAKE, [make_obs("EMSC", "e1", magnitude=5.0)], None
        )
        bigger = make_obs("EMSC", "e1", magnitude=6.8, revision="2")
        second, _ = build_event("evt_1", HazardType.EARTHQUAKE, [bigger], first)

        alert_type, reasons = material_changes(first, second, ALERTS)
        assert alert_type == AlertType.ESCALATION
        assert any("MAGNITUDE_CHANGED" in r for r in reasons)

    def test_provenance_upgrade_escalates(self):
        first, _ = build_event("evt_1", HazardType.EARTHQUAKE, [make_obs("EMSC", "e1")], None)
        second, _ = build_event(
            "evt_1",
            HazardType.EARTHQUAKE,
            [make_obs("EMSC", "e1"), make_obs("USGS", "u1")],
            first,
        )

        alert_type, reasons = material_changes(first, second, ALERTS)
        assert alert_type == AlertType.ESCALATION
        assert "PROVENANCE_UPGRADED" in reasons

    def test_retraction_is_always_a_cancellation(self):
        first, _ = build_event("evt_1", HazardType.EARTHQUAKE, [make_obs("EMSC", "e1")], None)
        deleted = make_obs("EMSC", "e1", revision="2", action=Action.DELETE)
        second, _ = build_event("evt_1", HazardType.EARTHQUAKE, [deleted], first)

        alert_type, reasons = material_changes(first, second, ALERTS)
        assert alert_type == AlertType.CANCELLATION
        assert "EVENT_RETRACTED" in reasons


class TestImpact:
    def test_s_wave_arrives_after_p_wave(self):
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [make_obs("EMSC", "e1")], None)
        # Roughly 200 km away.
        impact = earthquake_impact(event, 24.5, 38.32, MODEL)

        assert impact is not None
        assert impact.p_arrival.estimate < impact.s_arrival.estimate
        assert impact.distance_km > 150

    def test_arrival_is_an_interval_not_a_point(self):
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [make_obs("EMSC", "e1")], None)
        impact = earthquake_impact(event, 24.5, 38.32, MODEL)

        assert impact.s_arrival.earliest < impact.s_arrival.estimate
        assert impact.s_arrival.estimate < impact.s_arrival.latest
        assert impact.s_arrival.quality == Quality.MODELLED

    def test_depth_is_included_via_hypocentral_distance(self):
        shallow = make_obs("EMSC", "e1", depth=0.0)
        deep = make_obs("EMSC", "e2", depth=600.0)

        shallow_event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [shallow], None)
        deep_event, _ = build_event("evt_2", HazardType.EARTHQUAKE, [deep], None)

        # At the epicentre, surface distance is ~0 but depth still separates them.
        shallow_impact = earthquake_impact(shallow_event, 22.11, 38.32, MODEL)
        deep_impact = earthquake_impact(deep_event, 22.11, 38.32, MODEL)

        assert deep_impact.hypocentral_distance_km > shallow_impact.hypocentral_distance_km
        assert deep_impact.hypocentral_distance_km == pytest.approx(600.0, abs=1.0)

    def test_past_event_does_not_show_a_countdown(self):
        old = make_obs("EMSC", "e1", origin=datetime.now(UTC) - timedelta(hours=2))
        event, _ = build_event("evt_1", HazardType.EARTHQUAKE, [old], None)

        impact = earthquake_impact(event, 22.5, 38.4, MODEL)
        assert impact.already_arrived

    def test_alert_radius_grows_with_magnitude(self):
        assert alert_radius_km(4.0, 10) < alert_radius_km(6.0, 10)
        assert alert_radius_km(7.0, 10) < alert_radius_km(7.0, 200)
        assert alert_radius_km(9.5, 10) <= 2000.0


class TestSafetyLanguage:
    def test_no_label_asserts_the_wrong_hazard(self):
        """A volcano must never be described as an earthquake report."""
        for hazard in HazardType:
            for provenance in ProvenanceClass:
                if provenance == ProvenanceClass.AUTHORITATIVE_EEW:
                    continue  # Earthquake Early Warning is seismic by definition.
                label = label_for(provenance, hazard).lower()
                if hazard != HazardType.EARTHQUAKE:
                    assert "earthquake" not in label, f"{hazard}/{provenance}: {label}"

    def test_volcano_labels_are_distinct_from_earthquake_labels(self):
        for provenance in (
            ProvenanceClass.SINGLE_SOURCE_RAPID,
            ProvenanceClass.MULTISOURCE_RAPID,
        ):
            assert label_for(provenance, HazardType.VOLCANO) != label_for(
                provenance, HazardType.EARTHQUAKE
            )

    def test_every_provenance_class_has_a_label(self):
        for provenance in ProvenanceClass:
            assert PROVENANCE_LABELS[provenance]

    def test_no_label_promises_safety(self):
        """Spec section 3.2 forbids telling anyone they are safe."""
        forbidden = ("safe", "no danger", "all clear", "you are fine")
        for hazard in HazardType:
            for provenance in ProvenanceClass:
                label = label_for(provenance, hazard).lower()
                assert not any(word in label for word in forbidden)


class TestThermalClassification:
    def test_single_pixel_is_never_an_eruption(self):
        cluster = ThermalCluster("v_etna", 1, 1, 12.0, 3.0)
        classification, reasons = classify_thermal(cluster)

        assert classification.value == "AUTOMATED_SIGNAL"
        assert "SINGLE_ISOLATED_PIXEL" in reasons

    def test_multi_satellite_cluster_is_possible_eruption(self):
        cluster = ThermalCluster("v_etna", 5, 2, 88.0, 1.2)
        assert classify_thermal(cluster)[0].value == "POSSIBLE_ERUPTION"

    def test_ash_advisory_confirms(self):
        cluster = ThermalCluster("v_etna", 5, 2, 88.0, 1.2)
        assert classify_thermal(cluster, has_ash_advisory=True)[0].value == "CONFIRMED_ERUPTION"


def _gdacs_feature(
    *,
    event_type: str = "WF",
    event_id: int = 1030252,
    todate: str = "2026-08-25T00:00:00",
    iscurrent: str = "false",
) -> dict:
    """Shaped from a live GDACS response; a fire leaves ``eventname`` empty."""
    return {
        "geometry": {"type": "Point", "coordinates": [21.1671, 44.8678]},
        "properties": {
            "eventid": event_id,
            "eventtype": event_type,
            "eventname": "" if event_type == "WF" else "Krakatau",
            "name": "Forest fires in Serbia",
            "country": "Serbia",
            "alertlevel": "Orange",
            "fromdate": "2026-08-05T00:00:00",
            "todate": todate,
            "iscurrent": iscurrent,
            "datemodified": "2026-09-14T10:10:13",
            "episodeid": 40,
            "episodealertscore": 1.5,
            "severitydata": {"severity": 18310.0, "severitytext": "", "severityunit": "ha"},
        },
    }


def _parse_one(feature: dict) -> dict:
    adapter = GdacsAdapter(None, None)
    records = adapter.parse(json.dumps({"features": [feature]}).encode())
    assert len(records) == 1
    return records[0]


class TestWildfire:
    def test_fire_is_not_mistaken_for_a_volcano(self):
        record = _parse_one(_gdacs_feature())
        assert record["hazard_type"] is HazardType.WILDFIRE
        # GDACS numbers each type separately, so a bare id could collide.
        assert record["source_id"] == "WF_1030252"
        assert record["normalized"]["volcano_name"] is None
        assert record["normalized"]["place"] == "Serbia"

    def test_volcano_keys_are_unchanged_by_the_fire_support(self):
        record = _parse_one(_gdacs_feature(event_type="VO", event_id=1000148))
        assert record["hazard_type"] is HazardType.VOLCANO
        assert record["source_id"] == "1000148"
        assert record["normalized"]["volcano_name"] == "Krakatau"

    def test_burnt_out_fire_is_marked_ended(self):
        record = _parse_one(_gdacs_feature(todate="2026-08-25T00:00:00", iscurrent="false"))
        assert record["normalized"]["ended"] is True

    def test_still_burning_fire_is_not_ended(self):
        record = _parse_one(_gdacs_feature(todate="2099-01-01T00:00:00", iscurrent="true"))
        assert record["normalized"]["ended"] is False

    def test_volcano_alert_keeps_standing_even_when_not_current(self):
        """An alert level holds until the agency withdraws it, unlike a fire."""
        record = _parse_one(_gdacs_feature(event_type="VO", iscurrent="false"))
        assert record["normalized"]["ended"] is False

    def test_ended_feed_event_ends_rather_than_retracts(self):
        obs = make_obs("GDACS", "WF_1")
        obs.normalized["ended"] = True
        state = derive_state([obs], EventState.PRELIMINARY, ProvenanceClass.SINGLE_SOURCE_RAPID)
        assert state is EventState.ENDED

    def test_ending_never_resurrects_a_retraction(self):
        obs = make_obs("GDACS", "WF_1")
        obs.normalized["ended"] = True
        state = derive_state([obs], EventState.RETRACTED, ProvenanceClass.SINGLE_SOURCE_RAPID)
        assert state is EventState.RETRACTED


class TestFireClassification:
    def test_single_pixel_is_never_a_fire(self):
        reportable, reasons = classify_fire(FireCluster(1, 1, 12.0, 21.1, 44.8))
        assert reportable is False
        assert "CLUSTER_TOO_SMALL" in reasons

    def test_small_cluster_is_not_enough(self):
        assert classify_fire(FireCluster(4, 2, 200.0, 21.1, 44.8))[0] is False

    def test_multi_satellite_cluster_reports(self):
        reportable, reasons = classify_fire(FireCluster(6, 2, 60.0, 21.1, 44.8))
        assert reportable is True
        assert "MULTI_SATELLITE" in reasons

    def test_multi_satellite_agreement_alone_is_not_enough(self):
        """Both VIIRS satellites see every field burn, so agreement is cheap."""
        reportable, reasons = classify_fire(FireCluster(40, 2, 12.0, 21.1, 44.8))
        assert reportable is False
        assert "WEAK_RADIATIVE_POWER" in reasons

    def test_one_satellite_needs_strong_power(self):
        assert classify_fire(FireCluster(6, 1, 40.0, 21.1, 44.8))[0] is False
        assert classify_fire(FireCluster(6, 1, 150.0, 21.1, 44.8))[0] is True

    def test_official_event_lets_a_lone_pixel_corroborate(self):
        reportable, reasons = classify_fire(
            FireCluster(1, 1, 5.0, 21.1, 44.8), has_official_event=True
        )
        assert reportable is True
        assert "OFFICIAL_EVENT_FEED_AGREES" in reasons


class TestGdacsCyclone:
    def _feature(self, **overrides) -> dict:
        """Shaped from a live GDACS TC response."""
        props = {
            "eventtype": "TC",
            "eventid": 1001334,
            "episodeid": 12,
            "eventname": "ISAIAS-26",
            "name": "Tropical Cyclone ISAIAS-26",
            "country": "United States",
            "alertlevel": "Orange",
            "episodealertscore": 2.0,
            "iscurrent": "true",
            "fromdate": "2026-10-06T21:00:00",
            "todate": "2099-01-01T00:00:00",
            "datemodified": "2026-10-09T15:16:07",
            "severitydata": {"severity": 194.4432, "severityunit": "km/h", "severitytext": ""},
        }
        props.update(overrides)
        return {"geometry": {"type": "Point", "coordinates": [-87.3, 27.7]}, "properties": props}

    def test_storm_is_a_cyclone_with_its_own_id_space(self):
        record = _parse_one(self._feature())
        assert record["hazard_type"] is HazardType.CYCLONE
        # GDACS numbers each type separately, so a bare id could collide.
        assert record["source_id"] == "TC_1001334"
        assert record["normalized"]["volcano_name"] is None

    def test_name_loses_gdacs_year_suffix_so_it_can_match_nhc(self):
        assert _parse_one(self._feature())["normalized"]["storm_name"] == "Isaias"

    def test_wind_is_converted_from_kmh_to_knots(self):
        assert _parse_one(self._feature())["normalized"]["max_wind_kt"] == pytest.approx(105.0, abs=0.1)

    def test_wind_in_an_unknown_unit_is_not_guessed(self):
        severity = {"severity": 194.4, "severityunit": "mph", "severitytext": ""}
        assert _parse_one(self._feature(severitydata=severity))["normalized"]["max_wind_kt"] is None

    def test_each_advisory_is_a_new_revision(self):
        """The alert score barely moves while a storm does, so it cannot be the key."""
        first = _parse_one(self._feature(episodeid=12))["source_revision"]
        second = _parse_one(self._feature(episodeid=13))["source_revision"]
        assert first != second

    def test_finished_storm_is_ended_and_not_dropped_as_a_duplicate(self):
        live = _parse_one(self._feature())
        done = _parse_one(self._feature(iscurrent="false", todate="2026-10-09T15:00:00"))
        assert live["normalized"]["ended"] is False
        assert done["normalized"]["ended"] is True
        assert done["source_revision"] != live["source_revision"]


class TestNhcParsing:
    def _parse(self, payload: bytes) -> list[dict]:
        return NhcAdapter(None, NhcSettings()).parse(payload)

    def _frames(self, record: dict, geometry_type: str) -> list[dict]:
        return [f for f in record["normalized"]["frames"] if f["geometry_type"] == geometry_type]

    def test_storm_becomes_an_official_cyclone_record(self):
        (record,) = self._parse(nhc_samples.bundle())
        normalized = record["normalized"]

        assert record["hazard_type"] is HazardType.CYCLONE
        assert record["source_id"] == "AL092026"
        assert normalized["storm_name"] == "Isaias"
        assert normalized["max_wind_kt"] == 105.0
        assert normalized["place"] == "Atlantic"
        assert normalized["longitude"] == -87.2

    def test_geometry_comes_from_all_three_products(self):
        (record,) = self._parse(nhc_samples.bundle())

        assert len(self._frames(record, "CYCLONE_CONE")) == 1
        assert len(self._frames(record, "CYCLONE_POSITION")) == 2
        assert sorted(f["properties"]["windKt"] for f in self._frames(record, "CYCLONE_WIND_RADII")) == [
            34,
            64,
        ]

    def test_the_longer_forecast_line_is_the_track(self):
        (record,) = self._parse(nhc_samples.bundle())
        (track,) = self._frames(record, "CYCLONE_TRACK")
        assert len(track["geometry"]["coordinates"]) == 4

    def test_forecast_points_carry_lead_time_and_wind(self):
        (record,) = self._parse(nhc_samples.bundle())
        points = {f["properties"]["leadHours"]: f for f in self._frames(record, "CYCLONE_POSITION")}

        assert points[12]["properties"]["maxWindKt"] == 100
        assert points[24]["properties"]["maxWindKt"] == 55

    def test_the_current_position_is_not_a_forecast_point(self):
        """The event marker already is the current position."""
        (record,) = self._parse(nhc_samples.bundle())
        assert all(f["lead_hours"] is not None for f in self._frames(record, "CYCLONE_POSITION"))

    def test_local_valid_time_is_converted_to_utc(self):
        (record,) = self._parse(nhc_samples.bundle())
        point = next(
            f for f in self._frames(record, "CYCLONE_POSITION") if f["lead_hours"] == 12
        )
        # 7:00 PM CDT (UTC-5) on 9 October is midnight UTC on the 10th.
        assert point["valid_time"] == "2026-10-10T00:00:00Z"

    def test_unrecognised_zone_keeps_the_point_without_inventing_a_time(self):
        files = {"track": nhc_samples.kmz(nhc_samples.track_kml(zone="XYZ"))}
        (record,) = self._parse(nhc_samples.bundle(files))

        points = self._frames(record, "CYCLONE_POSITION")
        assert len(points) == 2
        assert all("validTimeMs" not in p["properties"] for p in points)

    def test_every_frame_records_which_advisory_it_came_from(self):
        (record,) = self._parse(nhc_samples.bundle())
        issued_ms = datetime(2026, 10, 9, 18, tzinfo=UTC).timestamp() * 1000
        assert {f["properties"]["issuedAtMs"] for f in record["normalized"]["frames"]} == {issued_ms}

    def test_a_kml_declaring_a_dtd_is_refused_without_losing_the_storm(self):
        files = {"cone": nhc_samples.kmz(nhc_samples.DTD_KML), "radii": nhc_samples.kmz(nhc_samples.RADII_KML)}
        (record,) = self._parse(nhc_samples.bundle(files))

        assert any(w.startswith("CONE_UNREADABLE") for w in record["warnings"])
        assert self._frames(record, "CYCLONE_CONE") == []
        assert len(self._frames(record, "CYCLONE_WIND_RADII")) == 2

    def test_storm_with_no_products_still_has_a_position(self):
        (record,) = self._parse(nhc_samples.bundle({}))
        assert record["normalized"]["frames"] == []
        assert record["normalized"]["latitude"] == 28.4

    def test_storm_without_a_position_is_skipped(self):
        assert self._parse(nhc_samples.bundle(lon=None, lat=None)) == []

    def test_each_advisory_is_a_new_revision(self):
        first = self._parse(nhc_samples.bundle(updated="2026-10-09T18:00:00.000Z"))[0]
        second = self._parse(nhc_samples.bundle(updated="2026-10-09T21:00:00.000Z"))[0]
        assert first["source_revision"] != second["source_revision"]


class TestCycloneLanguage:
    def _obs(self, provider: str, source_id: str = "x") -> Observation:
        obs = make_obs(provider, source_id)
        obs.hazard_type = HazardType.CYCLONE
        return obs

    def test_nhc_advisory_is_an_official_notice(self):
        provenance, reasons = classify_provenance(HazardType.CYCLONE, [self._obs("NHC")])
        assert provenance is ProvenanceClass.AUTHORITATIVE_NOTICE
        assert "OFFICIAL_CYCLONE_ADVISORY" in reasons
        assert label_for(provenance, HazardType.CYCLONE) == "Official tropical cyclone advisory"

    def test_gdacs_alone_stays_preliminary(self):
        provenance, _ = classify_provenance(HazardType.CYCLONE, [self._obs("GDACS")])
        assert provenance is ProvenanceClass.SINGLE_SOURCE_RAPID
        assert label_for(provenance, HazardType.CYCLONE) == "Preliminary tropical cyclone report"

    def test_cyclone_labels_never_use_earthquake_wording(self):
        for provenance in (
            ProvenanceClass.SINGLE_SOURCE_RAPID,
            ProvenanceClass.MULTISOURCE_RAPID,
            ProvenanceClass.AUTHORITATIVE_NOTICE,
        ):
            assert "earthquake" not in label_for(provenance, HazardType.CYCLONE).lower()

    def test_nhc_outranks_gdacs_for_the_storm_name_and_wind(self):
        nhc = self._obs("NHC", "AL092026")
        nhc.normalized.update(storm_name="Isaias", max_wind_kt=105.0)
        gdacs = self._obs("GDACS", "TC_1")
        gdacs.normalized.update(storm_name="Isaias-26", max_wind_kt=99.0)
        # GDACS is the newer report, so recency alone would pick it.
        gdacs.ingested_at = nhc.ingested_at + timedelta(minutes=30)

        event, _ = build_event("evt_1", HazardType.CYCLONE, [nhc, gdacs], None)
        assert event.summary.storm_name == "Isaias"
        assert event.summary.max_wind_kt == 105.0


class TestFirmsKeyRedaction:
    """The key travels in the URL, so failures would otherwise log it."""

    def _adapter(self, map_key: str) -> FirmsAdapter:
        return FirmsAdapter(None, FirmsSettings(map_key=map_key))

    def test_key_is_stripped_from_error_text(self):
        adapter = self._adapter("SECRET123")
        message = adapter.redact(
            "Client error '400' for url 'https://firms/api/area/csv/SECRET123/VIIRS/1'"
        )
        assert "SECRET123" not in message
        assert "[MAP_KEY]" in message

    def test_no_key_configured_leaves_text_alone(self):
        assert self._adapter("").redact("plain failure") == "plain failure"
