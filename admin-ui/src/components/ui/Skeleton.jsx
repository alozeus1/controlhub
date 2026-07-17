import "./Skeleton.css";

/** Base shimmer block. */
export function Skeleton({ width = "100%", height = 14, radius = 6, className = "", style = {} }) {
  return (
    <span
      className={`skeleton ${className}`}
      style={{ width, height, borderRadius: radius, ...style }}
      aria-hidden="true"
    />
  );
}

/** Row of stat-card skeletons. */
export function SkeletonStats({ count = 4 }) {
  return (
    <div className="skeleton-stats">
      {Array.from({ length: count }).map((_, i) => (
        <div className="skeleton-stat-card" key={i}>
          <Skeleton width={46} height={46} radius={12} />
          <div className="skeleton-stat-lines">
            <Skeleton width="55%" height={20} />
            <Skeleton width="80%" height={12} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Table placeholder with shimmering rows. */
export function SkeletonTable({ rows = 6, cols = 4 }) {
  return (
    <div className="skeleton-table" role="status" aria-label="Loading">
      <div className="skeleton-table-head">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} width={i === 0 ? "40%" : "60%"} height={12} />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div className="skeleton-table-row" key={r}>
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} width={c === 0 ? "70%" : "50%"} height={14} />
          ))}
        </div>
      ))}
    </div>
  );
}

export default Skeleton;
