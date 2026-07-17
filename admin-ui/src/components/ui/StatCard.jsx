import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import AppIcon from "./AppIcon";
import "./StatCard.css";

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Animated count-up that respects reduced-motion. */
function useCountUp(target, duration = 900) {
  const numeric = typeof target === "number" ? target : parseFloat(target);
  const isNumeric = !Number.isNaN(numeric);
  const [value, setValue] = useState(isNumeric && !prefersReducedMotion() ? 0 : numeric);
  const raf = useRef(null);

  useEffect(() => {
    if (!isNumeric || prefersReducedMotion()) {
      setValue(numeric);
      return;
    }
    const start = performance.now();
    const from = 0;
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      setValue(Math.round(from + (numeric - from) * eased));
      if (t < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => raf.current && cancelAnimationFrame(raf.current);
  }, [numeric, isNumeric, duration]);

  return isNumeric ? value : target;
}

/**
 * Elevated stat card with icon chip + animated count-up.
 * Props: icon, value, label, to?, accent? ("cyan"|"green"|"amber"|"violet"|"red")
 */
export default function StatCard({ icon = "dashboard", value = 0, label, to, accent = "cyan" }) {
  const shown = useCountUp(value);
  const inner = (
    <>
      <div className={`stat-card-v2-icon accent-${accent}`}>
        <AppIcon name={icon} size={22} />
      </div>
      <div className="stat-card-v2-content">
        <div className="stat-card-v2-value">{shown}</div>
        <div className="stat-card-v2-label">{label}</div>
      </div>
    </>
  );
  if (to) {
    return <Link to={to} className="stat-card-v2">{inner}</Link>;
  }
  return <div className="stat-card-v2">{inner}</div>;
}
