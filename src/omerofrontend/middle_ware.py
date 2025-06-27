import traceback
import datetime
import time
import functools
from typing import Optional, Callable, List
from threading import Lock
from concurrent.futures import Future, ThreadPoolExecutor
from werkzeug.datastructures import FileStorage

from omerofrontend import conf
from omerofrontend import logger
from omerofrontend.temp_file_handler import TempFileHandler
from omerofrontend.file_importer import FileImporter
from omerofrontend.file_data import FileData
from omerofrontend.server_event_manager import ServerEventManager
from omerofrontend.exceptions import ImageNotSupported, DuplicateFileExists, GeneralError, OmeroConnectionError, AssertImportError
from omerofrontend.omero_connection import OmeroConnection
from omerofrontend.database import DatabaseHandler

DoneCallback = Optional[Callable[[List[int]], None]]

class MiddleWare:
    """this class holds the connections between the api and the backend"""
    
    def __init__(self, database_handler: DatabaseHandler):
        self._temp_file_handler = TempFileHandler()
        self._file_importer = FileImporter()
        self._server_event_manager = ServerEventManager()
        self._executor = ThreadPoolExecutor(max_workers=conf.FILE_IMPORT_THREADS)
        self._future_filedata_context = {}
        self._future_filedata_mutex = Lock()
        self._db = database_handler
        self._done_cb = None

    def import_files(self, files: list[FileStorage], tags, connection: OmeroConnection, done_callback: DoneCallback = None):
    
        username: str = connection.get_logged_in_user_full_name()
        groupname: str = connection.getDefaultOmeroGroup()
        fileData = self._store_and_handle_temp_files(files, username)
        
        self._done_cb = done_callback
        
        future = self._executor.submit(self._handle_image_imports, fileData, tags, username, groupname, connection)
        self._safe_add_future_filedata_context(future, fileData)
        future.add_done_callback(self._future_complete_callback)
        logger.debug("Future added to executor")
        #return True
        
    def _safe_add_future_filedata_context(self, future: Future, fileData: FileData):
        with self._future_filedata_mutex:
            self._future_filedata_context[future] = fileData
        
        
    def _safe_get_future_filedata_context(self, future: Future) -> Optional[FileData]:
        with self._future_filedata_mutex:
            return self._future_filedata_context.get(future, None)
    
            
    def _future_complete_callback(self, future):
    
        if future.cancelled(): 
            logger.info("Import Image was cancelled.")
            #signal error to UI!
            return

        try:
            image_ids = future.result()
            logger.info("Image import completed successfull!")
            if self._done_cb is not None:
                logger.debug(f"Calling done callback with image_ids: {image_ids}")
                self._done_cb(image_ids)
        #catch all kinds of exceptions here!!!
        except FileNotFoundError as fnf:
            logger.error(f"FileNotFoundError during import of {fnf.filename}: {str(fnf)}, line: {traceback.format_exc()}")
            #ServerEventManager._send_error_event(filename,str(fnf))

        except ImageNotSupported as ins:
            logger.error(f"FileNotFoundError during import of {ins.filename}: {str(ins)}, line: {traceback.format_exc()}")

        except GeneralError as ge:
            logger.error(f"General during import of {ge.filename}: {str(ge)}, line: {traceback.format_exc()}")

        except DuplicateFileExists as dfe:
            logger.info(f"Duplicate {dfe.filename}: {str(dfe)}, line: {traceback.format_exc()}")
            ServerEventManager.send_duplicate_event(dfe.filename)

        except OmeroConnectionError as oce:
            logger.error(f"Connection error during import: {str(oce)}, line: {traceback.format_exc()}")
            #ServerEventManager._send_error_event(filename,str(oce))
            
        except ImportError as aie:
            logger.error(f"Import error during import: {str(aie)}, line: {traceback.format_exc()}")
            #ServerEventManager._send_error_event(filename,str(aie))

        except Exception as e:
            logger.error(f"Error during import: {str(e)}, line: {traceback.format_exc()}")

        finally:
            filedata = self._safe_get_future_filedata_context(future)
            if filedata is None:
                logger.error("No UUID found for future, cannot clean up file data context.")
                return
            #filedata = self._safe_get_future_filedata_context(id)
            logger.debug(f"Cleaning up file data context for file {filedata.getMainFileName()}") if filedata else None
            self._remove_temp_files(filedata) if filedata else None
    
    
    def _handle_image_imports(self, fileData: FileData, tags: dict, username: str, groupname: str, conn: OmeroConnection):
        import_time_start = time.time()
        self._server_event_manager.send_started_event(fileData.getMainFileName())
        scopes, image_ids = self._import_files_to_omero(fileData,tags,conn)
        import_time = time.time() - import_time_start
        self._register_in_database(scopes[0],username,groupname,import_time,fileData)
        return image_ids

    
    def _store_and_handle_temp_files(self, files: list[FileStorage], username: str) -> FileData:
        fileData = self._temp_file_handler.check_and_store_tempfiles(files, username)
        #self._safe_add_uuid_filedata_context(uid, fileData)
        return fileData
    
    def _import_files_to_omero(self, file: FileData, tags, conn: OmeroConnection):
        filename = file.getMainFileName()
        logger.info(f"Processing of {file.getTempFilePaths()}")
        prog_fun = functools.partial(ServerEventManager.send_progress_event,filename)
        rt_fun = functools.partial(ServerEventManager.send_retry_event,filename)
        return self._file_importer.import_image_data(file, tags, prog_fun, rt_fun, conn)
    
    def _remove_temp_files(self, file: FileData):
        self._temp_file_handler._remove_temp_files(file)
    
        
    def _register_in_database(self, scope, username, groupname, import_time, fileData):
        scope = None
        time_stamp = datetime.datetime.today().strftime(conf.DATE_TIME_FMT)

        groupname = str(groupname) if groupname else "Unknown Group"
        username = str(username) if username else "Unknown User"
        scope = str(scope) if scope is not None else "Unknown Scope"
        file_n = int(fileData.getNrOfFiles()) 
        total_file_size = float(fileData.getTotalFileSize())
        import_time = float(import_time)
        
        #show the data in the log
        logger.info('User information:')
        logger.info(f"    Time: {time_stamp}")
        logger.info(f"    Full Name: {username}")
        logger.info(f"    Current group: {groupname}")
        logger.info(f"    Main microscope: {scope}")
        logger.info(f"    File number: {file_n}")
        logger.info(f"    File total size (MB): {total_file_size /1024 / 1024}")
        logger.info(f"    Import time (s): {import_time}")
        logger.info("")
        
        # Insert data into the database
        self._db.insert_import_data(
            time=time_stamp,
            username=username,
            groupname=groupname,
            scope=scope,
            file_count=file_n,
            total_file_size_mb=total_file_size / 1024 / 1024,
            import_time_s=import_time
            )

    def get_ssevent(self, timeout=None):
        """
        Get the next server-sent event from the queue.
        """
        return self._server_event_manager.getEvent(timeout=timeout)
