ARG BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim
ARG CZI_PYRAMIDIZER_VERSION=v0.1.3
ARG CZI_PYRAMIDIZER_ASSET=czi-pyramidizer-ubuntu-24.04-x64-v0.1.3.tar.gz
ARG CZI_PYRAMIDIZER_SHA256=00e59e266e071a826c6a23bee5fe4488f28082a9d9cd248a19027d31f8fc351d

FROM public.ecr.aws/docker/library/ubuntu:24.04 AS pyramidizer-fetch

ARG CZI_PYRAMIDIZER_VERSION
ARG CZI_PYRAMIDIZER_ASSET
ARG CZI_PYRAMIDIZER_SHA256

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    archive_url="https://github.com/ZEISS/czi-pyramidizer/releases/download/${CZI_PYRAMIDIZER_VERSION}/${CZI_PYRAMIDIZER_ASSET}"; \
    curl -fsSL -o "/tmp/${CZI_PYRAMIDIZER_ASSET}" "${archive_url}"; \
    echo "${CZI_PYRAMIDIZER_SHA256}  /tmp/${CZI_PYRAMIDIZER_ASSET}" | sha256sum -c -; \
    tar -xzf "/tmp/${CZI_PYRAMIDIZER_ASSET}" -C /tmp; \
    package_dir="/tmp/${CZI_PYRAMIDIZER_ASSET%.tar.gz}"; \
    install -m 0755 "${package_dir}/czi-pyramidizer" /usr/local/bin/czi-pyramidizer; \
    mkdir -p /opt/czi-pyramidizer; \
    cp "${package_dir}/LICENSE" /opt/czi-pyramidizer/; \
    cp "${package_dir}/THIRD_PARTY_LICENSES.txt" /opt/czi-pyramidizer/; \
    cp "${package_dir}/README.release.md" /opt/czi-pyramidizer/; \
    rm -rf "/tmp/${CZI_PYRAMIDIZER_ASSET}" "${package_dir}"

FROM ${BASE_IMAGE}

ARG CZI_PYRAMIDIZER_VERSION
ARG CZI_PYRAMIDIZER_ASSET
ARG CZI_PYRAMIDIZER_SHA256

# Install dependencies
RUN set -eux; \
    apt-get update; \
    apt-get install -y \
        build-essential \
        libssl-dev \
        libjpeg-dev \
        zlib1g-dev \
        libtiff-dev \
        libxml2-dev \
        libxslt-dev \
        libfreetype6-dev \
        liblcms2-dev \
        libwebp-dev \
        gettext \
        curl \
        libbz2-dev \
        libstdc++6 \
        libgcc-s1 \
        default-jdk-headless \
        htop; \
    if ! apt-get install -y \
        libopencv-core406 \
        libopencv-imgproc406 \
        libopencv-imgcodecs406 \
        libopencv-videoio406; then \
        if ! apt-get install -y \
            libopencv-core406t64 \
            libopencv-imgproc406t64 \
            libopencv-imgcodecs406t64 \
            libopencv-videoio406t64; then \
            apt-get install -y libopencv-dev; \
        fi; \
    fi; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    ldconfig; \
    for lib in core imgproc imgcodecs videoio; do \
        src="$(find /usr/lib -name "libopencv_${lib}.so.*" ! -name "*.so.406" | sort | head -n 1 || true)"; \
        if [ -n "$src" ]; then \
            target_dir="$(dirname "$src")"; \
            ln -sf "$src" "${target_dir}/libopencv_${lib}.so.406"; \
        fi; \
    done; \
    ldconfig

COPY --from=pyramidizer-fetch /usr/local/bin/czi-pyramidizer /usr/local/bin/czi-pyramidizer
COPY --from=pyramidizer-fetch /opt/czi-pyramidizer /opt/czi-pyramidizer

ENV PYTHONUNBUFFERED=1 \
    APP_HOME=/app/omero \
    USER_NAME=cci \
    XDG_CACHE_HOME=/.cache \
    JGO_CACHE_DIR=/.cache/jgo \
    SCYJAVA_CACHE_DIR=/.cache/scyjava \
    CJDK_CACHE_DIR=/.cache/cjdk \
    BIOFORMATS_MEMO_DIR=/.cache/bioformats-memo \
    JAVA_HOME=/usr/lib/jvm/default-java \
    PATH="/usr/lib/jvm/default-java/bin:${PATH}" \
    JAVA_TOOL_OPTIONS="-Xmx2g"

RUN mkdir -p \
        ${APP_HOME} \
        ${XDG_CACHE_HOME} \
        ${JGO_CACHE_DIR} \
        ${SCYJAVA_CACHE_DIR} \
        ${CJDK_CACHE_DIR} \
        ${BIOFORMATS_MEMO_DIR} \
    && chgrp -R 0 ${APP_HOME} ${XDG_CACHE_HOME} \
    && chmod -R g=u ${APP_HOME} ${XDG_CACHE_HOME}

RUN python -m pip install --upgrade pip setuptools wheel

# Create a new user
RUN useradd -m -s /bin/bash ${USER_NAME}

# Set the working directory
WORKDIR ${APP_HOME}

#COPY . ${APP_HOME}
COPY src ${APP_HOME}/src
COPY static ${APP_HOME}/static
COPY templates ${APP_HOME}/templates
COPY logback.xml ${APP_HOME} 
COPY requirements.txt ${APP_HOME}
COPY uwsgi.ini ${APP_HOME}

RUN chmod 777 -R ${APP_HOME}

RUN pip install --no-cache-dir -r requirements.txt

RUN ldd /usr/local/bin/czi-pyramidizer | grep -E "opencv|not found" || true

RUN czi-pyramidizer --version

COPY tests/data/test_image.czi /tmp/test_image.czi

RUN chown -R ${USER_NAME}:0 /app/omero /.cache /tmp/test_image.czi \
    && chmod -R g=u /app/omero \
    && chmod -R g=u /.cache \
    && chmod 644 /tmp/test_image.czi

USER ${USER_NAME}

# Test bioio and bioio-bioformats while building the image.
RUN python - <<'PY'
import os
from bioio import BioImage
import bioio_bioformats

print("XDG_CACHE_HOME =", os.environ.get("XDG_CACHE_HOME"))
print("JGO_CACHE_DIR =", os.environ.get("JGO_CACHE_DIR"))
print("SCYJAVA_CACHE_DIR =", os.environ.get("SCYJAVA_CACHE_DIR"))
print("CJDK_CACHE_DIR =", os.environ.get("CJDK_CACHE_DIR"))
print("BIOFORMATS_MEMO_DIR =", os.environ.get("BIOFORMATS_MEMO_DIR"))

img = BioImage("/tmp/test_image.czi", reader=bioio_bioformats.Reader)
print("Scenes:", img.scenes)
print("Dims:", img.dims)
print("Shape:", img.shape)

arr = img.get_image_data("YX", T=0, Z=0, C=0)
print("Read slice:", arr.shape, arr.dtype)
PY

# Switch back to root to fix permissions after the cache was created.
USER root

# Ensure pre-warmed cache files remain writable for runtime.
RUN chgrp -R 0 /.cache /app/omero \
    && chmod -R g=u /.cache /app/omero

# Final runtime user.
USER ${USER_NAME}

EXPOSE 5000

CMD ["uwsgi","--ini","uwsgi.ini"]
