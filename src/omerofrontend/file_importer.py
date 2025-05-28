import os
import datetime
import time
import traceback
import functools
from dateutil import parser
from multiprocessing import Queue
from enum import Enum
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from . import image_funcs
from . import omero_funcs
from . import conf
from . import logger
from .file_data import FileData

class ImportStatus(Enum):
    IDLE = 0,
    RUNNING = 1
    EXIT_OK = 2,
    EXIT_FAILED = 3
    
#make sure these match javascript versions of same "structs"
PENDING = "pending"
STARTED = "started"
UPLOADING = "uploading"
PROGRESS = "progress"
SUCCESS = "success"

UNSUPPORTED_FORMAT = "unsupported_format"
DUPLICATE = "duplicate"
UNMATCHED = "unmatched"
ERROR = "error"


class FileImporter:
    
    _mutex = Lock() #needed?
    _msg_q = Queue()
    _executor = ThreadPoolExecutor(max_workers=conf.FILE_IMPORT_THREADS)
    _futures = set()
    _db = None
    
    #asynch method starts a thread, returns imideately
    def startImport(self, files, tags, omeroConnection):
        
        filePaths = []
        fileSizes = []
        logger.info("in startImport")
        for file in files:
            basename = os.path.basename(file.filename)
            if not self.check_supported_format(file.filename):
                self._send_unsupported_event(file.filename)
                return False
            
            logger.info(f"Storing temp file {basename}")
            self._send_started_event(basename)
            result, filepath, filesize = self._store_temp_file(file)
            logger.info(f"Done storing temp file {basename}")
            if not result:
                #probably cleanup here!!!
                return False
            
            filePaths.append(filepath)
            fileSizes.append(filesize)

        fileData = FileData(files)
        fileData.setFileSizes(fileSizes)
        fileData.setTempFilePaths(filePaths)
        
        future = self._executor.submit(self._do_file_imports,fileData,tags,omeroConnection)
        future.add_done_callback(self._future_done)
        self._futures.add(future)
        logger.info("Future added to executor")

        return True
    
    def reset(self):
        self._futures = set()
    
    def setDatabaseHandler(self, dbHandler):
        self._db = dbHandler
    
    def _future_done(self,future):
        if future.cancelled():
            logger.info("Import Image was cancelled.")
        elif future.done():
            error = future.exception()
            if error:
                logger.error(f"Import Image exception: {error}, line: {traceback.format_exc()}")
            else:
                result = future.result()
                logger.info(f"Task completed successfully with result: {result}")
        
        self._futures.discard(future)
        
    def isRunning(self):
        running = False
        with self._mutex:
            running = any(not future.done() for future in self._futures)
        
        return running

    def _send_started_event(self,fileName):
        event = self._generateEvent(fileName,STARTED,"preparing file...")
        self.putEvent(event)   
       
    def _send_unsupported_event(self,fileName, msg = ""):
        event = self._generateEvent(fileName,UNSUPPORTED_FORMAT,f" {msg}")
        self.putEvent(event)   
        
    def _send_uploading_event(self,fileName):
        event = self._generateEvent(fileName,UPLOADING,"Uploading file")
        self.putEvent(event)   

    def _send_progress_event(self,fileName,progress):
        event = self._generateEvent(fileName,PROGRESS,str(progress))
        self.putEvent(event)   

    def _send_success_event(self,fileName,path, imageId):
        msg = f"Image id: {imageId}, stored at {path}"
        event = self._generateEvent(fileName,SUCCESS,msg)
        self.putEvent(event)   

    def _send_duplicate_event(self,fileName):
        event = self._generateEvent(fileName,DUPLICATE,"File already in current group")
        self.putEvent(event)   
    
    def _send_error_event(self,fileName,message):
        event = self._generateEvent(fileName,ERROR,message)
        self.putEvent(event)   
        
    def _send_retry_event(self, filename, retry, maxTries):
        self._put_event(filename,str(retry),str(maxTries),result="",type="retry_event")
    
    def _put_event(self,fileName,status,message,result="", type="message"):
        event = self._generateEvent(fileName,status,message,result, type=type)
        self.putEvent(event)
    
    def _generateEvent(self,fileName,status,message,result="", type="message"):
        
        event_data = { 
            
            "data" : { 
                "name" : fileName,
                "status" : status,
                "message" : message,
                "result" : result 
                },
            "type" : type 
            }
        
        return event_data
       
    def getEvent(self, timeout=None):
        event = self._msg_q.get(timeout=timeout)
        return event
        
    def putEvent(self,event):
        self._msg_q.put(event)  
    
    def _store_temp_file(self, file):
        filename = file.filename
        # Create subdirectories if needed
        file_path = os.path.join(conf.UPLOAD_FOLDER, *os.path.split(filename))
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
        file.seek(0)    
        file_size = len(file.read())
        file.seek(0)
    
        # Save file to temporary directory    
        if file_size > conf.MAX_SIZE_FULL_UPLOAD and conf.USE_CHUNK_READ_ON_LARGE_FILES:
            logger.info(f"File {filename} is larger than {conf.MAX_SIZE_FULL_UPLOAD / (1024 * 1024)} MB. Chunked upload will be used.")
            with open(file_path, 'wb') as f:
                while chunk := file.stream.read(conf.CHUNK_SIZE):
                    f.write(chunk)
        else:
            logger.info(f"File {filename} is smaller than {conf.MAX_SIZE_FULL_UPLOAD / (1024 * 1024)} MB. Full upload will be used.")
            file.save(file_path) #one go save
    
        return True, file_path, file_size

    def _remove_temp_files(self,fileData : FileData):
        for f in fileData.getTempFilePaths():
            if os.path.exists(f):
                logger.info(f"Deleting temporary file: {f}")
                os.remove(f)
            else:
                logger.info(f"Temporary file {f} does not exist, unable to remove")

        if not fileData.hasConvertedFileName():
            return
        
        cf = fileData.getConvertedFileName()
        basePath = fileData.getBasePath()
        cfile = os.path.join(basePath,cf)
        if os.path.exists(cfile):
            logger.info(f"Deleting converted files file: {cfile}")
            os.remove(cfile)
        else:
            logger.error(f"Unable to remove converted temp file: {cfile}")
    
    def _do_file_imports(self, fileData, batchtags, conn):
        res = False
        filename = fileData.getMainFileName()
        import_time_start = time.time()

        try:
            res, scopes, img_id, img_path = self._importImages(fileData, batchtags, conn)
            if res:
                import_time = time.time() - import_time_start
                self._log_and_insert_in_databse(scopes,conn,import_time,fileData)

        except FileNotFoundError as fnf:
            logger.error(f"FileNotFoundError during import of {filename}: {str(fnf)}, line: {traceback.format_exc()}")
            self._send_error_event(filename,str(fnf))
        except TypeError as t:
            logger.error(f"TypeError during import of {filename}: {str(t)}, line: {traceback.format_exc()}")
            self._send_unsupported_event(filename, str(t))
        except Exception as e:
            logger.error(f"Error during import of {filename}: {str(e)}, line: {traceback.format_exc()}")
            self._send_error_event(filename,str(e))
        finally:
            self._remove_temp_files(fileData)
            if res:
                self._send_success_event(filename,img_path,img_id)

    def _importImages(self, fileData, batch_tag, conn):
        
        scopes = []
        filename = fileData.getMainFileName()
        logger.info(f"Processing of {fileData.getTempFilePaths()}")
        #Spliter functions required here for multiple file format support
        file_path, meta_dict = image_funcs.file_format_splitter(fileData, verbose=True)
        
        meta_dict = meta_dict | batch_tag #merge the batch tag to the meta_dictionnary
        folder = os.path.basename(os.path.dirname(file_path))
        converted_filename = os.path.basename(file_path)
        fileData.setConvertedFileName(converted_filename)
        if folder != '': meta_dict['Folder'] = folder
        logger.info(f"Metadata successfully extracted from {filename}")

        scopes.append([meta_dict['Microscope']])
        project_name = meta_dict['Microscope']
        acquisition_date_time = parser.parse(meta_dict['Acquisition date'])
        dataset_name = acquisition_date_time.strftime("%Y-%m-%d")
        
        # Get or create project and dataset
        projID = conn.get_or_create_project(project_name)
        dataID = conn.get_or_create_dataset(projID, dataset_name)
        
        logger.info(f"Check ProjectID: {projID}, DatasetID: {dataID}")
        
        # Check if image is already in the dataset and has the acquisition time
        dataset = conn.getDataset(dataID)
        
        dup, childId = omero_funcs.check_duplicate_filename(converted_filename,dataset)
        if dup:
            sameTime = conn.compareImageAcquisitionTime(childId,acquisition_date_time)
            if sameTime:
                logger.info(f'{converted_filename} already exists, skip.')
                self._send_duplicate_event(filename)
                return False, [], "", ""
            
            acq_time = acquisition_date_time.strftime("%H-%M-%S")
            new_name = ''.join(file_path.split('.')[:-1]+['_', acq_time,'.',file_path.split('.')[-1]])   
            os.rename(file_path, new_name)
            logger.info(f'Rename {file_path} to {new_name} in order to avoid name duplication')
            file_path = new_name

        #import the file
        logger.info(f'Importing {filename}.')
        user = conn.get_logged_in_user_name()
        index = user.find('@')
        user_name = user[:index] if index != -1 else user

        dst_path = f'{user_name} / {project_name} / {dataset_name}'
        pfun = functools.partial(self._send_progress_event,filename)
        rtFun = functools.partial(self._send_retry_event,filename)
        image_id = omero_funcs.import_image(conn, file_path, dataset, meta_dict, batch_tag, pfun, rtFun)
        logger.info(f"ezimport result for {filename}: {image_id}, path: {dst_path}")
        
        return True, scopes, image_id, dst_path
                
    
    def _log_and_insert_in_databse(self,scopes, conn,import_time,fileData):
        if len(scopes) > 0:
            scope = sorted(scopes, key=scopes.count, reverse=True)[0] #take only one scope
            if isinstance(scope, list):
                if len(scope) > 0:
                    scope = scope[0]

        logger.info("Import done")
        
        #get some data
        user = conn.get_user()
        time_stamp = datetime.datetime.today().strftime(conf.DATE_TIME_FMT)
        username = user.getFullName()
        group = conn.get_omero_connection().getGroupFromContext()
        groupname = group.getName()

        # security:
        groupname = str(groupname) if groupname else "Unknown Group"
        username = str(username) if username else "Unknown User"
        scope = str(scope) if scope else "Unknown Scope"
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
        if self._db:
            self._db.insert_import_data(
                time=time_stamp,
                username=username,
                groupname=groupname,
                scope=scope,
                file_count=file_n,
                total_file_size_mb=total_file_size / 1024 / 1024,
                import_time_s=import_time
            )
        
    def check_supported_format(self,fileName):
        if not '.' in fileName:
            logger.info(f"{fileName} is not a propper file name")
            return False
        
        ext = fileName.split('.')[-1]
        return ('.'+ext) in conf.ALLOWED_FOLDER_FILE_EXT or ('.'+ext) in conf.ALLOWED_SINGLE_FILE_EXT 