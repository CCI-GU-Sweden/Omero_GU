import os
from werkzeug.datastructures import FileStorage
from omerofrontend import logger
from omerofrontend import conf
from omerofrontend.file_data import FileData
from omerofrontend.image_funcs import is_supported_format
from omerofrontend.exceptions import GeneralError, ImageNotSupported

class TempFileHandler:
    
    def check_and_store_tempfiles(self, files: list[FileStorage], username: str) -> FileData:
        filePaths = []
        fileSizes = []
        fileNames = []
        logger.info("in startImport")
        for file in files:
            if file.filename is None:
                raise GeneralError(None,f"Got file without filename! {file}")
            
            if not is_supported_format(file.filename):
                raise ImageNotSupported(file.filename) 

            result, filepath, filesize = self._store_temp_file(file, file.filename, username)
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
    
    
    def _store_temp_file(self, file: FileStorage, filename: str, username: str):
        
        file_path = self._create_user_temp_dir(filename, username)
    
        file.seek(0)    
        file_size = len(file.read())
        file.seek(0)
    
        # Save file to temporary directory    
        if file_size > conf.MAX_SIZE_FULL_UPLOAD and conf.USE_CHUNK_READ_ON_LARGE_FILES:
            logger.debug(f"File {filename} is larger than {conf.MAX_SIZE_FULL_UPLOAD / (1024 * 1024)} MB. Chunked upload will be used.")
            with open(file_path, 'wb') as f:
                while chunk := file.stream.read(conf.CHUNK_SIZE):
                    f.write(chunk)
        else:
            logger.debug(f"File {filename} is smaller than {conf.MAX_SIZE_FULL_UPLOAD / (1024 * 1024)} MB. Full upload will be used.")
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
            logger.info(f"Unable to remove converted temp file: {cfile} since it did not exist (perhaps not converted at all?)")
            
        
    def _create_user_temp_dir(self, filename: str, username: str) -> str:
          # Create subdirectories if needed
        user_ul_folder = conf.UPLOAD_FOLDER + "/" + username
        file_path = os.path.join(user_ul_folder, *os.path.split(filename))
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        return file_path