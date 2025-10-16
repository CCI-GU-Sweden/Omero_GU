import os
import shutil
from typing import Callable, Optional
from werkzeug.datastructures import FileStorage
from common import logger
from common import conf
from common.file_data import FileData
from common import image_funcs
from omerofrontend.exceptions import GeneralError, ImageNotSupported, OutOfDiskError

TempProgressCallback = Optional[Callable[[str, int], None]]  # Define a type for the progress callback

class TempFileHandler:
    
    def check_and_store_tempfiles(self, files: list[FileStorage], username: str, temp_cb: TempProgressCallback) -> FileData:
        filePaths = []
        fileSizes = []
        fileNames = []
        logger.info("in startImport")
        for file in files:
            if file.filename is None:
                raise GeneralError(None,f"Got file without filename! {file}")
            
            if not image_funcs.is_supported_format(file.filename):
                raise ImageNotSupported(file.filename) 

            result, filepath, filesize = self._store_temp_file(file, file.filename, username, temp_cb)
            if not result:
                raise GeneralError(None, "Unable to store temp file {file}")
            
            fileNames.append(file.filename)
            filePaths.append(filepath)
            fileSizes.append(filesize)

        fileData = FileData(fileNames)
        fileData.setUserName(username)
        fileData.setFileSizes(fileSizes)
        fileData.setTempFilePaths(filePaths)
        
        return fileData
    
    
    def _store_temp_file(self, file: FileStorage, filename: str, username: str, temp_cb: TempProgressCallback):
        
        def call_if_not_none(cb, fname, data):
            return cb(fname, data) if cb is not None else None
        
        file_path = self._create_user_temp_dir(filename, username)
    
        file.seek(0)    
        file_size = len(file.read())
        file.seek(0)
    
        try:
            call_if_not_none(temp_cb,filename,0)
            # Save file to temporary directory
            if file_size <= conf.MAX_SIZE_FULL_UPLOAD or not conf.USE_CHUNK_READ_ON_LARGE_FILES:
                logger.debug(f"File {filename} is smaller than {conf.MAX_SIZE_FULL_UPLOAD / (1024 * 1024)} MB. Full upload will be used.")
                file.save(file_path) #one go save
                call_if_not_none(temp_cb, filename, 100)

            else:        
                logger.debug(f"File {filename} is larger than {conf.MAX_SIZE_FULL_UPLOAD / (1024 * 1024)} MB. Chunked upload will be used.")
                tot = 0
                with open(file_path, 'wb') as f:
                    while chunk := file.stream.read(conf.CHUNK_SIZE):
                        tot += len(chunk)
                        f.write(chunk)
                        call_if_not_none(temp_cb, filename, (tot / file_size) * 100)
                        #logger.debug(f"storing {tot} of {file_size} ")
        except Exception as e:
            logger.error(f"Error in _store_temp_file:  {str(e)}")
            raise OutOfDiskError(filename, file_path, "Out Of Disk on temp storage!")
    
        return True, file_path, file_size

    def _remove_temp_files(self,fileData : FileData):
        for f in fileData.getTempFilePaths():
            self.remove_temp_file_by_path(f)
        #     if os.path.exists(f):
        #         logger.info(f"Deleting temporary file: {f}")
        #         os.remove(f)
        #     else:
        #         logger.info(f"Temporary file {f} does not exist, unable to remove")

        if not fileData.hasConvertedFileName():
            return
        
        cf = fileData.getConvertedFileName()
        basePath = fileData.getBasePath()
        cfile = os.path.join(basePath,cf)
        if os.path.exists(cfile):
            logger.info(f"Deleting converted files file: {cfile}")
            os.remove(cfile)
        else:
            logger.info(f"Unable to remove converted temp file: {cfile} since it did not exist (perhaps not converted at all?)")
            
    def remove_temp_file_by_path(self, filepath: str):
        if os.path.exists(filepath):
            logger.info(f"Deleting temporary file: {filepath}")
            os.remove(filepath)
        else:
            logger.info(f"Temporary file {filepath} does not exist, unable to remove")

       
    def _create_user_temp_dir(self, filename: str, username: str) -> str:
          # Create subdirectories if needed
        user_ul_folder = conf.UPLOAD_FOLDER + "/" + username
        file_path = os.path.join(user_ul_folder, *os.path.split(filename))
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        return file_path
    
    def _delete_user_upload_dir(self, username: str):
        user_ul_folder = conf.UPLOAD_FOLDER + "/" + username
        if os.path.exists(user_ul_folder):
            shutil.rmtree(user_ul_folder)