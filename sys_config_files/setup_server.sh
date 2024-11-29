#!/bin/bash

source "server_common.sh"

if id "$WWW_USER" >/dev/null 2>&1; then
    echo "User $WWW_USER exists"
else
    echo "User $WWW_USER does not exist. Create the user and run this script again"
    exit 1
fi

# Check if the environment already exists

sudo -i -u "$WWW_USER" bash << EOS

CONDA_ROOT_PATH="\$HOME/miniconda3"

# Define the environment name and path to the environment.yml file
ENV_NAME="Omero_gu_app"
ENV_YML_PATH="environment.yml"


# Check if Miniconda exists
if [ ! -d "\$CONDA_ROOT_PATH" ]; then
    echo "Miniconda3 is not installed in \$CONDA_ROOT_PATH. Please install Miniconda3 and try again."
    exit 1
fi

# Source conda
source \$CONDA_ROOT_PATH/etc/profile.d/conda.sh


if ! conda env list | grep -q "$ENV_NAME"; then
    echo "Environment $ENV_NAME does not exist. Creating it from $ENV_YML_PATH..."
    conda env create -f "$ENV_YML_PATH"
fi

EOS

# Check the exit status of the sudo command
if [ $? -ne 0 ]; then
    echo "An error occurred in the sudo command."
    exit 1
fi

#NGINX_CONFIG="$SRC_DIR/nginx_config_$ENVIRONMENT"
GEN_DIR="generated"
mkdir -p $GEN_DIR

# Source the environment variables
source "$ENV_FILE"

# Process the Nginx config template
envsubst < "$NGINX_TEMPL" > "$GEN_DIR/$NGINX_SITE_FILE"

# Copy the first file to systemd directory
cp "$OMERO_SERVICE_FILE" "$SYSTEMD_DIR/"

# Copy the second file to Nginx sites-available
cp "$GEN_DIR/$NGINX_SITE_FILE" "$NGINX_AVAIL_DIR/"

# Create symlink in sites-enabled
ln -sf "$NGINX_AVAIL_DIR/$NGINX_SITE_FILE" "$NGINX_ENABLED_DIR/"

#set correct owner on dir
#chown -R $WWW_USER:www-data .

# Reload systemd configuration
systemctl daemon-reload

# Start the new service (assuming file1 is the service file)
systemctl start $(basename "$SRC_DIR/$OMERO_SERVICE_FILE")

# Restart Nginx
systemctl restart nginx


if [ $? -ne 0 ]; then
    echo "One or more commands failed during script execution"
else
    echo "Nginx configuration for $ENVIRONMENT environment processed, copied, and applied successfully"
fi