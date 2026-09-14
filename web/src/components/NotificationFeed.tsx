import type { NotificationRecord } from "../api/types";
import { utcTime } from "./format";

interface Props {
  notifications: NotificationRecord[];
  onSelect: (eventId: string) => void;
  onMarkRead: (id: string) => void;
}

/**
 * Alerts sit on the opaque tier. Safety copy must not depend on whatever the
 * map happens to be showing behind it.
 */
export function NotificationFeed({
  notifications,
  onSelect,
  onMarkRead,
}: Props): React.JSX.Element {
  return (
    <section className="panel glass grow">
      <header className="panel-head">
        <span className="panel-title">Alerts</span>
        <span className="tag">{notifications.filter((n) => n.readAt === null).length} unread</span>
      </header>

      <div className="panel-body">
        {notifications.length === 0 ? (
          <p className="empty">
            No alerts yet.
            <br />
            Add a watch area to be told about events near a place you care about.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: 10 }}>
            {notifications.map((notification) => (
              <article
                key={notification.id}
                className={`alert solid ${notification.alertType}`}
                style={{ opacity: notification.readAt ? 0.6 : 1 }}
              >
                <span className="alert-title">{notification.title}</span>
                <span className="alert-body">{notification.body}</span>
                <div className="alert-foot">
                  <span style={{ fontSize: 10, color: "var(--fg-faint)" }}>
                    {utcTime(notification.createdAt)} · {notification.alertType}
                  </span>
                  <span style={{ display: "flex", gap: 5 }}>
                    <button
                      className="btn ghost"
                      onClick={() => onSelect(notification.eventId)}
                      type="button"
                    >
                      Show
                    </button>
                    {notification.readAt === null ? (
                      <button
                        className="btn ghost"
                        onClick={() => onMarkRead(notification.id)}
                        type="button"
                      >
                        Dismiss
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
