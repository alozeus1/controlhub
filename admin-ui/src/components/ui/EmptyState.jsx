import AppIcon from "./AppIcon";
import "./EmptyState.css";

/**
 * Unified empty-state used across every page.
 * Outline icon inside a soft-glowing cyan chip (no emoji), consistent type
 * scale, optional one-line hint, and an optional primary CTA.
 *
 * Props:
 *  - icon: AppIcon name (default "folder")
 *  - title: string
 *  - subtitle: string
 *  - hint: string (optional, muted one-liner)
 *  - action: ReactNode (optional, e.g. a <Button>)
 */
export default function EmptyState({ icon = "folder", title, subtitle, hint, action }) {
  return (
    <div className="empty-state-v2" role="status">
      <div className="empty-state-v2-chip">
        <AppIcon name={icon} size={26} />
      </div>
      {title && <h3 className="empty-state-v2-title">{title}</h3>}
      {subtitle && <p className="empty-state-v2-subtitle">{subtitle}</p>}
      {hint && <p className="empty-state-v2-hint">{hint}</p>}
      {action && <div className="empty-state-v2-action">{action}</div>}
    </div>
  );
}
