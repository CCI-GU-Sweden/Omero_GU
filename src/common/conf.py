import pathlib
import logging
import os

ALLOWED_FOLDER_FILE_EXT = [".czi", ".tif", ".emi", ".ser", ".mrc", ".xml", ".emd"]
ALLOWED_SINGLE_FILE_EXT = [".czi", ".tif", ".emi", ".ser", ".mrc", ".xml"]

VENDOR_TAG_IDS = {34118, 34119}          # Zeiss SEM variants
VENDOR_TAG_NAMES = {"CZ_SEM", "FibicsXML"}

LOG_DIR = "logs/"
LOG_FILE = LOG_DIR + "omero_app.log"

IMPORT_PROGRESS_DIR = LOG_DIR + "progress/"

IMPORT_NR_OF_RETRIES = 5
IMPORT_PROGRESS_FILE_STEM = "import_progress"
IMPORT_LOG_FILE_STEM = "import_log"
IMPORT_LOG_FILE_EXTENSION = ".log"
IMPORT_LOGBACK_FILE = "logback.xml"


PG_DB_NAME = 'omerofilestats'

DB_USERNAME = "gu_cci_postgres"
DB_PASSWORD = "gu_cci_postgres"

SECRET_KEY = "s3cr3t"

APP_NAME = "gu_omero_frontend"
LOGGER_NAME = "omero_logger"
LOG_LEVEL = logging.DEBUG

FILE_IMPORT_THREADS = 8

GENERATE_THUMBNAILS = False

#configs for local running
USE_TEST_URL = True
DB_HOST = "localhost"
DB_PORT = 5432
DB_HANDLER = "postgres"

MAX_SIZE_FULL_UPLOAD = 1024 * 1024 * 30 # 30 MB in bytes
CHUNK_SIZE = 1024 * 1024 * 10 #1024 * 1024 is 1MB
USE_CHUNK_READ_ON_LARGE_FILES = True

REDIS_URL = "redis://:redis@redis-omero-test:6379/0"
RQ_QUEUE_NAME = "sse:omero_imports"
USE_FAKE_REDIS: bool = False

# CZI pyramid generation
CZI_PYRAMIDIZER_ENABLED: bool = False
CZI_PYRAMIDIZER_BIN: str = "czi-pyramidizer"
CZI_PYRAMIDIZER_TIMEOUT_SEC: int = 60 * 30
CZI_PYRAMIDIZER_THRESHOLD: int = 4096
CZI_PYRAMIDIZER_TILE_SIZE: int = 1024
CZI_PYRAMIDIZER_MAX_TOP_LEVEL: int = 1024
CZI_PYRAMIDIZER_MODE: str = "IfNeeded"

USER_VARIABLES = ["Sample", "User", "PI", "Preparation", "Lens ID"]
MICROSCOPE_ID_TO_NAME = {}
TRUSTED_PROXY_IPS = []
MICROSCOPE_IP_TO_NAME = {}

def _getenv_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


try:
    import config #pyright: ignore[reportAttributeAccessIssue]
    FILE_IMPORT_THREADS = getattr(config, "FILE_IMPORT_THREADS", FILE_IMPORT_THREADS)
    USE_TEST_URL = getattr(config, "USE_TEST_URL", USE_TEST_URL)
    DB_HOST = getattr(config, "DB_HOST", DB_HOST)
    DB_PORT = getattr(config, "DB_PORT", DB_PORT)
    DB_HANDLER = getattr(config, "DB_HANDLER", DB_HANDLER)
    LOG_LEVEL = getattr(config, "LOG_LEVEL", LOG_LEVEL)
    USE_CHUNK_READ_ON_LARGE_FILES = getattr(config, "USE_CHUNK_READ_ON_LARGE_FILES", USE_CHUNK_READ_ON_LARGE_FILES)
    REDIS_URL = getattr(config, "REDIS_URL", REDIS_URL)
    USE_FAKE_REDIS = getattr(config, "USE_FAKE_REDIS", USE_FAKE_REDIS)

    CZI_PYRAMIDIZER_ENABLED = getattr(config, "CZI_PYRAMIDIZER_ENABLED", CZI_PYRAMIDIZER_ENABLED)
    CZI_PYRAMIDIZER_BIN = getattr(config, "CZI_PYRAMIDIZER_BIN", CZI_PYRAMIDIZER_BIN)
    CZI_PYRAMIDIZER_TIMEOUT_SEC = getattr(config, "CZI_PYRAMIDIZER_TIMEOUT_SEC", CZI_PYRAMIDIZER_TIMEOUT_SEC)
    CZI_PYRAMIDIZER_THRESHOLD = getattr(config, "CZI_PYRAMIDIZER_THRESHOLD", CZI_PYRAMIDIZER_THRESHOLD)
    CZI_PYRAMIDIZER_TILE_SIZE = getattr(config, "CZI_PYRAMIDIZER_TILE_SIZE", CZI_PYRAMIDIZER_TILE_SIZE)
    CZI_PYRAMIDIZER_MAX_TOP_LEVEL = getattr(config, "CZI_PYRAMIDIZER_MAX_TOP_LEVEL", CZI_PYRAMIDIZER_MAX_TOP_LEVEL)
    CZI_PYRAMIDIZER_MODE = getattr(config, "CZI_PYRAMIDIZER_MODE", CZI_PYRAMIDIZER_MODE)

    GENERATE_THUMBNAILS = getattr(config, "GENERATE_THUMBNAILS", GENERATE_THUMBNAILS)
    USER_VARIABLES = getattr(config, "USER_VARIABLES", USER_VARIABLES)
    MICROSCOPE_ID_TO_NAME = getattr(config, "MICROSCOPE_ID_TO_NAME", MICROSCOPE_ID_TO_NAME)
    TRUSTED_PROXY_IPS = getattr(config, "TRUSTED_PROXY_IPS", TRUSTED_PROXY_IPS)
    MICROSCOPE_IP_TO_NAME = getattr(config, "MICROSCOPE_IP_TO_NAME", MICROSCOPE_IP_TO_NAME)

except ImportError:
    pass

# Environment variables can override file-based config, useful for Docker runs
# where local config.py is not mounted into /app/omero.
REDIS_URL = os.getenv("REDIS_URL", REDIS_URL)
USE_FAKE_REDIS = _getenv_bool("USE_FAKE_REDIS", USE_FAKE_REDIS)

#if DB_HANDLER == "sqlite":
SQL_DB_DIR = "database"
SQL_DB_NAME = 'omero_imports.db'

if USE_TEST_URL:
    OMERO_HOST = 'omero-cli.test.gu.se'
    OMERO_BASE_URL = 'https://omero-web-test.apps.k8s.gu.se'
else: #production mode
    OMERO_HOST = 'omero-cci-cli.gu.se'
    OMERO_BASE_URL = 'https://omero-cci-users.gu.se'

OMERO_PORT = '4064'

OMERO_LOGIN_URL = f'{OMERO_BASE_URL}/oauth/?url=%2Fwebclient%2F'
OMERO_SESSION_TOKEN_URL = f'{OMERO_BASE_URL}/oauth/sessiontoken'


UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'

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