# Plan: Add CZI Pyramid Detection and Generation in Deployment (Linux)

## Goal
Introduce ZEISS czi-pyramidizer into the server-side import pipeline so that old CZI files that lack a multi-resolution pyramid are fixed before OMERO import.

Target behavior:
- Keep CZI as CZI whenever possible.
- Detect whether a pyramid is required.
- Build the pyramid only when needed.
- Remove (or heavily reduce) CZI -> OME-TIFF conversion for old/large CZI files.

---

## Why this change

### Current pain
- Some old CZI files do not contain pyramids.
- Missing pyramids cause poor visualization performance in viewers (OMERO-side rendering workflows).
- Current workaround uses CZI -> OME-TIFF conversion for selected cases, which can be costly for large files and introduces extra processing/storage overhead.

### Why czi-pyramidizer
- It is designed specifically for this exact problem: add pyramids to existing CZI files.
- It supports a check-only mode, so we can avoid unnecessary processing.
- It allows a clean decision path: check -> build only if needed -> continue import.

---

## Current code touchpoints (for future implementation)
- CZI conversion decision currently lives in src/common/image_funcs.py (file_format_splitter).
- Conversion controls currently live in src/common/conf.py (FORCE_CZI_CONVERSION, CZI_CONVERT_MIN_BYTES, TO_CONVERT_SCOPE).
- Import orchestration runs via src/omerofrontend/file_importer.py.

This plan keeps those touchpoints but changes the CZI branch behavior.

---

## High-level design

### New CZI branch behavior
For CZI input files in import flow:
1. Run czi-pyramidizer with --check-only.
2. If pyramid is needed, run czi-pyramidizer to generate a pyramidized CZI output.
3. Continue import using the resulting CZI file path.
4. Skip CZI -> OME-TIFF conversion in this path.

### Exit-code driven control flow
Use tool exit codes as primary signal:
- 10: pyramid is needed.
- 0: no pyramid needed / already present (check-only mode).
- 11: no output created in IfNeeded mode because no pyramid needed.
- 1 or 99: failure; trigger fallback policy.

### Fallback policy
Recommended for first rollout:
- If check/build fails, log structured error and continue with original CZI (do not block import).
- Keep optional emergency fallback flag to old conversion path during transition window.

---

## Deployment plan (Linux)

## 1) Package czi-pyramidizer in container image
Recommended installation approach: install the prebuilt release binary from the pinned GitHub release during the Docker image build.

Why this is the preferred installation path:
- It fits the current deployment model better than manual host installation.
- The binary becomes part of the application image, so every deployment uses the same tested version.
- It avoids compiling czi-pyramidizer inside this project pipeline.
- It gives a simple rollback path by changing one pinned version or disabling the feature flag.

Recommended source:
- Download the Linux release asset directly from the ZEISS GitHub release page for a pinned tag, for example v0.1.3.
- Use the Ubuntu 24.04 x64 package if the deployment image is Debian/Ubuntu based.
- Use the Alpine Linux x64 package only if the runtime image is Alpine based.
- Do not download "latest" dynamically at build time; always pin an explicit version.

Recommended Docker installation flow:
1. Add build arguments for the pinned version and asset name.
2. Download the zip archive from the release URL during docker build.
3. Download the corresponding SHA256SUMS file from the same release.
4. Verify the archive checksum before unpacking.
5. Unzip the archive in a temporary directory.
6. Copy the czi-pyramidizer executable to /usr/local/bin/czi-pyramidizer.
7. Copy LICENSE, THIRD_PARTY_LICENSES.txt, and README.release.md into an image directory such as /opt/czi-pyramidizer/ for traceability.
8. Mark the binary executable.
9. Run a smoke check in the build: czi-pyramidizer --version.

Why Docker is better than direct host installation:
- Host installation creates drift between servers.
- Docker keeps the binary version tied to the deployed application version.
- It is easier to audit because checksum verification lives in the Dockerfile/build logs.
- Rebuilding the image is enough to upgrade or roll back.

Direct host installation is possible but not recommended as the primary plan:
- It would mean downloading the zip on each server, unpacking it manually, placing the binary in PATH, and maintaining checksums outside the image build.
- That is harder to reproduce and easier to misconfigure.

Suggested Docker pattern:
- Keep the current Python base image.
- Install minimal extra packages needed for archive handling and download, for example curl and unzip.
- Use ARG values like CZI_PYRAMIDIZER_VERSION and CZI_PYRAMIDIZER_ASSET.
- Build the release URL explicitly from the pinned tag.

Example shape of the download URL:
- https://github.com/ZEISS/czi-pyramidizer/releases/download/v0.1.3/<release-asset-name>.zip

Notes for the final implementation phase:
- The exact asset filename must be copied from the release page and pinned in the Dockerfile.
- The release includes a package-local SHA256SUMS and also a top-level SHA256SUMS for the published archive assets; verify against the archive checksum before extraction.
- If the runtime image stays python:3.12-slim or another Debian/Ubuntu family image, the Ubuntu 24.04 x64 asset is the expected package to use.
- If the base image changes to Alpine in the future, switch to the Alpine Linux x64 asset instead of reusing the Ubuntu package.

