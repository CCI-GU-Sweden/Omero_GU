from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
import logger
import datetime
import time
from multiprocessing import Queue
import image_funcs
import omero_funcs
import conf
import os
import traceback
import database
from dateutil import parser


class ImportStatus(Enum):
    IDLE = 0,
    RUNNING = 1
    EXIT_OK = 2,
    EXIT_FAILED = 3
    
PENDING = "pending"
STARTED = "started"
UPLOADING = "uploading"
PROGRESS = "progress"
SUCCESS = "success"

UNSUPPORTED_FORMAT = "unsupported_format"
DUPLICATE = "duplicate"
UNMATCHED = "unmatched"
ERROR = "error"

class FileData:
    
    def __init__(self,files):
        self.originalFileNames = []
        for f in files:
            basename = os.path.basename(f.filename)
            self.originalFileNames.append(basename)
            ext = f.filename.split('.')[1]
            if not ext == "ser" and not ext == "xml":
                self.mainFileExtension = ext
                self.mainFileName = basename
            else:
                self.dictFileExtension = ext
                self.dictFileName = basename
        
    def getMainFileExtension(self):
        return self.mainFileExtension
        
    def getMainFileName(self):
        return self.mainFileName
        
    def getDictFileExtension(self):
        return self.dictFileExtension
    
    def getDictFileName(self):
        return self.dictFileName
        
    def setTempFilePaths(self,paths):
        self.tempPaths = paths
        self.basePath = os.path.dirname(paths[0])
        
    def getTempFilePaths(self):
        return self.tempPaths

    def getBasePath(self):
        return self.basePath

    def getMainFileTempPath(self):
        main_p = ""
        for p in self.tempPaths:
            if self.getMainFileName() in str(p):
                main_p = p
        
        return main_p

    def getDictFileTempPath(self):
        dict_p = ""
        for p in self.tempPaths:
            if self.getDictFileName() in str(p):
                dict_p = p
        
        return dict_p

    def setConvertedFileName(self, convertedName):
        self.convertedFileName = convertedName
        
    def getConvertedFileName(self):
        return self.convertedFileName

    def setFileSizes(self, sizes):
        self.fileSizes = sizes
        
    def getFileSizes(self):
        return self.fileSizes

    def getNrOfFiles(self):
        return len(self.originalFileNames)
    
    def getTotalFileSize(self):
        tot = 0
        for s in self.fileSizes:
            tot += int(s)
            
        return tot

