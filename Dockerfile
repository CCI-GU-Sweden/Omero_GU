ARG BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim

FROM  ${BASE_IMAGE}

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    #OMERO_USER=omero \
    APP_HOME=/app/omero \
    USER_NAME=cci

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
    htop \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel

# Create a new user
RUN useradd -m -s /bin/bash ${USER_NAME}

# Set the working directory
WORKDIR ${APP_HOME}

#COPY . ${APP_HOME}
COPY src ${APP_HOME}
COPY static ${APP_HOME}
COPY templates ${APP_HOME}

COPY gunicorn.conf.py ${APP_HOME}
COPY logback.xml ${APP_HOME} 
COPY requirements.txt ${APP_HOME}
COPY uwsgi.ini ${APP_HOME}


RUN chmod 777 -R ${APP_HOME}

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

USER 1001
CMD ["uwsgi","--ini","uwsgi.ini"]

# Switch to the new user for all subsequent commands and runtime
USER ${USER_NAME}
# Set the working directory (optional)
