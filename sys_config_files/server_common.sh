#!/bin/bash


exec > >(tee -i setup_server.log) 2>&1

# Set environment (default to "dev" if not specified)
ENVIRONMENT=${1:-dev}

# Print which environment is being used
echo "Using $ENVIRONMENT environment"

WWW_USER="www-user"

# Define source and destination directories
#SRC_DIR="sys_config_files"
WWW_ROOT_DIR="/var/www/html"
WWW_SYMLINK_NAME="Omero_GU"
SYSTEMD_DIR="/etc/systemd/system"
NGINX_AVAIL_DIR="/etc/nginx/sites-available"
NGINX_ENABLED_DIR="/etc/nginx/sites-enabled"
NGINX_SITE_FILE="nginx_omero_app"
NGINX_TEMPLATE="nginx_omero_app.template"
OMERO_SERVICE_TEMPLATE="omero_app_uwsgi.template"
OMERO_SERVICE_FILE="omero_app_uwsgi.service"

USER_HOME=$(eval echo ~${SUDO_USER})

CONDA_ROOT_PATH=$USER_HOME/miniconda3
# Define the environment name and path to the environment.yml file
CONDA_ENV_NAME="Omero_gu_app"



GEN_DIR="generated"

# Set environment-specific variables
if [ "$ENVIRONMENT" == "prod" ]; then
    ENV_FILE="nginx_prod.env"
else
    ENV_FILE="nginx_dev.env"
fi
