import git
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

GIT_HASH_FILE_NAME = "git_hash.txt"
BUILD = ""
hashfile = pathlib.Path("/path/to/file")
try:
    hash_abs_path = hashfile.resolve(strict=True)
except FileNotFoundError:
    # doesn't exist
    repo = git.Repo(search_parent_directories=True)
    sha = repo.head.object.hexsha
    BUILD = "local"
    
else:
    with open(hashfile, 'r') as file:
    # Read each line in the file
        sha = file.readline()

    BUILD = "server"
APP_VERSION = BUILD + "-" + sha
