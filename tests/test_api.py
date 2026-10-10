"""End-to-end API tests against a temporary database, with ingestion disabled."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import nhc_samples
from gaia.api.app import create_app
from gaia.config import AlertSettings, GdacsSettings, IsigmetSettings, NhcSettings, Settings, VonaSettings
from gaia.domain.enums import Action, AlertType, HazardType
from gaia.domain.geo import circle_geojson
from gaia.domain.models import Observation, WatchArea
from gaia.engine.policy import should_alert
from gaia.providers.gdacs import GdacsAdapter
from gaia.providers.isigmet import IsigmetAdapter
from gaia.providers.nhc import NhcAdapter
from gaia.providers.vona import VonaAdapter

VAA_BULLETIN = """FVAU01 ADRM 131800
VA ADVISORY
DTG: 20260913/1800Z
VAAC: DARWIN
VOLCANO: SEMERU 263300
PSN: S0806 E11255
AREA: INDONESIA
SUMMIT ELEV: 3676M
ADVISORY NR: 2026/45
INFO SOURCE: HIMAWARI-9
AVIATION COLOUR CODE: ORANGE
ERUPTION DETAILS: CONTINUOUS EMISSION
OBS VA DTG: 13/1740Z
OBS VA CLD: SFC/FL140 S0806 E11255 - S0750 E11310 - S0820 E11330 - S0806 E11255 MOV SW 15KT
FCST VA CLD +6HR: 14/0000Z SFC/FL140 S0806 E11255 - S0740 E11300 - S0830 E11340 - S0806 E11255
RMK: VA PLUME VISIBLE ON SATELLITE
NXT ADVISORY: 20260914/0000Z
"""


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, start_ingestion=False)
    with TestClient(app) as test_client:
        yield test_client


def seed_quake(
    client: TestClient,
    *,
    provider: str = "EMSC",
    source_id: str = "20260913_0000123",
    magnitude: float = 6.1,
    revision: str = "1",
    minutes_ago: float = 2.0,
) -> None:
    """Push an observation through the pipeline exactly as an adapter would."""
    runtime = client.app.state.runtime
    origin = datetime.now(UTC) - timedelta(minutes=minutes_ago)

    observation = Observation(
        message_id=f"obs_{provider}_{source_id}_{revision}",
        provider=provider,
        source_id=source_id,
        source_revision=revision,
        hazard_type=HazardType.EARTHQUAKE,
        action=Action.UPSERT,
        observed_at=origin,
        source_issued_at=origin,
        ingested_at=datetime.now(UTC),
        parser_version="test/1.0.0",
        normalized={
            "longitude": 22.11,
            "latitude": 38.32,
            "depth_km": 12.0,
            "magnitude": magnitude,
            "magnitude_type": "Mw",
            "place": "Central Greece",
        },
    )
    runtime.observations.insert(observation)
    # Run on the app's own event loop so the bus and pipeline share it.
    client.portal.call(runtime.pipeline.handle_observation, observation)


class TestMeta:
    def test_health_is_process_liveness_only(self, client):
        assert client.get("/healthz").json() == {"status": "ok"}

    def test_meta_exposes_model_version_and_disclaimer(self, client):
        body = client.get("/v1/meta").json()

        assert body["seismicModel"]["version"]
        assert "not an earthquake early warning system" in body["disclaimer"]
        assert body["provenanceLabels"]["SINGLE_SOURCE_RAPID"]
        assert any("EMSC" in a for a in body["attribution"])

    def test_volcano_catalogue_is_seeded(self, client):
        volcanoes = client.get("/v1/volcanoes").json()["volcanoes"]

        assert len(volcanoes) > 50
        assert any(v["name"] == "Semeru" for v in volcanoes)


class TestEvents:
    def test_empty_before_ingest(self, client):
        assert client.get("/v1/events").json()["count"] == 0

    def test_observation_becomes_an_event(self, client):
        seed_quake(client)
        body = client.get("/v1/events").json()

        assert body["count"] == 1
        event = body["events"][0]
        assert event["summary"]["magnitude"] == 6.1
        assert event["provenance_class"] == "SINGLE_SOURCE_RAPID"
        assert event["label"] == "Preliminary earthquake report"
        assert event["dataAgeSeconds"] is not None

    def test_second_provider_upgrades_provenance(self, client):
        seed_quake(client)
        seed_quake(client, provider="USGS", source_id="us7000abcd", magnitude=6.0)

        events = client.get("/v1/events").json()["events"]
        assert len(events) == 1
        assert events[0]["provenance_class"] == "MULTISOURCE_RAPID"
        assert sorted(events[0]["providers"]) == ["EMSC", "USGS"]

    def test_revision_history_is_retained(self, client):
        seed_quake(client, magnitude=6.1)
        seed_quake(client, magnitude=6.6, revision="2")

        event_id = client.get("/v1/events").json()["events"][0]["id"]
        revisions = client.get(f"/v1/events/{event_id}/revisions").json()["revisions"]

        assert len(revisions) == 2
        assert [r["revision"] for r in revisions] == [1, 2]

    def test_observations_trace_back_to_raw(self, client):
        seed_quake(client)
        event_id = client.get("/v1/events").json()["events"][0]["id"]

        observations = client.get(f"/v1/events/{event_id}/observations").json()
        assert len(observations["observations"]) == 1
        assert observations["observations"][0]["provider"] == "EMSC"

    def test_missing_event_is_404(self, client):
        assert client.get("/v1/events/evt_nope").status_code == 404

    def test_magnitude_filter(self, client):
        seed_quake(client, magnitude=6.1)
        assert client.get("/v1/events", params={"minMagnitude": 7.0}).json()["count"] == 0
        assert client.get("/v1/events", params={"minMagnitude": 5.0}).json()["count"] == 1

    def test_bbox_filter(self, client):
        seed_quake(client)
        inside = client.get("/v1/events", params={"bbox": "20,36,24,40"}).json()
        outside = client.get("/v1/events", params={"bbox": "130,30,145,45"}).json()

        assert inside["count"] == 1
        assert outside["count"] == 0

    def test_bad_bbox_is_rejected(self, client):
        assert client.get("/v1/events", params={"bbox": "1,2,3"}).status_code == 400


class TestMap:
    def test_geojson_carries_provenance_and_time(self, client):
        seed_quake(client)
        body = client.get("/v1/map/events.geojson").json()

        assert body["type"] == "FeatureCollection"
        props = body["features"][0]["properties"]
        assert props["label"] == "Preliminary earthquake report"
        assert props["originTimeMs"] > 0
        assert props["hazardType"] == "EARTHQUAKE"
        assert body["features"][0]["geometry"]["type"] == "Point"


class TestImpact:
    def test_point_impact_returns_an_interval(self, client):
        seed_quake(client)
        body = client.post(
            "/v1/impact/point", json={"longitude": 23.72, "latitude": 37.98}
        ).json()

        assert body["results"], "expected an impact result"
        result = body["results"][0]
        assert result["s_arrival"]["earliest"] < result["s_arrival"]["latest"]
        assert result["distance_km"] > 0
        assert "Not an official warning" in body["note"]

    def test_coordinates_are_validated(self, client):
        response = client.post(
            "/v1/impact/point", json={"longitude": 999, "latitude": 37.98}
        )
        assert response.status_code == 422


class TestWatchAreas:
    def test_create_list_delete(self, client):
        created = client.post(
            "/v1/watch-areas",
            json={"name": "Athens", "longitude": 23.72, "latitude": 37.98, "radiusKm": 400},
        )
        assert created.status_code == 201
        area_id = created.json()["id"]

        assert len(client.get("/v1/watch-areas").json()["watchAreas"]) == 1

        assert client.delete(f"/v1/watch-areas/{area_id}").status_code == 204
        assert client.get("/v1/watch-areas").json()["watchAreas"] == []

    def test_watch_area_produces_a_notification(self, client):
        client.post(
            "/v1/watch-areas",
            json={
                "name": "Near field",
                "longitude": 22.30,
                "latitude": 38.45,
                "radiusKm": 400,
                "minMagnitude": 4.5,
            },
        )
        seed_quake(client, magnitude=6.1)

        event_id = client.get("/v1/events").json()["events"][0]["id"]
        decisions = client.get(f"/v1/alert-decisions/{event_id}").json()["decisions"]

        notifications = client.get("/v1/notifications").json()["notifications"]
        assert len(notifications) == 1, f"decisions were {decisions}"
        assert notifications[0]["alertType"] == "INITIAL"
        assert "Preliminary earthquake report" in notifications[0]["body"]

    def test_distant_watch_area_is_suppressed_with_a_distance_reason(self, client):
        """A wide watch radius does not override the magnitude screening radius."""
        client.post(
            "/v1/watch-areas",
            json={
                "name": "Athens",
                "longitude": 23.72,
                "latitude": 37.98,
                "radiusKm": 400,
                "minMagnitude": 4.5,
            },
        )
        seed_quake(client, magnitude=6.1)

        assert client.get("/v1/notifications").json()["notifications"] == []

        event_id = client.get("/v1/events").json()["events"][0]["id"]
        decisions = client.get(f"/v1/alert-decisions/{event_id}").json()["decisions"]
        assert decisions[0]["decision"] == "SUPPRESS"
        assert any(r.startswith("OUTSIDE_RADIUS") for r in decisions[0]["reasonCodes"])

    def test_below_threshold_event_is_suppressed_with_a_reason(self, client):
        client.post(
            "/v1/watch-areas",
            json={
                "name": "Athens",
                "longitude": 23.72,
                "latitude": 37.98,
                "radiusKm": 400,
                "minMagnitude": 6.5,
            },
        )
        seed_quake(client, magnitude=5.0)

        assert client.get("/v1/notifications").json()["notifications"] == []

        event_id = client.get("/v1/events").json()["events"][0]["id"]
        decisions = client.get(f"/v1/alert-decisions/{event_id}").json()["decisions"]
        assert decisions[0]["decision"] == "SUPPRESS"
        assert decisions[0]["reasonCodes"]


class TestWebcams:
    def test_catalogue_is_seeded_on_startup(self, client):
        webcams = client.get("/v1/webcams").json()["webcams"]
        assert len(webcams) == 13

        names = {w["name"] for w in webcams}
        assert any(name.startswith("Bromo") for name in names)
        assert any("Kilauea" in name for name in names)

        # Indonesian entries link out to MAGMA Indonesia rather than
        # embedding an image (CCTV images require a session/token).
        bromo = next(w for w in webcams if w["name"].startswith("Bromo"))
        assert bromo["image_url"] is None
        assert bromo["source_url"].startswith("https://magma.esdm.go.id/")

        # HVO entries embed a direct, hotlinkable still image.
        kilauea = next(w for w in webcams if "Kilauea" in w["name"])
        assert kilauea["image_url"].startswith("https://volcanoes.usgs.gov/")

    def test_seeding_does_not_resurrect_a_deleted_webcam(self, client):
        webcams = client.get("/v1/webcams").json()["webcams"]
        bromo_id = next(w["id"] for w in webcams if w["name"].startswith("Bromo"))

        assert client.delete(f"/v1/webcams/{bromo_id}").status_code == 204

        # Re-seeding (as would happen on the next app startup against the
        # same database) must not bring the deleted webcam back, because
        # the seed is gated on the table being empty, not per-row.
        runtime = client.app.state.runtime
        assert runtime.seed_webcams() == 0

        webcams_after = client.get("/v1/webcams").json()["webcams"]
        assert len(webcams_after) == 12
        assert all(w["id"] != bromo_id for w in webcams_after)

    def test_create_list_update_delete(self, client):
        baseline = client.get("/v1/webcams").json()["webcams"]

        created = client.post(
            "/v1/webcams",
            json={
                "name": "Ridge cam",
                "latitude": 38.32,
                "longitude": 22.11,
                "hazardTypes": ["EARTHQUAKE"],
                "imageUrl": "https://example.invalid/latest.jpg",
            },
        )
        assert created.status_code == 201
        body = created.json()
        webcam_id = body["id"]
        assert body["stream_status"] == "UNCHECKED"
        assert body["image_status"] == "UNCHECKED"

        listed = client.get("/v1/webcams").json()["webcams"]
        assert len(listed) == len(baseline) + 1

        updated = client.put(
            f"/v1/webcams/{webcam_id}",
            json={
                "name": "Ridge cam (renamed)",
                "latitude": 38.32,
                "longitude": 22.11,
                "hazardTypes": ["EARTHQUAKE", "VOLCANO"],
                "imageUrl": "https://example.invalid/latest.jpg",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Ridge cam (renamed)"
        assert set(updated.json()["hazard_types"]) == {"EARTHQUAKE", "VOLCANO"}

        assert client.delete(f"/v1/webcams/{webcam_id}").status_code == 204
        assert client.get("/v1/webcams").json()["webcams"] == baseline


    def test_recheck_sets_last_checked_at_without_network(self, client):
        created = client.post(
            "/v1/webcams",
            json={
                "name": "Unconfigured cam",
                "latitude": 38.32,
                "longitude": 22.11,
                "hazardTypes": ["EARTHQUAKE"],
            },
        )
        webcam_id = created.json()["id"]
        assert created.json()["last_checked_at"] is None

        rechecked = client.post(f"/v1/webcams/{webcam_id}/recheck")
        assert rechecked.status_code == 200
        assert rechecked.json()["last_checked_at"] is not None
        assert rechecked.json()["stream_status"] == "UNCHECKED"
        assert rechecked.json()["image_status"] == "UNCHECKED"

    def test_recheck_missing_webcam_is_404(self, client):
        assert client.post("/v1/webcams/nope/recheck").status_code == 404

    def test_event_detail_includes_nearby_matching_webcams(self, client):
        client.post(
            "/v1/webcams",
            json={
                "name": "Near the quake",
                "latitude": 38.32,
                "longitude": 22.11,
                "hazardTypes": ["EARTHQUAKE"],
                "imageUrl": "https://example.invalid/latest.jpg",
            },
        )
        client.post(
            "/v1/webcams",
            json={
                "name": "Wrong hazard type",
                "latitude": 38.32,
                "longitude": 22.11,
                "hazardTypes": ["VOLCANO"],
                "imageUrl": "https://example.invalid/latest.jpg",
            },
        )
        seed_quake(client, magnitude=6.1)

        event_id = client.get("/v1/events").json()["events"][0]["id"]
        webcams = client.get(f"/v1/events/{event_id}").json()["webcams"]
        assert [w["name"] for w in webcams] == ["Near the quake"]


class TestVaaIngest:
    def test_bulletin_becomes_an_ash_event_with_frames(self, client):
        response = client.post("/v1/ingest/vaa", json={"bulletin": VAA_BULLETIN})
        assert response.status_code == 200

        body = response.json()
        assert body["event"]["hazard_type"] == "ASH"
        assert body["event"]["provenance_class"] == "AUTHORITATIVE_NOTICE"
        assert body["event"]["label"] == "Official volcanic ash advisory"
        assert body["frameCount"] == 2

    def test_frames_expose_valid_time_and_kind(self, client):
        event_id = (
            client.post("/v1/ingest/vaa", json={"bulletin": VAA_BULLETIN})
            .json()["event"]["id"]
        )
        features = client.get(
            "/v1/map/frames.geojson", params={"eventId": event_id}
        ).json()["features"]

        kinds = {f["properties"]["frameKind"] for f in features}
        assert kinds == {"OBSERVED", "FORECAST"}
        assert all(f["properties"]["validTimeMs"] > 0 for f in features)
        assert all(f["geometry"]["type"] == "Polygon" for f in features)

    def test_garbage_bulletin_is_rejected_not_invented(self, client):
        response = client.post("/v1/ingest/vaa", json={"bulletin": "hello world"})
        assert response.status_code == 422

    def test_event_detail_includes_official_hazard_zone_map(self, client):
        event_id = (
            client.post("/v1/ingest/vaa", json={"bulletin": VAA_BULLETIN})
            .json()["event"]["id"]
        )
        hazard_map = client.get(f"/v1/events/{event_id}").json()["hazardMap"]

        assert hazard_map["volcanoName"] == "Semeru"
        assert hazard_map["imageUrl"].startswith("https://magma.esdm.go.id/")
        assert "PVMBG" in hazard_map["attribution"]

    def test_hazard_map_is_absent_for_earthquakes(self, client):
        seed_quake(client, magnitude=6.1)
        event_id = client.get("/v1/events").json()["events"][0]["id"]

        assert client.get(f"/v1/events/{event_id}").json()["hazardMap"] is None


class TestIsigmetIngest:
    """A VA record from the international SIGMET feed, shaped as IsigmetAdapter
    would parse it. Modelled on a real Dukono (Indonesia) SIGMET."""

    RECORD = {
        "icaoId": "WAAA",
        "firId": "WAAF",
        "firName": "UJUNG PANDANG",
        "receiptTime": "2026-09-16T08:12:06.162Z",
        "validTimeFrom": 1789546320,
        "validTimeTo": 1789567200,
        "seriesId": "09",
        "hazard": "VA",
        "qualifier": "DUKONO",
        "geom": "AREA",
        "coords": [
            {"lon": 127.917, "lat": 1.65},
            {"lon": 127.817, "lat": 1.7},
            {"lon": 127.817, "lat": 2.533},
            {"lon": 128.467, "lat": 2.283},
            {"lon": 127.917, "lat": 1.65},
        ],
        "rawSigmet": (
            "WVID21 WAAA 160810\n"
            "WAAF SIGMET 09 VALID 160810/161410 WAAA-\n"
            "WAAF UJUNG PANDANG  FIR VA\n"
            "ERUPTION MT DUKONO\n"
            "PSN N0142 E12754 VA CLD OBS AT 0810Z WI N0139\n"
            "E12755 - N0142 E12749 - N0232 E12753 - N0217 E12828 - N0139 E12755\n"
            "SFC/FL070 MOV N 10KT\n"
            "NC="
        ),
    }

    def _ingest(self, client):
        runtime = client.app.state.runtime
        adapter = IsigmetAdapter(ctx=None, settings=IsigmetSettings())
        records = adapter.parse(json.dumps([self.RECORD]).encode())
        observation = adapter.to_observation(records[0], "raw/isigmet-test", "sha")
        runtime.observations.insert(observation)
        # Run on the app's own event loop so the bus and pipeline share it.
        return client.portal.call(runtime.pipeline.handle_observation, observation)

    def test_va_sigmet_becomes_an_ash_event_with_a_frame(self, client):
        event = self._ingest(client)

        assert event.hazard_type.value == "ASH"
        assert event.provenance_class.value == "AUTHORITATIVE_NOTICE"
        assert event.summary.volcano_name == "DUKONO"

        events = client.get("/v1/events").json()["events"]
        assert any(e["id"] == event.id for e in events)

    def test_frame_geometry_and_levels_are_parsed(self, client):
        event = self._ingest(client)

        features = client.get(
            "/v1/map/frames.geojson", params={"eventId": event.id}
        ).json()["features"]

        assert len(features) == 1
        assert features[0]["properties"]["frameKind"] == "OBSERVED"
        assert features[0]["geometry"]["type"] == "Polygon"

        advisories = client.get(f"/v1/events/{event.id}").json()["advisories"]
        assert advisories[0]["altitude"]["top_flight_level"] == 70


class TestVonaIngest:
    """A per-volcano status record from USGS's VONA-derived regionstatus feed."""

    RECORD = {
        "vName": "Redoubt",
        "lat": 60.4852,
        "long": -152.7438,
        "vnum": "313030",
        "volcanoCd": "VNUM313030",
        "obs": "avo",
        "region": "Alaska Peninsula",
        "noticeId": "DOI-USGS-AVO-2026-09-01T12:00:00-08:00",
        "noticeSynopsis": "Seismic unrest continues beneath Redoubt Volcano.",
        "alertLevel": "WATCH",
        "colorCode": "ORANGE",
        "alertDate": "2026-09-01 20:00:00",
        "colorDate": "2026-09-01 20:00:00",
    }

    def _ingest(self, client, record):
        runtime = client.app.state.runtime
        adapter = VonaAdapter(ctx=None, settings=VonaSettings())
        records = adapter.parse(json.dumps([record]).encode())
        observation = adapter.to_observation(records[0], "raw/vona-test", "sha")
        runtime.observations.insert(observation)
        return client.portal.call(runtime.pipeline.handle_observation, observation)

    def test_elevated_alert_becomes_an_authoritative_volcano_event(self, client):
        event = self._ingest(client, self.RECORD)

        assert event.hazard_type.value == "VOLCANO"
        assert event.provenance_class.value == "AUTHORITATIVE_NOTICE"
        assert event.summary.volcano_name == "Redoubt"

        events = client.get("/v1/events").json()["events"]
        assert any(e["id"] == event.id for e in events)

    def test_normal_alert_level_produces_no_observation(self):
        adapter = VonaAdapter(ctx=None, settings=VonaSettings())
        record = dict(self.RECORD, alertLevel="NORMAL", colorCode="GREEN")

        assert adapter.parse(json.dumps([record]).encode()) == []


