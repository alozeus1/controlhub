// Grammar helpers for counts. `1 contact`, `2 contacts`, etc.

export function pluralize(count, singular, plural) {
  const n = Number(count) || 0;
  return n === 1 ? singular : (plural || `${singular}s`);
}

// Returns "1 contact" / "3 contacts". Set withCount=false to get just the noun.
export function countLabel(count, singular, plural) {
  const n = Number(count) || 0;
  return `${n.toLocaleString()} ${pluralize(n, singular, plural)}`;
}
