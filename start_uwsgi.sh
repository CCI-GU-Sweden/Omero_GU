#!/bin/bash

#path to conda installation
CONDA_ROOT_PATH=$HOME/miniconda3

# Define the environment name and path to the environment.yml file
ENV_NAME="Omero_gu_app"
#ENV_YML_PATH="environment.yml"

# Check if Miniconda exists
if [ ! -d "$CONDA_ROOT_PATH" ]; then
    echo "Miniconda3 is not installed in $CONDA_ROOT_PATH. Please install Miniconda3 and try again."
    exit 1
fi

# Source conda
source $CONDA_ROOT_PATH/etc/profile.d/conda.sh


# Activate the environment
conda activate "$ENV_NAME"

# Start uWSGI
uwsgi --ini uwsgi.ini
