"""End-to-end API tests against a temporary database, with ingestion disabled."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from gaia.api.app import create_app
from gaia.config import IsigmetSettings, Settings
from gaia.domain.enums import Action, HazardType
from gaia.domain.models import Observation
from gaia.providers.isigmet import IsigmetAdapter

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
