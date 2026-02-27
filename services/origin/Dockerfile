FROM nginx:1.25-alpine

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d /etc/nginx/conf.d
COPY scripts/healthcheck.sh /healthcheck.sh

RUN chmod +x /healthcheck.sh

USER appuser

EXPOSE 8080 9113

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD /healthcheck.sh

