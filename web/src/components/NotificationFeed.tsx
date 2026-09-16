import { useState } from "react";
import { api } from "../api/client";
import type { NotificationRecord } from "../api/types";
import { useTimeZone } from "../state/timeZone";
import { timeIn } from "./format";

interface Props {
  notifications: NotificationRecord[];
  onSelect: (eventId: string) => void;
  onMarkRead: (id: string) => void;
  onArchive: (id: string) => void;
  onClose: () => void;
}

/**
 * Alerts sit on the opaque tier. Safety copy must not depend on whatever the
 * map happens to be showing behind it.
 */
export function NotificationFeed({
  notifications,
  onSelect,
  onMarkRead,
  onArchive,
  onClose,
}: Props): React.JSX.Element {
  const { zone } = useTimeZone();
  const [history, setHistory] = useState<NotificationRecord[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const openHistory = (): void => {
    setHistoryError(null);
    api
      .notifications({ archived: true })
      .then((r) => setHistory(r.notifications))
      .catch((cause: unknown) =>
        setHistoryError(cause instanceof Error ? cause.message : "could not load history"),
      );
  };

  const showingHistory = history !== null;
  const list = showingHistory ? history : notifications;

  return (
    <section className="panel glass grow">
      <header className="panel-head">
        <span className="panel-title">{showingHistory ? "Archived alerts" : "Alerts"}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {showingHistory ? (
            <button className="btn ghost" onClick={() => setHistory(null)} type="button">
              Back
            </button>
          ) : (
            <>
              <span className="tag">
                {notifications.filter((n) => n.readAt === null).length} unread
              </span>
              <button className="btn ghost" onClick={openHistory} type="button">
                History
              </button>
            </>
          )}
          <button className="btn ghost" onClick={onClose} type="button" aria-label="Close">
            ✕
          </button>
        </div>
      </header>

      <div className="panel-body">
        {historyError ? <p className="list-error">{historyError}</p> : null}
        {list.length === 0 ? (
          <p className="empty">
            {showingHistory ? (
              "No archived alerts."
            ) : (
              <>
                No alerts yet.
                <br />
                Add a watch area to be told about events near a place you care about.
              </>
            )}
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: 10 }}>
            {list.map((notification) => (
              <article
                key={notification.id}
                className={`alert solid ${notification.alertType}`}
                style={{ opacity: notification.readAt ? 0.6 : 1 }}
              >
                <span className="alert-title">{notification.title}</span>
                <span className="alert-body">{notification.body}</span>
                <div className="alert-foot">
                  <span style={{ fontSize: 10, color: "var(--fg-faint)" }}>
                    {timeIn(zone, notification.createdAt)} · {notification.alertType}
                    {notification.readAt ? <span className="tag read-tag">Read</span> : null}
                  </span>
                  <span style={{ display: "flex", gap: 5 }}>
                    <button
                      className="btn ghost"
                      onClick={() => {
                        onSelect(notification.eventId);
                        if (!showingHistory && notification.readAt === null) {
                          onMarkRead(notification.id);
                        }
                      }}
                      type="button"
                    >
                      Show
                    </button>
                    {!showingHistory && notification.readAt === null ? (
                      <button
                        className="btn ghost"
                        onClick={() => onMarkRead(notification.id)}
                        type="button"
                      >
                        Dismiss
                      </button>
                    ) : null}
                    {!showingHistory && notification.readAt !== null ? (
                      <button
                        className="btn ghost"
                        onClick={() => onArchive(notification.id)}
                        type="button"
                      >
                        Archive
                      </button>
                    ) : null}
                  </span>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
