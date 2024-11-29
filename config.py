

LOG_DIR = "logs/"
LOG_FILE = "omero_app.log"

SECRET_KEY = "s3cr3t"

OMERO_BASE_URL = 'https://omero-web-test.apps.k8s.gu.se'
OMERO_LOGIN_URL = f'{OMERO_BASE_URL}/oauth/?url=%2Fwebclient%2F'
OMERO_SESSION_TOKEN_URL = f'{OMERO_BASE_URL}/oauth/sessiontoken'

MAX_SIZE_FULL_UPLOAD = 1024 * 1024 * 30 # 30 MB in bytes
CHUNK_SIZE = 1024 * 1024 * 10 #1024 * 1024 is 1MB

UPLOAD_FOLDER = 'uploads'

DB_NAME = 'omero_imports.db'