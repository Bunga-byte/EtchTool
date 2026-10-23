# Optional trusted-proxy Docker build

Ordinary workstation operation remains `docker compose up --build -d`. This page describes an additional cloud-build path for a machine whose approved outbound proxy signs TLS with a locally supplied trusted CA. It is not required by the application, and it does not create a new VPN or bypass platform networking.

Both Dockerfiles accept an optional BuildKit secret named `build_ca`. If supplied, the Python dependency-install step combines that CA with the image's existing CA bundle through `PIP_CERT`; npm uses `NODE_EXTRA_CA_CERTS`. The secret and temporary combined bundle are not retained in the final image. Package hashes and TLS verification remain enabled. Do not use insecure-host options, disable certificate verification, or copy proxy credentials into the repository.

The cloud environment supplies the trusted CA at `/usr/local/share/ca-certificates/environment-proxy-ca.crt`. Cloud validation used a **temporary** Compose override with build networking set to `host`, an `extra_hosts` entry for the proxy resolved from the running machine, and that file supplied as a BuildKit secret. Proxy host/IP information is runtime infrastructure state and is deliberately not hard-coded in the repository.

For an authorized machine with that CA and existing `HTTPS_PROXY`/`HTTP_PROXY` configuration, the following creates a temporary override, derives the current proxy hostname/address without displaying credentials, and forwards the existing proxy settings as Docker's predefined build arguments:

```bash
(
  set -euo pipefail
  export DOCKER_CONFIG=/tmp/frip-docker-config
  mkdir -p "$DOCKER_CONFIG"
  read -r FRIP_PROXY_HOST FRIP_PROXY_IP < <(python3 - <<'PY'
import os, socket
from urllib.parse import urlparse
proxy = urlparse(os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY') or '')
if not proxy.hostname:
    raise SystemExit('An approved proxy must already be configured')
print(proxy.hostname, socket.gethostbyname(proxy.hostname))
PY
  )
  export FRIP_PROXY_HOST FRIP_PROXY_IP
  FRIP_BUILD_OVERRIDE="$(mktemp /tmp/frip-build-override.XXXXXX.yaml)"
  trap 'rm -f "$FRIP_BUILD_OVERRIDE"' EXIT
  cat > "$FRIP_BUILD_OVERRIDE" <<'YAML'
services:
  backend:
    build:
      network: host
      extra_hosts:
        - "${FRIP_PROXY_HOST}:${FRIP_PROXY_IP}"
      secrets:
        - build_ca
  frontend:
    build:
      network: host
      extra_hosts:
        - "${FRIP_PROXY_HOST}:${FRIP_PROXY_IP}"
      secrets:
        - build_ca
secrets:
  build_ca:
    file: /usr/local/share/ca-certificates/environment-proxy-ca.crt
YAML
  docker compose -f compose.yaml -f "$FRIP_BUILD_OVERRIDE" build \
    --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY
)
```

`DOCKER_CONFIG` points to writable temporary storage because the cloud user's home configuration can be read-only. This example does not perform a registry login or copy credentials. Use the approved credential flow if an internal registry requires authentication. Host build networking is an environment-specific troubleshooting accommodation; runtime database and application networking remain defined by the standard Compose file. If the cloud changes its proxy or trusted-CA contract, adapt the temporary override using the supported platform configuration rather than persisting an old address.

The GitLab browser example uses the Playwright image matching the npm-locked Playwright version, with a modern Node runtime and Python 3.12 available for the backend test server. It installs `python3-venv` and creates the repository `.venv` expected by `frontend/playwright.config.ts`. Update the CI image whenever that Playwright dependency changes. Local successful tests do not imply that a particular GitLab runner or corporate registry has been validated.
