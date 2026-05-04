ARG BASE_IMAGE=public.ecr.aws/docker/library/ubuntu:24.04
ARG CZI_PYRAMIDIZER_VERSION=v0.1.3
ARG CZI_PYRAMIDIZER_ASSET=czi-pyramidizer-ubuntu-24.04-x64-v0.1.3.tar.gz
ARG CZI_PYRAMIDIZER_SHA256=00e59e266e071a826c6a23bee5fe4488f28082a9d9cd248a19027d31f8fc351d

FROM  ${BASE_IMAGE}

ARG CZI_PYRAMIDIZER_VERSION
ARG CZI_PYRAMIDIZER_ASSET
ARG CZI_PYRAMIDIZER_SHA256

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    #OMERO_USER=omero \
    APP_HOME=/app/omero \
    USER_NAME=cci

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python-is-python3 \
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
    libopencv-core406 \
    libopencv-imgproc406 \
    libopencv-imgcodecs406 \
    libopencv-videoio406 \
    default-jre-headless \
    htop \
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
    czi-pyramidizer --version; \
    rm -rf "/tmp/${CZI_PYRAMIDIZER_ASSET}" "${package_dir}"

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

RUN python -m pip install --no-cache-dir --break-system-packages -r requirements.txt

EXPOSE 5000

USER 1001
CMD ["uwsgi","--ini","uwsgi.ini"]

# Switch to the new user for all subsequent commands and runtime
USER ${USER_NAME}
# Set the working directory (optional)
