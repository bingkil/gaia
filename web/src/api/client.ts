import type {
  AlertDecision,
  EventDetail,
  FirmsKeyStatus,
  HazardEvent,
  ImpactResponse,
  Meta,
  NotificationRecord,
  Observation,
  ProviderRecord,
  RefreshResult,
  SettingsResponse,
  WatchArea,
} from "./types";

class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  meta: () => request<Meta>("/v1/meta"),

  events: (
    params: {
      sinceHours?: number;
      since?: string;
      until?: string;
      minMagnitude?: number;
      hazardType?: string;
    } = {},
  ) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    return request<{ events: HazardEvent[]; generatedAt: string; count: number }>(
      `/v1/events?${query}`,
    );
  },

  event: (id: string) => request<EventDetail>(`/v1/events/${id}`),

  revisions: (id: string) =>
    request<{ revisions: Record<string, unknown>[] }>(`/v1/events/${id}/revisions`),

  observations: (id: string) =>
    request<{ observations: Observation[] }>(`/v1/events/${id}/observations`),

  rawPayload: (eventId: string, observationId: string) =>
    request<{ payload: string; sha256: string; objectKey: string; provider: string }>(
      `/v1/events/${eventId}/raw/${observationId}`,
    ),

  mapEvents: (
    params: {
      sinceHours?: number;
      since?: string;
      until?: string;
      minMagnitude?: number;
      hazardType?: string;
    } = {},
  ) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    return request<GeoJSON.FeatureCollection>(`/v1/map/events.geojson?${query}`);
  },

  mapFrames: (eventId?: string) =>
    request<GeoJSON.FeatureCollection>(
      `/v1/map/frames.geojson${eventId ? `?eventId=${eventId}` : ""}`,
    ),

  impact: (longitude: number, latitude: number, eventId?: string) =>
    request<ImpactResponse>("/v1/impact/point", {
      method: "POST",
      body: JSON.stringify({ longitude, latitude, eventId }),
    }),

  watchAreas: () => request<{ watchAreas: WatchArea[] }>("/v1/watch-areas"),

  createWatchArea: (body: {
    name: string;
    longitude: number;
    latitude: number;
    radiusKm: number;
    minMagnitude: number;
  }) => request<WatchArea>("/v1/watch-areas", { method: "POST", body: JSON.stringify(body) }),

  updateWatchArea: (
    id: string,
    body: {
      name: string;
      longitude: number;
      latitude: number;
      radiusKm: number;
      minMagnitude: number;
    },
  ) => request<WatchArea>(`/v1/watch-areas/${id}`, { method: "PUT", body: JSON.stringify(body) }),

  deleteWatchArea: (id: string) =>
    request<void>(`/v1/watch-areas/${id}`, { method: "DELETE" }),

  notifications: () =>
    request<{ notifications: NotificationRecord[] }>("/v1/notifications"),

  markRead: (id: string) =>
    request<void>(`/v1/notifications/${id}/read`, { method: "POST" }),

  alertDecisions: (eventId: string) =>
    request<{ decisions: AlertDecision[] }>(`/v1/alert-decisions/${eventId}`),

  providerHealth: () =>
    request<{ providers: ProviderRecord[]; generatedAt: string }>("/v1/provider-health"),

  ingestVaa: (bulletin: string) =>
    request<{ event: HazardEvent; frameCount: number; parserWarnings: string[] }>(
      "/v1/ingest/vaa",
      { method: "POST", body: JSON.stringify({ bulletin }) },
    ),

  refreshProviders: (provider?: string) =>
    request<{ results: RefreshResult[]; requestedAt: string }>("/v1/providers/refresh", {
      method: "POST",
      body: JSON.stringify({ provider: provider ?? null }),
    }),

  settings: () => request<SettingsResponse>("/v1/settings"),

  setFirmsKey: (mapKey: string) =>
    request<FirmsKeyStatus>("/v1/settings/firms-key", {
      method: "PUT",
      body: JSON.stringify({ mapKey }),
    }),

  clearFirmsKey: () => request<FirmsKeyStatus>("/v1/settings/firms-key", { method: "DELETE" }),
};

export { ApiError };
