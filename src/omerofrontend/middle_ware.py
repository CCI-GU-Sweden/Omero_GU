import traceback
import datetime
import time
import functools
from typing import Optional, Callable, List
from threading import Lock
from concurrent.futures import Future, ThreadPoolExecutor
from werkzeug.datastructures import FileStorage

from common import conf
from common import logger
from omerofrontend.temp_file_handler import TempFileHandler
from omerofrontend.file_importer import FileImporter
from common.file_data import FileData
from omerofrontend.server_event_manager import ServerEventManager
from omerofrontend.exceptions import ImageNotSupported, DuplicateFileExists, GeneralError, OmeroConnectionError, OutOfDiskError
from common.omero_connection import OmeroConnection
from omerofrontend import database

DoneCallback = Optional[Callable[[List[int],bool], None]]

class MiddleWare:
    """this class holds the connections between the api and the backend"""
    
    def __init__(self, database_handler: database.DatabaseHandler):
        self._temp_file_handler = TempFileHandler()
        self._file_importer = FileImporter()
        self._executor = ThreadPoolExecutor(max_workers=conf.FILE_IMPORT_THREADS)
        self._future_filedata_context = {}
        self._store_tmp_file_mutex = Lock()
        self._future_filedata_mutex = Lock()
        self._db = database_handler
        self._done_cb = None

    def import_files(self, files: list[FileStorage], tags, username: str, groupname: str, token: Optional[str], done_callback: DoneCallback = None) -> tuple[bool, str]:
    #def import_files(self, files: list[FileStorage], tags, token: str, done_callback: DoneCallback = None) -> tuple[bool, str]:
    
        if not token:
            logger.error("No valid session token provided for import.")
            return (False, "No valid session token provided for import.")

        conn: OmeroConnection = OmeroConnection(hostname=conf.OMERO_HOST, port=conf.OMERO_PORT, token=token)
        
        #TODO: error handling in this function
        with self._store_tmp_file_mutex:
            try:
                for f in files:
                    ServerEventManager.send_staging_event(f.filename)
                logger.debug("in import files...")
                logger.debug("storing tempfile...")
                fileData = self._store_and_handle_temp_files(files, username)
                logger.debug("done")
            except OutOfDiskError as ode:
                logger.error(f"Out of disk error while storing temp file {files[0].filename}: {str(ode)}")
                self._temp_file_handler.remove_temp_file_by_path(ode.filepath)
                ServerEventManager.send_error_event(files[0].filename,"Out of disk error while storing temp file")
                
                return (False, "Out of disk error while storing temp file")
            
        self._done_cb = done_callback
        future = self._executor.submit(self._handle_image_imports, fileData, tags, username, groupname, conn)
        self._safe_add_future_filedata_context(future, fileData)
        future.add_done_callback(self._future_complete_callback)
        logger.debug("Future added to executor")
        return (True, "")
        
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

        image_ids = []
        result = False
        duplicate = False
        filedata = self._safe_get_future_filedata_context(future)
        err_msg = ""
        try:
            if filedata is None:
                logger.error("No filedata found for future, cannot clean up file data context.")
                raise GeneralError(message="No filedata found")
            image_ids, omero_path = future.result()
            result = True
            logger.info(f"*** Image import of {filedata.getMainFileName()} completed successfully! ***")
            logger.info(f"*** Stored at {omero_path} with id {image_ids[0]}                        ***")
            ServerEventManager.send_success_event(filedata.getMainFileName(), omero_path, image_ids[0])
        #catch all kinds of exceptions here!!!
        except FileNotFoundError as fnf:
            err_msg = str(fnf)
            logger.error(f"FileNotFoundError during import of {fnf.filename}: {err_msg}, line: {traceback.format_exc()}")

        except ImageNotSupported as ins:
            err_msg = str(ins)
            logger.error(f"FileNotFoundError during import of {ins.filename}: {str(ins)}, line: {traceback.format_exc()}")

        except GeneralError as ge:
            err_msg = str(ge)
            logger.error(f"General during import of {ge.filename}: {str(ge)}, line: {traceback.format_exc()}")

        except DuplicateFileExists as dfe:
            logger.info(f"Duplicate {dfe.filename}: {str(dfe)}")
            ServerEventManager.send_duplicate_event(dfe.filename)
            duplicate = True

        except OmeroConnectionError as oce:
            err_msg = str(oce)
            logger.error(f"Connection error during import: {str(oce)}, line: {traceback.format_exc()}")
            
        except ImportError as aie:
            err_msg = str(aie)
            logger.error(f"Import error during import: {str(aie)}, line: {traceback.format_exc()}")

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Error during import: {str(e)}, line: {traceback.format_exc()}")

        finally:
            if self._done_cb is not None:
                logger.debug(f"Calling done callback with image_ids: {image_ids}")
                self._done_cb(image_ids, result)

            if not result and not duplicate:
                filename = filedata.getMainFileName() if filedata else None
                ServerEventManager.send_error_event(filename, err_msg)

            logger.debug(f"Cleaning up file data context for file {filedata.getMainFileName()}") if filedata else None
            self._remove_temp_files(filedata) if filedata else None
    
    
    def _handle_image_imports(self, fileData: FileData, tags: dict, username: str, groupname: str, conn: OmeroConnection):
        import_time_start = time.time()
        ServerEventManager.send_started_event(fileData.getMainFileName())
        scopes, image_ids, omero_path = self._import_files_to_omero(fileData,tags,conn)
        import_time = time.time() - import_time_start
        self._register_in_database(scopes[0],username,groupname,import_time,fileData)
        return image_ids, omero_path

    
    def _store_and_handle_temp_files(self, files: list[FileStorage], username: str) -> FileData:
        def temp_cb(filename: str, prg:int):
            ServerEventManager.send_staging_event(filename,str(int(prg)) + "%")
        fileData = self._temp_file_handler.check_and_store_tempfiles(files, username, temp_cb)
        return fileData
    
    def _import_files_to_omero(self, file: FileData, tags, conn: OmeroConnection):
        filename = file.getMainFileName()
        logger.info(f"Processing of {file.getTempFilePaths()}")
        prog_fun = functools.partial(ServerEventManager.send_progress_event,filename)
        rt_fun = functools.partial(ServerEventManager.send_retry_event,filename)
        import_fun = functools.partial(ServerEventManager.send_importing_event,filename)
        
        return self._file_importer.import_image_data(file, tags, prog_fun, rt_fun, import_fun, conn)
    
    def _remove_temp_files(self, file: FileData):
        self._temp_file_handler._remove_temp_files(file)
    
    def remove_user_upload_dir(self, username):
        self._temp_file_handler._delete_user_upload_dir(username)
        
    def _register_in_database(self, scope, username, groupname, import_time, fileData):
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
