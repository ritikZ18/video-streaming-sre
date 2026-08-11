# Public gateway: one nginx that fronts upload-api (reads), beacon-collector and
# the origin, and is the single Cloudflare-tunnel target. See default.conf.
FROM nginx:1.30-alpine

# Replace the stock server block with ours.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY default.conf /etc/nginx/conf.d/default.conf

EXPOSE 8088

# Liveness: the same endpoint the tunnel verifier uses.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost:8088/healthz >/dev/null 2>&1 || exit 1
