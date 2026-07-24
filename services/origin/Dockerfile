FROM nginx:1.25-alpine

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d /etc/nginx/conf.d
COPY scripts/healthcheck.sh /healthcheck.sh

RUN chmod +x /healthcheck.sh

# The non-root appuser must be able to create nginx's cache/temp dirs, write the
# pid file, and log — otherwise nginx aborts on startup with EACCES.
RUN mkdir -p /var/cache/nginx /var/run \
 && chown -R appuser:appgroup /var/cache/nginx /var/run /var/log/nginx /etc/nginx/conf.d \
 && touch /var/run/nginx.pid \
 && chown appuser:appgroup /var/run/nginx.pid

USER appuser

EXPOSE 8080 9113

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD /healthcheck.sh

