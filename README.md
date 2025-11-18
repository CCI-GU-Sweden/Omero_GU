# Omero_GU

A lightweight web interface and utility layer for interacting with an existing **OMERO.server** installation.  
This repository contains the application code, uWSGI configuration, and deployment instructions for running the service in production (e.g. **OpenShift / Kubernetes**) as well as locally for development.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Configuration](#configuration)
- [Authentication & 2FA](#authentication--2fa)
- [Local Development](#local-development)
- [Container Build](#container-build)
- [OpenShift / Kubernetes Deployment](#openshift--kubernetes-deployment)
- [Optional Components](#optional-components)
- [Health Checks](#health-checks)
- [Logging & Monitoring](#logging--monitoring)
- [Known Limitations](#known-limitations)
- [License](#license)

---

## Overview

**Omero_GU** provides a lightweight web GUI to interact with **OMERO** datasets and integrate custom workflows.  
It is designed to run as a small containerized service with:

- uWSGI as the application server  
- Redis for caching and/or session management  
- Optional PostgreSQL for usage tracking  

The app connects to an external OMERO.server instance; it does **not** host OMERO itself.

---

## Features

- Web interface for OMERO data browsing [TOWRITE]  
- API endpoints for GU workflows [TOWRITE]  
- Optional usage logging into PostgreSQL [TOCHECK]  
- Container-friendly design  
- Minimal runtime dependencies

---

## Architecture

+-----------------+  
| Omero_GU App | <-- uWSGI + Python app  
| &ensp;&ensp;(Container) &ensp;&ensp;|  
+-----------------+  
&ensp;&ensp;&ensp;&ensp;&ensp;|  
&ensp;&ensp;&ensp;&ensp;&ensp;| Redis (required)  
&ensp;&ensp;&ensp;&ensp;&ensp;v  
&ensp;+-----------+  
&ensp;|&ensp;&ensp; Redis &ensp;&ensp;|  
&ensp;+-----------+  
&ensp;&ensp;&ensp;&ensp;&ensp;|  
&ensp;&ensp;&ensp;&ensp;&ensp;| PostgreSQL (optional)  
&ensp;&ensp;&ensp;&ensp;&ensp;v  
+---------------+  
| &ensp;Postgres DB &ensp;|  
+---------------+  
&ensp;&ensp;&ensp;&ensp;&ensp;|  
&ensp;&ensp;&ensp;&ensp;&ensp;| OMERO.server (external)  
&ensp;&ensp;&ensp;&ensp;&ensp;v  
+----------------+  
| OMERO Server |  
+----------------+

### Components

- **Omero_GU container**
  - Runs uWSGI with config in `uwsgi.ini`.
  - Stateless except for Redis/Postgres dependencies.

- **Redis**
  - Required.
  - Used for [TOCHECK: sessions? caching? task queue?]

- **PostgreSQL**
  - Optional.
  - Stores usage logs / analytics data.
  - App still runs without it.

- **OMERO.server**
  - Must be an existing running OMERO installation.
  - The app connects via host/port configured at runtime.

---

## Requirements

Runtime dependencies:

- Python 3.9+ [TOCHECK]
- Redis 6+ (or managed Redis)
- Optional: PostgreSQL 12+
- OMERO.server version [TOFILL]

For deployment:

- Docker/Podman or OpenShift BuildConfig  
- OpenShift 4+ or generic Kubernetes 1.22+  
- Route/Ingress controller for external access

---

## Configuration

Configuration values can be provided via environment variables or a ConfigMap/Secret in OpenShift.  
Defaults live in `conf.py`.

### OMERO connection

| Variable | Description |
|----------|-------------|
| `OMERO_HOST` | Hostname of OMERO.server |
| `OMERO_PORT` | Port of OMERO.server |
| `OMERO_SSL` | `true/false` [TOCHECK] |

### Redis

| Variable | Description |
|----------|-------------|
| `REDIS_HOST` | Redis hostname |
| `REDIS_PORT` | Default 6379 |
| `REDIS_DB` | Redis DB index [TOFILL if used] |
| `REDIS_PASSWORD` | If applicable |

### PostgreSQL (optional)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Full connection string OR |
| `PGHOST`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` | Split configuration |

If these are **not provided**, the app will:

- start normally  
- disable usage logging  
- emit warnings in logs  

### Application settings

| Variable | Description |
|----------|-------------|
| `APP_PORT` | Internal port for uWSGI (default [TOFILL]) |
| `APP_ENV` | `development` or `production` |
| `DEBUG` | Enable debug mode (dev only) |

---

## Authentication & 2FA

The application uses the **university OAuth2 provider** with mandatory **2-factor authentication**.

### Flow

1. User clicks “Login”.
2. User is redirected to the university’s OAuth2/SSO system.
3. 2FA is handled *entirely* by the university IdP.
4. After authentication, the user receives an **OAuth access token** to paste in the app  
5. The app generates a temporary **OMERO CLI web token** and performs operations on behalf of the user.

### Required OAuth variables

| Variable | Description |
|----------|-------------|
| `OAUTH_CLIENT_ID` | App client ID |
| `OAUTH_CLIENT_SECRET` | App secret (store in OpenShift Secret) |
| `OAUTH_AUTH_URL` | Authorization endpoint |
| `OAUTH_TOKEN_URL` | Token endpoint |
| `OAUTH_REDIRECT_URI` | Callback URL (must match Route) |
| `OAUTH_LOGOUT_URL` | Logout endpoint [TOCHECK] |

---

## Local Development

```bash
git clone https://github.com/CCI-GU-Sweden/Omero_GU.git
cd Omero_GU

# create venv
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

# start Redis locally
docker run -p 6379:6379 redis

# optional: local postgres
docker run -p 5432:5432 -e POSTGRES_PASSWORD=pass postgres
```

Run app (choose one):

1. Development mode

```bash
export FLASK_ENV=development  # [TOCHECK if applicable]
python app.py  # or the correct entrypoint [TOCHECK]
```

2. uWSGI (production-like)

```bash
uwsgi --ini uwsgi.ini
```

## Container Build

### Build

```bash
podman build -t omero_gu:latest .
# or docker build -t omero_gu:latest .
```

### Run locally

```bash
podman run -p 8080:8080 \
  -e REDIS_HOST=host.containers.internal \
  omero_gu:latest
```

(Ensure Redis is reachable by the container.)

## OpenShift / Kubernetes Deployment

A typical deployment consists of:

1. App Deployment

    - Image: omero_gu:[VERSION]
    - Command: uwsgi --ini /app/uwsgi.ini
    - Inject environment variables via:
        - ConfigMap (non-secrets)
        - Secret (passwords, tokens)

2. Redis Deployment

A simple YAML such as:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: redis
          image: redis:7
          ports:
            - containerPort: 6379
```

No special configuration is required. A plain Redis instance works.

3. PostgreSQL Deployment (optional)

You may use:

- OpenShift’s built-in PostgreSQL template
- A managed external PostgreSQL
- A simple Deployment with a PVC

4. Service + Route

Expose the app:

```yaml
kind: Service
spec:
  ports:
    - port: 8080
```

```yaml
kind: Route
spec:
  tls:
    termination: edge
```

[TOFILL: Internal app port, targetPort, TLS requirements]

5. Persistent Volume Claims

    - PostgreSQL requires a PVC
    - Redis persistence is optional [TOCHECK]

## Optional Components

### Usage Logging Database

If PostgreSQL is configured, the app logs the user activity.

If not configured:

- the feature is disabled
- app core functionality is unaffected

### Additional Integrations

[TOFILL if app uses external APIs, LDAP auth, OMERO tokens, etc.]

## Health Checks

No Health check in current version!

Recommended endpoints:

- Liveness: /ping or /health [TOCHECK]
- Readiness: optionally check:
    - Redis connectivity
    - OMERO connectivity

## Logging & Monitoring

Application logs go to stdout/stderr inside the container.

Collect logs using:

- OpenShift Logging
- Loki/Grafana
- Any cluster-wide log collector

No special log format is required.
[TOFILL if structured logging is used]

## Known Limitations

- Heavy reliance on OMERO CLI.
- OAuth/2FA requires university IdP.
- Requires an existing OMERO.server; does not deploy OMERO.
- PostgreSQL usage logging is optional and may produce warnings when disabled.
- Redis required for stable operation.
- Scaling horizontally requires a shared Redis backend.

## License

Copyright (c) 2024 LECLERC Simon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
