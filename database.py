#database import
import sqlite3
import logging
import config


logger = logging.getLogger(config.APP_NAME)

#SQL functions
def initialize_database(db_name='omero_imports.db'):
    conn = sqlite3.connect(db_name)
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

def insert_import_data(time, username, groupname, scope, file_count, total_file_size_mb, import_time_s, db_name='omero_imports.db'):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO imports (time, username, groupname, scope, file_count, total_file_size_mb, import_time_s)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (time, username, groupname, scope, file_count, total_file_size_mb, import_time_s))
    conn.commit()
    conn.close()
    
def get_all_imports(db_name='omero_imports.db'):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM imports')
    rows = cursor.fetchall()
    conn.close()
    return rows
