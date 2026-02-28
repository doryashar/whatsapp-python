# Observability Setup

This project uses OpenTelemetry for distributed tracing and structured JSON logging that integrates with Loki → Grafana → Alerts pipeline.

## Architecture

```
App (FastAPI)
    ↓
OpenTelemetry SDK (traces + structured logs)
    ↓
OTLP Collector (optional) or direct to Loki
    ↓
Loki (log aggregation)
    ↓
Grafana (visualization)
    ↓
Alerting (Grafana Alerts)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `""` | OTLP endpoint URL (e.g., `http://otel-collector:4317`) |
| `OTEL_SERVICE_NAME` | `whatsapp-api` | Service name for traces |
| `OTEL_SERVICE_VERSION` | `2.0.0` | Service version |
| `DEBUG` | `false` | Enable debug logging |

## Log Format

Logs are output in JSON format for easy parsing by Loki:

```json
{
  "timestamp": "2026-02-28T10:04:03.710256+00:00",
  "level": "INFO",
  "logger": "whatsapp",
  "message": "Starting WhatsApp API...",
  "module": "main",
  "function": "lifespan",
  "line": 18
}
```

## Grafana Loki Configuration

### promtail-config.yml

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: whatsapp-api
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        target_label: 'container'
      - source_labels: ['__meta_docker_container_log_stream']
        target_label: 'stream'
    pipeline_stages:
      - json:
          expressions:
            timestamp: timestamp
            level: level
            logger: logger
            message: message
            tenant: tenant
            event_type: event_type
      - labels:
          level:
          logger:
          tenant:
          event_type:
      - timestamp:
          source: timestamp
          format: RFC3339Nano
```

### loki-config.yml

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /loki/boltdb-shipper-active
    cache_location: /loki/boltdb-shipper-cache
    cache_ttl: 24h
    shared_store: filesystem
  filesystem:
    directory: /loki/chunks

compactor:
  working_directory: /loki/compactor
  shared_store: filesystem
  retention_enabled: true
  retention_delete_delay: 2h

limits_config:
  retention_period: 168h  # 7 days
```

## Grafana Dashboard

### dashboard.json

```json
{
  "dashboard": {
    "title": "WhatsApp API",
    "panels": [
      {
        "title": "Request Rate",
        "type": "timeseries",
        "targets": [
          {
            "expr": "sum(rate({app=\"whatsapp-api\"} |= \"level\" | json | line_format \"{{.level}}\" [5m]))",
            "legendFormat": "Requests/s"
          }
        ]
      },
      {
        "title": "Error Rate",
        "type": "timeseries",
        "targets": [
          {
            "expr": "sum(rate({app=\"whatsapp-api\"} |= \"ERROR\" [5m]))",
            "legendFormat": "Errors/s"
          }
        ]
      },
      {
        "title": "Connection Events",
        "type": "timeseries",
        "targets": [
          {
            "expr": "sum by (event_type) (count_over_time({app=\"whatsapp-api\"} | json | event_type != \"\" [1h]))",
            "legendFormat": "{{event_type}}"
          }
        ]
      },
      {
        "title": "Rate Limited IPs",
        "type": "stat",
        "targets": [
          {
            "expr": "count({app=\"whatsapp-api\"} |= \"429\")",
            "legendFormat": "Blocked Requests"
          }
        ]
      }
    ]
  }
}
```

## Grafana Alerts

### alerting.yaml

```yaml
groups:
  - name: whatsapp-api
    rules:
      - alert: HighErrorRate
        expr: |
          sum(rate({app="whatsapp-api"} |= "ERROR"[5m])) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate in WhatsApp API"
          description: "Error rate is {{ $value }} errors/s"

      - alert: WhatsAppDisconnected
        expr: |
          count_over_time({app="whatsapp-api"} |= "disconnected"[5m]) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "WhatsApp session disconnected"
          description: "A WhatsApp session has disconnected"

      - alert: RateLimitExceeded
        expr: |
          sum(rate({app="whatsapp-api"} |= "429"[5m])) > 1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High rate limit rejections"
          description: "Rate limit rejection rate is {{ $value }}/s"

      - alert: TenantBlocked
        expr: |
          count_over_time({app="whatsapp-api"} |= "blocked"[5m]) > 0
        for: 0m
        labels:
          severity: info
        annotations:
          summary: "IP blocked due to rate limiting"
          description: "An IP has been blocked"
```

## Docker Compose Example

```yaml
version: "3.8"

services:
  whatsapp-api:
    image: whatsapp-api:latest
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
      - OTEL_SERVICE_NAME=whatsapp-api
      - DATABASE_URL=postgresql://user:pass@postgres:5432/whatsapp
      - RATE_LIMIT_PER_MINUTE=60
      - RATE_LIMIT_PER_HOUR=1000
    depends_on:
      - postgres
      - otel-collector
    networks:
      - monitoring

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4317:4317"   # OTLP gRPC receiver
      - "4318:4318"   # OTLP http receiver
    depends_on:
      - loki
    networks:
      - monitoring

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    volumes:
      - ./loki-config.yml:/etc/loki/local-config.yaml
      - loki-data:/loki
    networks:
      - monitoring

  promtail:
    image: grafana/promtail:latest
    volumes:
      - ./promtail-config.yml:/etc/promtail/config.yml
      - /var/log:/var/log
      - /var/run/docker.sock:/var/run/docker.sock
    depends_on:
      - loki
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana
    depends_on:
      - loki
    networks:
      - monitoring

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=whatsapp
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - monitoring

volumes:
  loki-data:
  grafana-data:
  postgres-data:

networks:
  monitoring:
```

## otel-collector-config.yaml

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

exporters:
  loki:
    endpoint: http://loki:3100/loki/api/v1/push
    default_labels_enabled:
      exporter: false
      resource: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [logging]  # Add jaeger or other trace backends as needed
    logs:
      receivers: [otlp]
      exporters: [loki]
```
