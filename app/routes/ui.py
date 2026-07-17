# REMOVED (audit finding A-5).
#
# This module previously defined a legacy, server-rendered `ui` blueprint that:
#   - implemented a SECOND, parallel session-cookie JWT auth path that
#     contradicted the SPA bearer-token model,
#   - hardcoded `API_BASE = "http://localhost:9000"` (broken outside local dev),
#   - exposed `/ui/admin` as an unauthenticated server-rendered shell.
#
# The production UI is the React SPA served by nginx at `/ui/*`. The blueprint
# was dead in the nginx-fronted deployment and only reachable on the direct API
# port, so it was removed to eliminate the parallel auth surface.
#
# Intentionally left with no `ui_bp` symbol so any accidental re-import fails
# loudly instead of silently re-registering the old routes.
