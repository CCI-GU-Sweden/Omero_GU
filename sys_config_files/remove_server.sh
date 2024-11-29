#!/bin/bash

source "server_common.sh"

#stopping omero service
echo "stopping $OMERO_SERVICE_FILE"
systemctl stop $(basename "$SRC_DIR/$OMERO_SERVICE_FILE")

# stopping nginx
echo "stopping nginx"
systemctl stop nginx

echo "removing generated files and directory"
rm -rf $GEN_DIR

echo "removing $SYSTEMD_DIR/$OMERO_SERVICE_FILE"
rm "$SYSTEMD_DIR/$OMERO_SERVICE_FILE"

echo "removing $NGINX_AVAIL_DIR/$NGINX_SITE_FILE"
rm "$NGINX_AVAIL_DIR/$NGINX_SITE_FILE"

echo "removing symlink $NGINX_ENABLED_DIR/$NGINX_SITE_FILE"
rm "removing symlink $NGINX_ENABLED_DIR/$NGINX_SITE_FILE"

# Reload systemd configuration
systemctl daemon-reload

if [ $? -ne 0 ]; then
    echo "One or more commands failed during script execution"
else
    echo "Nginx configuration for $ENVIRONMENT environment stopped and removed"
fi