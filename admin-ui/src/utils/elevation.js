/**
 * Bridge between the API client and the elevation prompt.
 *
 * When the server answers 403 ELEVATION_REQUIRED, api.js calls
 * `promptForElevation(permissionKey)`. That resolves once the user has either
 * completed the elevation (true) or dismissed the prompt (false). On true the
 * original request is retried once — the same shape as the existing silent
 * token-refresh retry, so callers never have to know elevation exists.
 */

let handler = null;

/** Registered by <ElevationGate /> on mount. */
export function registerElevationHandler(fn) {
  handler = fn;
  return () => {
    if (handler === fn) handler = null;
  };
}

export function promptForElevation(permissionKey) {
  // No prompt mounted (e.g. an unauthenticated shell) — fail the request rather
  // than hanging forever on a promise nothing can resolve.
  if (!handler) return Promise.resolve(false);
  return handler(permissionKey);
}
