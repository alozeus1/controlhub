// The API stores and emits UTC timestamps WITHOUT a timezone suffix
// (e.g. "2026-07-08T20:01:01.123456"). new Date() would misread those as
// local time, displaying the UTC clock face in every timezone. These helpers
// pin zone-less strings to UTC so everything renders in the viewer's local
// timezone automatically.

export function parseApiDate(value) {
  if (!value) return null;
  let normalized = value;
  if (typeof value === "string" && !/([zZ]|[+-]\d{2}:?\d{2})$/.test(value)) {
    normalized = `${value}Z`;
  }
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value) {
  const date = parseApiDate(value);
  return date ? date.toLocaleString() : "—";
}

export function formatDate(value) {
  const date = parseApiDate(value);
  return date ? date.toLocaleDateString() : "—";
}
