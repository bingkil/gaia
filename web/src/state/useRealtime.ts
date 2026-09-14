import { useCallback, useEffect, useRef, useState } from "react";
import { RealtimeClient, type RealtimeStatus } from "../api/realtime";
import type { RealtimeMessage } from "../api/types";

/**
 * Live bus subscription.
 *
 * Refetches are coalesced: a burst of revisions on one event should cause one
 * reload, not one per message.
 */
export function useRealtime(onChange: (subjects: Set<string>) => void): RealtimeStatus {
  const [status, setStatus] = useState<RealtimeStatus>("connecting");
  const callbackRef = useRef(onChange);
  callbackRef.current = onChange;

  useEffect(() => {
    const pending = new Set<string>();
    let timer: number | null = null;

    const flush = (): void => {
      timer = null;
      const subjects = new Set(pending);
      pending.clear();
      callbackRef.current(subjects);
    };

    const schedule = (subject: string): void => {
      pending.add(subject);
      if (timer === null) timer = window.setTimeout(flush, 400);
    };

    const client = new RealtimeClient({
      onMessage: (message: RealtimeMessage) => schedule(message.type),
      onStatus: setStatus,
      onResyncRequired: () => schedule("resync"),
    });
    client.connect();

    return () => {
      if (timer !== null) window.clearTimeout(timer);
      client.close();
    };
  }, []);

  return status;
}

export function useNotificationPermission(): [NotificationPermission, () => void] {
  const [permission, setPermission] = useState<NotificationPermission>(() =>
    "Notification" in window ? Notification.permission : "denied",
  );

  const request = useCallback(() => {
    if (!("Notification" in window)) return;
    void Notification.requestPermission().then(setPermission);
  }, []);

  return [permission, request];
}
