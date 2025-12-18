# Omero_GU
 
Omero script for the University of Gothenburg, Centre for Cellular Imaging (CCI).

You can run this from your oridinary python debugger. 
The bette way to really test it is to run the docker image. Here is how:

1. install Podman
2. In to root directory of the repo run: podman build --build-arg BASE_IMAGE=docker.io/python:3.9-slim -f Dockerfile .
3. get the image ID of te built image by, for example, running podman images
4. start the server by running the command: podman run --user root -p 5000:5000 -v ./:/app/omero IMAGE_ID (image id is something like 7fc781648bb4). The -v args maps your current directory to the /app/omero path in the image. Very convenient if you want to develop and change the code without rebuilding the image.
5. Open a browser and go to localhost:5000 to enjoy the page


## Running tests, lint and typechecking

### linting (Ruff)
Make sure ruff is installed and run

ruff check --target-version=py39 src/omerofrontend/*.py

to check all files in the omerofrontend module

### typechecking (pyright)
Make sure pyright is installed and run

pyright src/omerofrontend/*.py 

to check all files in the omerofrontend module

### running the tests (pytest)

There are two types of tests implemented. Manual and automatic.
The manual tests need to be given a connection token for the omeroconnection to pass.

In order to run the automatic tests make sure pytest is installed and run

pytest tests "-m not manual"


To run the manual tests you run
pytest tests "-m manual"


### Deploying on Open shift

The image is built automatically on core-omero-test namespace whenever the main branch is updated in git.
When the image is in the expected and wanted state you tag it in core-omero-prod using oc:

use oc to login and change to the core-omero-prod project
run oc tag core-omero-test/omero-frontend-test:latest omero-frontend-prod:name_of_tag (usually v1.x or similar)

Update the yaml for flask-app. Look for the section
containers:
        - name: flask-app
          image: 'image-registry.openshift-image-registry.svc:5000/core-omero-prod/omero-frontend-prod:v1.5'
 and update the version number in the end to the one you tagged.