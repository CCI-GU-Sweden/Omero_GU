#!/bin/bash

# Check if the script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script as root using sudo"
    exit 1
fi

exec > >(tee -i setup_server.log) 2>&1

# Set environment (default to "dev" if not specified)
ENVIRONMENT=${1:-dev}

# Print which environment is being used
echo "Using $ENVIRONMENT environment"

WWW_USER="www-user"

# Define source and destination directories
#SRC_DIR="sys_config_files"
SYSTEMD_DIR="/etc/systemd/system"
NGINX_AVAIL_DIR="/etc/nginx/sites-available"
NGINX_ENABLED_DIR="/etc/nginx/sites-enabled"
NGINX_SITE_FILE="nginx_omero_app"
NGINX_TEMPLATE="nginx_omero_app.template"
OMERO_SERVICE_FILE="omero_app_uwsgi.service"

GEN_DIR="generated"

# Set environment-specific variables
if [ "$ENVIRONMENT" == "prod" ]; then
    NGINX_TEMPL="$NGINX_TEMPLATE"
    ENV_FILE="nginx_prod.env"
else
    NGINX_TEMPL="$NGINX_TEMPLATE"
    ENV_FILE="nginx_dev.env"
fi