class FileImporter:
    
    _mutex = Lock() #needed?
    _msg_q = Queue()
    _executor = ThreadPoolExecutor(max_workers=5)
    _futures = set()
    
    #asynch method starts a thread, returns imideately
    def startImport(self, files, tags, omeroConnection):
        
        filePaths = []
        fileSizes = []
        for file in files:
            basename = os.path.basename(file.filename)
            if not self.check_supported_format(file.filename):
                self._send_unsupported_event(file.filename)
                return False
            
            self._send_started_event(basename)
            result, filepath, filesize = self._store_temp_file(file)
            
            if not result:
                #probably cleanup here!!!
                #self._send_error_event(basename,"Uploading failed!")
                return False
            
            filePaths.append(filepath)
            fileSizes.append(filesize)

        fileData = FileData(files)
        fileData.setFileSizes(fileSizes)
        fileData.setTempFilePaths(filePaths)
        
        logger.info("Starting import images thread")
        future = self._executor.submit(self._do_file_imports,fileData,tags,omeroConnection)
        #future = self._executor.submit(self._do_file_imports,file.filename,filepath,filesize,tags,omeroConnection)
        future.add_done_callback(self._future_done)
        self._futures.add(future)
        return True
    
    def reset(self):
        self._futures = set()
    
    def _future_done(self,future):
        if future.cancelled():
            logger.info("Import Image was cancelled.")
        elif future.done():
            error = future.exception()
            if error:
                logger.info(f"Import Image exception: {error}")
            else:
                result = future.result()
                #send success here??
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
       
    def _send_unsupported_event(self,fileName):
        event = self._generateEvent(fileName,UNSUPPORTED_FORMAT,"unsupported format")
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
    
    def _put_event(self,fileName,status,message,result=""):
        event = self._generateEvent(fileName,status,message,result)
        self.putEvent(event)
    
    def _generateEvent(self,fileName,status,message,result=""):
        event_data = {
            "name" : fileName,
            "status" : status,
            "message" : message,
            "result" : result
        }
        
        return event_data
       
    def getEvent(self, timeout=None):
        logger.debug(f"Trying to get event from queue {self._msg_q.qsize()}, {self._msg_q}")
        event = self._msg_q.get(timeout=timeout)
        return event
        
    def putEvent(self,event):
        logger.debug(f"putting event on queue {event}, {self._msg_q.qsize()} , {self._msg_q}")
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

    def _remove_temp_files(self,fileData):
        for f in fileData.getTempFilePaths():
            logger.info(f"Deleting temporary file: {f}")
            if os.path.exists(f):
                os.remove(f)

        cf = fileData.getConvertedFileName()
        basePath = fileData.getBasePath()
        cfile = os.path.join(basePath,cf)
        if os.path.exists(cfile):
            
            logger.info(f"Deleting converted files file: {cfile}")
            os.remove(cfile)
    

    # def _do_file_imports(self, filename, filepath, filesize, batchtags, conn):
    def _do_file_imports(self, fileData, batchtags, conn):
        res = False
        try:
            filename = fileData.getMainFileName()
            self._send_progress_event(filename,10)
            import_time_start = time.time()
            res, scopes, img_id, img_path = self._importImages(fileData, batchtags, conn)
            if res:
                self._send_progress_event(filename,95)
                import_time = time.time() - import_time_start
                self._log_and_insert_in_databse(scopes,conn,import_time,fileData)
        except Exception as e:
            logger.error(f"Error during import process: {str(e)}")
            self._send_error_event(filename,str(e))
        finally:
            self._remove_temp_files(fileData)
            if res:
                self._send_success_event(filename,img_path,img_id)

    #def _importImages(self, filename, path, batch_tag, conn):
    def _importImages(self, fileData, batch_tag, conn):
        
        scopes = []
        try:
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
            
            dup, childId = omero_funcs.check_duplicate_filename(conn,converted_filename,dataset)
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

            self._send_progress_event(filename,25)
            
            #import the file
            logger.info(f'Importing {filename}.')
            user = conn.get_logged_in_user_name()
            index = user.find('@')
            user_name = user[:index] if index != -1 else user

            self._send_progress_event(filename,37)

            dst_path = f'{user_name} / {project_name} / {dataset_name}'
            image_id = omero_funcs.import_image(conn, file_path, dataset, meta_dict, batch_tag)
            logger.info(f"ezimport result for {filename}: {image_id}, path: {dst_path}")
            
            self._send_progress_event(filename,75)
            return True, scopes, image_id, dst_path
            
        except Exception as e:
            logger.error(f"Error during import of {filename}: {str(e)}, line: {traceback.format_exc()}")
            self._send_error_event(filename,str(e))
            return  False, []
    
    def _log_and_insert_in_databse(self,scopes, conn,import_time,fileData):
    #def _log_and_insert_in_databse(self,scopes, conn,import_time,file_n,total_file_size):
        if len(scopes) > 0:
            scope = sorted(scopes, key=scopes.count, reverse=True)[0] #take only one scope
            if isinstance(scope, list):
                if len(scope) > 0:
                    scope = scope[0]

        logger.info("Import done")
        
        #get some data
        user = conn.get_user()
        time_stamp = datetime.datetime.today().strftime('%Y-%m-%d')
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
        database.insert_import_data(
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
        
        ext = fileName.split('.')[1]
        return ('.'+ext) in conf.ALLOWED_FOLDER_FILE_EXT
