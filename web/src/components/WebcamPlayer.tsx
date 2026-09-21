import { useEffect, useState } from "react";
import type { Webcam } from "../api/types";

const IMAGE_REFRESH_MS = 15_000;

type Tier = "video" | "image" | "thumbnail" | "none";

function firstTier(webcam: Webcam): Tier {
  if (webcam.stream_url) return "video";
  if (webcam.image_url) return "image";
  if (webcam.thumbnail_url) return "thumbnail";
  return "none";
}

/**
 * Tries live video, then a refreshing still, then a static thumbnail,
 * falling back only on a genuine load error at each tier so a broken link
 * never gets silently presented as a working camera.
 */
export function WebcamPlayer({ webcam }: { webcam: Webcam }): React.JSX.Element {
  const [tier, setTier] = useState<Tier>(() => firstTier(webcam));
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    setTier(firstTier(webcam));
  }, [webcam]);

  useEffect(() => {
    if (tier !== "image") return;
    const id = window.setInterval(() => setRefreshTick((t) => t + 1), IMAGE_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [tier]);

  const fallBackFrom = (from: Tier): void => {
    if (from === "video") setTier(webcam.image_url ? "image" : webcam.thumbnail_url ? "thumbnail" : "none");
    else if (from === "image") setTier(webcam.thumbnail_url ? "thumbnail" : "none");
    else setTier("none");
  };

  return (
    <div className="webcam-player">
      {tier === "video" && webcam.stream_url ? (
        <video
          key={webcam.stream_url}
          src={webcam.stream_url}
          autoPlay
          muted
          playsInline
          controls
          onError={() => fallBackFrom("video")}
        />
      ) : tier === "image" && webcam.image_url ? (
        <img
          key="image"
          src={`${webcam.image_url}${webcam.image_url.includes("?") ? "&" : "?"}t=${refreshTick}`}
          alt={webcam.name}
          onError={() => fallBackFrom("image")}
        />
      ) : tier === "thumbnail" && webcam.thumbnail_url ? (
        <img
          key="thumbnail"
          src={webcam.thumbnail_url}
          alt={webcam.name}
          onError={() => fallBackFrom("thumbnail")}
        />
      ) : (
        <div className="webcam-unavailable">Camera unavailable</div>
      )}
      <div className="webcam-caption">
        <span>{webcam.name}</span>
        {webcam.source_url ? (
          <a href={webcam.source_url} target="_blank" rel="noopener noreferrer">
            Source
          </a>
        ) : null}
      </div>
    </div>
  );
}
