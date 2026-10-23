# Phase 2 deployment validation evidence

The following checks were executed against the synthetic application during Phase 2. They establish local/container behavior and PostgreSQL migration readiness, not connectivity to Samsung systems. The final application regression results and any subsequent code-only checks are recorded in [PHASE2_VALIDATION](PHASE2_VALIDATION.md).

## PostgreSQL migration and preservation

The existing Compose volume `frip_frip-postgres` was retained throughout. It began at revision `0001` with one site, three tools, six chambers, 19 serialized components and 19 installation-history rows. A pre-migration database backup was made in temporary storage before the upgrade; temporary paths are not a persistent backup service.

In a Compose backend container, these commands all exited successfully:

```bash
alembic upgrade head
alembic upgrade head
alembic check
python -m app.seed
python -m app.seed
alembic check
```

The database finished at `0002`; `alembic check` reported **“No new upgrade operations detected.”** Original component identity and complete installation-history fingerprints matched their pre-upgrade values. All 19 original identities and all 19 original installation histories remained unchanged. Seeding added the two intended uninstalled demonstration spares, bringing serialized instances to 21, and registered three synthetic enterprise sources. No database reset was performed.

A separate fresh PostgreSQL database, `frip_phase2_validation`, was created for clean-install validation. Repeated migration and seed commands succeeded, followed by a clean `alembic check`. Inspection found 49 domain tables plus `alembic_version`. Six API probes passed: status-only health, application health, fleet, inventory, enterprise sources and Informs demonstration capabilities. All six manifests in the built image validated against the bundled JSON Schema.

The frozen migration SQL was also executed by the actual PostgreSQL parser inside a transaction with a separate schema/search path and **ROLLBACK**. This validated dialect-level DDL parsing without replacing or dropping the preserved application database.

## Container build and runtime

The backend image now copies `integration_manifests/` and `schemas/` alongside backend code and synthetic fixtures. Both images built successfully using their dependency locks. In this cloud machine, an approved proxy CA was supplied through the optional BuildKit `build_ca` secret; TLS verification and Python artifact hash verification remained enabled.

The executed build used temporary build and port overrides:

```bash
DOCKER_BUILDKIT=1 DOCKER_CONFIG=/tmp/frip-docker-config \
  docker compose -f compose.yaml \
  -f /tmp/frip-phase2-build.yaml -f /tmp/frip-phase2-ports.yaml \
  build --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY

DOCKER_CONFIG=/tmp/frip-docker-config \
  docker compose -f compose.yaml -f /tmp/frip-phase2-ports.yaml \
  up -d --no-build

docker exec frip-backend-1 alembic check
```

The build override used host build networking, a dynamically resolved approved proxy host entry, and the locally supplied trusted CA secret. The port override used loopback API port 28000 and UI port 28080 to avoid development-test conflicts. It did not expose PostgreSQL. Temporary override/config files are runtime artifacts and may disappear when the execution environment is replaced; recreate them using [cloud-build instructions](cloud-build.md). Standard workstation deployment remains `docker compose up --build -d`.

Observed runtime results:

- PostgreSQL, backend and frontend health checks all reported **healthy**.
- SHA-256 comparison verified **65 application, migration, fixture, manifest and schema files** in the running backend image against the frozen workspace used for that build.
- The built frontend HTML and both referenced JS/CSS assets loaded successfully.
- Five nginx-proxied API requests passed: application health, fleet, inventory, enterprise sources and Informs demonstration capabilities.
- Fleet data contained three tools and six chambers; source metadata contained three explicitly synthetic sources.
- The running image's `alembic check` was clean, and the preserved database remained at `0002` with its 19 original installation histories intact.

The final metadata-token implementation was included in the validated image: unchanged hints use complete validated document metadata, rather than content hash/revision alone. The source snapshot at that check had backend image `sha256:6b15b7586ec6768ad9272f3374ba8454cecc0e318fcd0ed38216147fbf58f390` and frontend image `sha256:df487ff0aa2bfe1e14b8203ebb85507bfd918bdac396915f4be1146467d59fcc`. Subsequent code-only fixes require a cached image rebuild and renewed runtime/hash checks; these identifiers are evidence of this run, not permanent release identifiers.

### Final code-only follow-up

After the final workflow change made retained-document metadata comparison cover the complete metadata envelope, the backend was rebuilt with the same trusted-CA/proxy configuration and restarted through Compose. The final build command selected `backend`; the frontend bundle was unchanged.

The resulting backend image is `sha256:bbbe9fadafdb53681e992875dcda73fd91f7fd3bf1a1e9cb85f32e558a5237e3`. Frontend image remains `sha256:df487ff0aa2bfe1e14b8203ebb85507bfd918bdac396915f4be1146467d59fcc`.

The final runtime recheck passed: all three containers healthy; all **65** application/migration/fixture/manifest/schema file hashes equal the final frozen workspace; frontend HTML and two assets loaded; the same five nginx-proxied API requests returned the expected synthetic fleet/source data; and the running backend's `alembic check` again reported no new upgrade operations. The preserved volume was reused without reset. Fresh-database and preservation checks above were not unnecessarily repeated for this code-only change.

## Automated backend check

After the metadata-token wiring, from `backend/`:

```bash
../.venv/bin/python -m pytest -q
```

Result: **162 passed in 36.64 seconds**, with one existing Starlette/AnyIO deprecation warning. The targeted connector/document and orchestration suites also passed together: 33 tests. This evidence does not replace the final regression ledger after later changes.

No real source was connected, no credentials were committed, no TLS/package verification was disabled, and no equipment or production-source writeback was attempted.
