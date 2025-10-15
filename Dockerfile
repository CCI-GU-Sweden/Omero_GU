ARG BASE_IMAGE=registry.k8s.gu.se/openshift/python:3.12-slim

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

# Set the working directory
WORKDIR ${APP_HOME}

COPY . ${APP_HOME}

RUN chmod 777 -R ${APP_HOME}

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

USER 1001
CMD ["uwsgi","--ini","uwsgi.ini"]