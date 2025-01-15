import pathlib

ALLOWED_FILE_EXT = [".czi"]

LOG_DIR = "logs/"
LOG_FILE = "omero_app.log"

DB_DIR = "database"
DB_NAME = 'omero_imports.db'

SECRET_KEY = "s3cr3t"

APP_NAME = "gu_omero_frontend"
LOGGER_NAME = "omero_logger"

OMERO_HOST = '130.241.39.241'
OMERO_PORT = '4064'

USE_TEST_URL = True
OMERO_TEST_BASE_URL = 'https://omero-web-test.apps.k8s.gu.se'
OMERO_BASE_URL = 'https://omero-web-test.apps.k8s.gu.se'

if USE_TEST_URL:
    OMERO_BASE_URL = OMERO_TEST_BASE_URL

OMERO_LOGIN_URL = f'{OMERO_BASE_URL}/oauth/?url=%2Fwebclient%2F'
OMERO_SESSION_TOKEN_URL = f'{OMERO_BASE_URL}/oauth/sessiontoken'


MAX_SIZE_FULL_UPLOAD = 1024 * 1024 * 30 # 30 MB in bytes
CHUNK_SIZE = 1024 * 1024 * 10 #1024 * 1024 is 1MB

UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'

#create the version_file.txt file from the build pipeline!
GIT_HASH_FILE_NAME = "version_file.txt"
SHA = "0000"
hashfile = pathlib.Path(GIT_HASH_FILE_NAME)
try:
    hash_abs_path = hashfile.resolve(strict=True)
    with open(hashfile, 'r') as file:
    # Read each line in the file
        SHA = file.readline()
    BUILD="server"
except FileNotFoundError:
    # doesn't exist
    BUILD = "local"

APP_VERSION = BUILD + "-" + SHA