Acceptance for packaging:
- Binary available in runtime PATH.
- Version printed during startup logs.
- Container build fails if binary missing.
- Container build fails if checksum verification fails.

## 2) Add config toggles for safe rollout
Introduce deployment flags (names proposal):
- CZI_PYRAMIDIZER_ENABLED=true|false
- CZI_PYRAMIDIZER_BIN=/usr/local/bin/czi-pyramidizer
- CZI_PYRAMIDIZER_TIMEOUT_SEC=...
- CZI_PYRAMIDIZER_THRESHOLD=4096
- CZI_PYRAMIDIZER_TILE_SIZE=1024
- CZI_PYRAMIDIZER_MAX_TOP_LEVEL=1024
- CZI_PYRAMIDIZER_MODE=IfNeeded
- CZI_PYRAMIDIZER_FALLBACK_TO_OLD_CONVERSION=false|true

Keep old conversion flags during migration, then deprecate.

## 3) Add a dedicated wrapper module
Create a small service/wrapper (future file suggestion):
- Runs subprocess safely (no shell=True).
- Captures stdout/stderr and exit code.
- Implements two operations:
  - check_needs_pyramid(path) -> bool + diagnostics
  - build_pyramid(src, dst) -> result object
- Handles timeout and clear error mapping.

## 4) Integrate wrapper in current import pipeline
In CZI path of format splitting/import preparation:
- Replace current conversion decision for targeted CZI with:
  - check-only call
  - conditional build call
  - return CZI path(s) only
- Preserve metadata extraction logic.
- Ensure fileData tracks the pyramidized output as the import source when generated.

## 5) Phase out CZI -> OME-TIFF for old/large CZI
Migration rule proposal:
- Phase 1: Keep conversion as emergency fallback only.
- Phase 2: Default fallback off in test deployment.
- Phase 3: Remove conversion branch for CZI, keep only non-CZI converters.

---

## Operational details

### File handling
- Write pyramidized output to temp path in same filesystem as source (fast move, less cross-device risk).
- Use deterministic suffix, e.g. <name>.pyramidized.czi.
- Clean temporary files after successful import and according to existing temp cleanup policy.

### Concurrency
- Large CZI pyramidization is CPU + IO heavy.
- Consider limiting concurrent pyramidization jobs (separate queue or semaphore) independent of general import thread count.

### Observability
Add structured log fields:
- czi_pyramid_check_exit_code
- czi_pyramid_build_exit_code
- czi_pyramid_duration_ms
- czi_source_bytes
- czi_pyramidizer_version
- fallback_path_used

Add counters/alerts:
- Number of CZI files checked
- Number requiring pyramid
- Number successfully pyramidized
- Number failed (check/build)
- Number using fallback path

---

## Test strategy

## Unit tests
- Wrapper command construction and argument validation.
- Exit-code mapping (0/10/11/1/99).
- Timeout behavior.
- Fallback behavior toggle.

## Integration tests (Linux CI or staging)
Use representative fixtures:
- Old CZI without pyramid -> check returns needed -> build created -> import succeeds.
- Modern CZI with pyramid -> check says not needed -> no build -> import succeeds.
- Corrupted/invalid CZI -> graceful failure path.
- Very large CZI -> verify timeout/logging/concurrency behavior.

## Non-functional tests
- Import throughput impact under concurrent uploads.
- Disk growth and temp-file cleanup validation.
- Crash recovery with partial pyramidized outputs.

---

## Rollout sequence
1. Add binary to deployment image and verify runtime availability.
2. Ship wrapper + config flags disabled by default.
3. Enable in test environment for a limited microscope/file cohort.
4. Validate logs, timings, and import success rates.
5. Disable CZI -> OME-TIFF fallback by default.
6. Remove old CZI conversion branch after stable period.

Rollback:
- Set CZI_PYRAMIDIZER_ENABLED=false and revert instantly to old behavior.

---

## Risks and mitigations
- Risk: Tool failures block imports.
  - Mitigation: non-blocking fallback policy in early phases.
- Risk: Runtime overhead on very large files.
  - Mitigation: queue limits, timeout, and metrics-based tuning.
- Risk: Extra disk consumption during processing.
  - Mitigation: bounded temp retention and cleanup hooks.
- Risk: Behavior changes for existing microscope scopes.
  - Mitigation: staged rollout by cohort and feature flags.

---

## Open decisions
- Do we pyramidize all CZI files or only old/large cohorts?
    - Only old files from the LSM700 and LSM710 should be without pyramid. So ALL.
- What timeout and concurrency limits are acceptable in production?
    - need some measurements. Let's make it flexible: in the config.py (living on kubernetes)
- Keep emergency CZI -> OME-TIFF fallback permanently or remove fully?
    - Roll out and delete in a future version
- Should destination overwrite in place or always write to new temp file then swap?
    - overwrite. Let's just log that the conversion happened

---

## Definition of done (implementation phase)
- Linux deployment image contains czi-pyramidizer and version is pinned.
- Import flow checks CZI pyramid presence and builds only when needed.
- CZI -> OME-TIFF conversion no longer used for old/large CZI by default.
- Feature flags, logs, metrics, and tests are in place.
- Staging validation completed on representative old CZI datasets.