class TestCycloneIngest:
    """NHC advisories and GDACS reports, through the real pipeline."""

    @staticmethod
    def _gdacs_feature(*, name: str = "ISAIAS-26", lon: float = -87.3, lat: float = 27.7) -> dict:
        return {
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "eventtype": "TC",
                "eventid": 1001334,
                "episodeid": 12,
                "eventname": name,
                "country": "United States",
                "alertlevel": "Orange",
                "iscurrent": "true",
                "fromdate": "2026-10-06T21:00:00",
                "todate": "2099-01-01T00:00:00",
                "datemodified": "2026-10-09T15:16:07",
                "severitydata": {"severity": 194.4, "severityunit": "km/h"},
            },
        }

    def _push(self, client, adapter, payload: bytes):
        runtime = client.app.state.runtime
        (record,) = adapter.parse(payload)
        observation = adapter.to_observation(record, "raw/cyclone-test", "sha")
        runtime.observations.insert(observation)
        return client.portal.call(runtime.pipeline.handle_observation, observation)

    def _nhc(self, client, **storm):
        adapter = NhcAdapter(ctx=None, settings=NhcSettings())
        return self._push(client, adapter, nhc_samples.bundle(**storm))

    def _gdacs(self, client, **feature):
        adapter = GdacsAdapter(ctx=None, settings=GdacsSettings())
        payload = json.dumps({"features": [self._gdacs_feature(**feature)]}).encode()
        return self._push(client, adapter, payload)

    def _frames(self, client, event_id: str) -> list[dict]:
        response = client.get("/v1/map/frames.geojson", params={"eventId": event_id})
        return response.json()["features"]

    def test_advisory_becomes_an_official_cyclone_event(self, client):
        event = self._nhc(client)

        assert event.hazard_type.value == "CYCLONE"
        assert event.provenance_class.value == "AUTHORITATIVE_NOTICE"
        assert event.summary.storm_name == "Isaias"
        assert event.summary.max_wind_kt == 105.0

    def test_map_feed_carries_the_storm_name_wind_and_honest_label(self, client):
        self._nhc(client)

        features = client.get("/v1/map/events.geojson").json()["features"]
        (props,) = [f["properties"] for f in features if f["properties"]["hazardType"] == "CYCLONE"]

        assert props["stormName"] == "Isaias"
        assert props["maxWindKt"] == 105.0
        assert props["label"] == "Official tropical cyclone advisory"

    def test_geometry_is_served_separately_from_ash_styling(self, client):
        event = self._nhc(client)

        features = self._frames(client, event.id)
        types = sorted(f["properties"]["geometryType"] for f in features)

        assert types.count("CYCLONE_CONE") == 1
        assert types.count("CYCLONE_TRACK") == 1
        assert types.count("CYCLONE_POSITION") == 2
        assert types.count("CYCLONE_WIND_RADII") == 2
        assert {f["properties"]["styleClass"] for f in features} == {"cyclone"}

    def test_a_newer_advisory_replaces_rather_than_stacks_geometry(self, client):
        event = self._nhc(client, updated="2026-10-09T18:00:00.000Z")
        before = len(self._frames(client, event.id))

        newer = self._nhc(client, updated="2026-10-09T21:00:00.000Z", lat=29.0)

        assert newer.id == event.id
        assert len(self._frames(client, event.id)) == before

    def test_gdacs_and_nhc_reports_of_one_storm_are_one_event(self, client):
        first = self._gdacs(client)
        fused = self._nhc(client)

        assert fused.id == first.id
        assert sorted(fused.providers) == ["GDACS", "NHC"]
        # The agency's own position wins over the re-published one.
        assert fused.latitude == 28.4
        assert fused.provenance_class.value == "AUTHORITATIVE_NOTICE"

    def test_fusion_does_not_depend_on_which_agency_reports_first(self, client):
        first = self._nhc(client)
        fused = self._gdacs(client)

        assert fused.id == first.id
        assert fused.latitude == 28.4

    def test_a_differently_named_storm_nearby_stays_separate(self, client):
        isaias = self._nhc(client)
        rachel = self._nhc(client, storm_id="al102026", name="Rachel", lon=-87.0, lat=28.8)

        assert rachel.id != isaias.id

    def test_an_unnamed_report_must_be_close_to_merge(self, client):
        isaias = self._nhc(client)
        # 200 km away: inside the named radius, outside the unnamed one.
        other = self._gdacs(client, name="", lon=-87.3, lat=30.2)

        assert other.id != isaias.id

    def test_cyclones_never_generate_alerts(self, client):
        event = self._nhc(client)
        area = WatchArea(
            id="area_1",
            name="Gulf coast",
            geometry=circle_geojson(-87.2, 30.0, 300),
            hazard_types=[HazardType.CYCLONE],
        )

        send, reasons = should_alert(event, area, None, AlertType.INITIAL, AlertSettings())

        assert send is False
        assert reasons == ["CYCLONE_ALERTS_NOT_SUPPORTED"]


class TestProviderHealth:
    def test_disabled_providers_are_reported(self, client):
        providers = client.get("/v1/provider-health").json()["providers"]
        assert isinstance(providers, list)


class TestRealtime:
    def test_client_receives_hello_then_events(self, client):
        with client.websocket_connect("/v1/realtime") as socket:
            hello = socket.receive_json()
            assert hello["type"] == "hello"
            assert hello["resyncRequired"] is False

    def test_unreplayable_sequence_demands_resync(self, client):
        with client.websocket_connect("/v1/realtime?since=999999") as socket:
            assert socket.receive_json()["resyncRequired"] is True
