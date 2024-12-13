# Use an official Python image as the base
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    OMERO_USER=omero \
    OMERO_HOME=/app/omero

# Create a non-root user for OMERO
RUN useradd -m -d ${OMERO_HOME} -s /bin/bash ${OMERO_USER}

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

# Install omero-py and its dependencies
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install omero-py

# Set the working directory
WORKDIR ${OMERO_HOME}

COPY . ${OMERO_HOME}

RUN chmod 777 -R /app/omero

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

#ENV FLASK_APP=app
#ENV FLASK_APP=omero_frontend

#CMD ["python", "-m", "flask", "run", "--host=0.0.0.0"]
CMD ["uwsgi","--ini","uwsgi.ini"]