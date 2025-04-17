# Omero_GU
 
Omero script for the University of Gothenburg, Centre for Cellular Imaging (CCI).

You can run this from your oridinary python debugger. 
The bette way to really test it is to run the docker image. Here is how:

1. install Podman
2. In to root directory of the repo run: podman build --build-arg BASE_IMAGE=docker.io/python:3.9-slim -f Dockerfile .
3. get the image ID of te built image by, for example, running podman images
4. start the server by running the command: podman run --user root -p 5000:5000 -v ./:/app/omero IMAGE_ID (image id is something like 7fc781648bb4). The -v args maps your current directory to the /app/omero path in the image. Very convenient if you want to develop and change the code without rebuilding the image.
5. Open a browser and go to localhost:5000 to enjoy the page
