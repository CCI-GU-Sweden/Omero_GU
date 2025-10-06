ARG BASE_IMAGE=registry.k8s.gu.se/openshift/python:3.9-slim

FROM  ${BASE_IMAGE}

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    #OMERO_USER=omero \
    APP_HOME=/app/omero

# Install dependencies
RUN apt-get update && apt-get install -y \
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
    default-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel

# Install ZeroC Ice from prebuilt wheel (Glencoe Software provides this)
RUN python3.9 -m pip install \
    https://github.com/glencoesoftware/zeroc-ice-py-rhel9-x86_64/releases/download/20230830/zeroc_ice-3.6.5-cp39-cp39-linux_x86_64.whl


# Set the working directory
WORKDIR ${APP_HOME}

COPY . ${APP_HOME}

RUN chmod 777 -R ${APP_HOME}

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

USER 1001
CMD ["uwsgi","--ini","uwsgi.ini"]