import psycopg
import logger
import conf
from threading import Lock

_db_mutex = Lock()


#SQL functions
def initialize_database():
    with _db_mutex, psycopg.connect(database=conf.conf.DB_NAME,user=conf.DB_USERNAME, password=conf.DB_USERNAME, host=conf.DB_HOST, port=conf.DB_PORT) as conn:
        cursor = conn.cursor()
        logger.info("Creating database if it does not already exist")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT NOT NULL,
                username TEXT NOT NULL,
                groupname TEXT NOT NULL,
                scope TEXT NOT NULL,
                file_count INTEGER NOT NULL,
                total_file_size_mb REAL NOT NULL,
                import_time_s REAL NOT NULL
            )
        ''')

def insert_import_data(time, username, groupname, scope, file_count, total_file_size_mb, import_time_s):
    with _db_mutex, psycopg.connect(database=conf.conf.DB_NAME,user=conf.DB_USERNAME, password=conf.DB_USERNAME, host=conf.DB_HOST, port=conf.DB_PORT) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO imports (time, username, groupname, scope, file_count, total_file_size_mb, import_time_s)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (time, username, groupname, scope, file_count, total_file_size_mb, import_time_s))
    
def get_all_imports():
    with _db_mutex, psycopg.connect(database=conf.DB_NAME,user=conf.DB_USERNAME, password=conf.DB_USERNAME, host=conf.DB_HOST, port=conf.DB_PORT) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM imports')
        rows = cursor.fetchall()
        return rows
