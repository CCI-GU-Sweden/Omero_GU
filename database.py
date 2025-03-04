import psycopg
import sqlite3
import os
import logger
import conf
from threading import Lock
_db_mutex = Lock()


class DatabaseHandler:
    
    def initialize_database(self):
        pass
        
    def insert_import_data(self, time, username, groupname, scope, file_count, total_file_size_mb, import_time_s):
        pass
        
    def get_all_imports(self):
        pass
    
class SqliteDatabaseHandler(DatabaseHandler):

    def __init__(self):
        super().__init__()
        self._db_mutex = Lock()
        self.DB_FILE = f"{conf.DB_DIR}/{conf.DB_NAME}"

    def initialize_database(self):
        with self._db_mutex:
            os.makedirs(conf.DB_DIR, exist_ok=True)
            conn = sqlite3.connect(self.DB_FILE)
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
            conn.commit()
            conn.close()

        
    def insert_import_data(self, time, username, groupname, scope, file_count, total_file_size_mb, import_time_s):
        with _db_mutex:
            conn = sqlite3.connect(self.DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO imports (time, username, groupname, scope, file_count, total_file_size_mb, import_time_s)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (time, username, groupname, scope, file_count, total_file_size_mb, import_time_s))
            conn.commit()
            conn.close()
        
    def get_all_imports(self):
        with _db_mutex:
            conn = sqlite3.connect(self.DB_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM imports')
            rows = cursor.fetchall()
            conn.close()
            return rows



class PostgresDatabaseHandler(DatabaseHandler):

    #SQL functions
    def initialize_database(self):
        try:
            with _db_mutex, psycopg.connect(dbname=conf.DB_NAME,user=conf.DB_USERNAME, password=conf.DB_USERNAME, host=conf.DB_HOST, port=conf.DB_PORT) as conn:
                with conn.cursor() as cursor:
                    logger.info("Creating database if it does not already exist")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS imports (
                            id SERIAL PRIMARY KEY,
                            time TIMESTAMP NOT NULL,
                            username TEXT NOT NULL,
                            groupname TEXT NOT NULL,
                            scope TEXT NOT NULL,
                            file_count INTEGER NOT NULL,
                            total_file_size_mb REAL NOT NULL,
                            import_time_s REAL NOT NULL
                        )
                    ''')
        except psycopg.Error as e:
            logger.error(f"Database error: {e}")
            raise

    def insert_import_data(self,time, username, groupname, scope, file_count, total_file_size_mb, import_time_s):
        try:
            with _db_mutex, psycopg.connect(dbname=conf.DB_NAME,user=conf.DB_USERNAME, password=conf.DB_USERNAME, host=conf.DB_HOST, port=conf.DB_PORT) as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        INSERT INTO imports (time, username, groupname, scope, file_count, total_file_size_mb, import_time_s)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (time, username, groupname, scope, file_count, total_file_size_mb, import_time_s))
        
        except psycopg.Error as e:
            logger.error(f"Database error: {e}")
            raise
        
    def get_all_imports(self):
        try:
            with _db_mutex, psycopg.connect(dbname=conf.DB_NAME,user=conf.DB_USERNAME, password=conf.DB_USERNAME, host=conf.DB_HOST, port=conf.DB_PORT) as conn:
                with conn.cursor() as cursor: 
                    cursor.execute('SELECT * FROM imports')
                    rows = cursor.fetchall()
                    return rows
        except psycopg.Error as e:
            logger.error(f"Database error: {e}")
            raise
        