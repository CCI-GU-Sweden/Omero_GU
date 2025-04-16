import pathlib

ALLOWED_FOLDER_FILE_EXT = [".czi", ".emd", ".tif", ".emi", ".ser", ".mrc", ".xml"]
ALLOWED_SINGLE_FILE_EXT = [".czi", ".tif", ".emi", ".ser", ".mrc", ".xml"]


LOG_DIR = "logs/"
LOG_FILE = LOG_DIR + "omero_app.log"

IMPORT_NR_OF_RETRIES = 3
IMPORT_PROGRESS_FILE = "import_progress.log"

DB_NAME = 'omerofilestats'

DB_USERNAME = "gu_cci_postgres"
DB_PASSWORD = "gu_cci_postgres"

SECRET_KEY = "s3cr3t"

APP_NAME = "gu_omero_frontend"
LOGGER_NAME = "omero_logger"

FILE_IMPORT_THREADS = 2

USE_TEST_URL = False
DB_HOST = "localhost"
DB_PORT = 5432
DB_HANDLER = "postgres"

try:
    import config
    USE_TEST_URL = config.USE_TEST_URL if hasattr(config,"USE_TEST_URL") else USE_TEST_URL
    DB_HOST = config.DB_HOST if hasattr(config,"DB_HOST") else DB_HOST
    DB_PORT = config.DB_PORT if hasattr(config,"DB_PORT") else DB_PORT
    DB_HANDLER = config.DB_HANDLER if hasattr(config,"DB_HANDLER") else DB_HANDLER
except ImportError:
    pass    
    
if DB_HANDLER == "sqlite":
    DB_DIR = "database"
    DB_NAME = 'omero_imports.db'

    
if USE_TEST_URL:
    OMERO_HOST = 'omero-cli.test.gu.se'
    OMERO_BASE_URL = 'https://omero-web-test.apps.k8s.gu.se'

else: #production mode
    OMERO_HOST = 'omero-cci-cli.gu.se'
    OMERO_BASE_URL = 'https://omero-cci-users.gu.se'

OMERO_PORT = '4064'

OMERO_LOGIN_URL = f'{OMERO_BASE_URL}/oauth/?url=%2Fwebclient%2F'
OMERO_SESSION_TOKEN_URL = f'{OMERO_BASE_URL}/oauth/sessiontoken'

USE_CHUNK_READ_ON_LARGE_FILES = True
MAX_SIZE_FULL_UPLOAD = 1024 * 1024 * 30 # 30 MB in bytes
CHUNK_SIZE = 1024 * 1024 * 10 #1024 * 1024 is 1MB

UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'

USER_VARIABLES = ["Sample", "User", "PI", "Preparation"]

DATE_TIME_FMT = "%Y-%m-%d %H:%M:%S"

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

OMERO_SESSION_TOKEN_KEY = "omero_token"
OMERO_SESSION_HOST_KEY  = "omero_host"
OMERO_SESSION_PORT_KEY  = "omero_port"
OMERO_G_CONNECTION_KEY  = "connection"
OMERO_G_IMPORTER_KEY    = "importer"