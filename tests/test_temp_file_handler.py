import os
import pytest
from omerofrontend.temp_file_handler import TempFileHandler
from omerofrontend.logger import logging
from omerofrontend import conf
from omerofrontend.exceptions import ImageNotSupported, GeneralError
from werkzeug.datastructures import FileStorage
from omerofrontend.file_data import FileData

class TestTempFileHandler:

    @classmethod
    def setup_class(cls):
        cls.tfh = TempFileHandler()
        logging.getLogger().info(f"Starting {cls.__name__}")
        
    @classmethod
    def teardown_class(cls):
        logging.getLogger().info(f"Stopping {cls.__name__}")
        
    
    def test_store_file_ok(self):
        czi_path = 'tests/data/test_image.czi'
        username: str = "ragnar"
         # Open the file in binary mode
        with open(czi_path, 'rb') as f:
            czi_filestorage = FileStorage(
            stream=f,
            filename=czi_path,           # You can set this to whatever name you want
            content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

            fd: FileData = self.tfh.check_and_store_tempfiles([czi_filestorage], username)

            assert(fd.getUserName() == username)
            fsize = os.path.getsize(czi_path)
            assert(fd.getFileSizes()[0] == fsize)
            assert(fd.getTotalFileSize() == fsize)
            file_path = os.path.join(conf.UPLOAD_FOLDER + "/" + username, *os.path.split(czi_path))
            assert(fd.getBasePath() == os.path.dirname(file_path))
            assert(os.path.exists(file_path))


    def test_store_file_nok_file_format(self):
        czi_path = 'tests/data/unsupported.jpg'
        username: str = "ragnar"
         # Open the file in binary mode
        with open(czi_path, 'rb') as f:
            czi_filestorage = FileStorage(
            stream=f,
            filename=czi_path,           # You can set this to whatever name you want
            content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

            with pytest.raises(ImageNotSupported) as excinfo:  
                self.tfh.check_and_store_tempfiles([czi_filestorage], username)
            assert str(excinfo.value) == f"File type is not supported: {czi_path}"


    def test_store_file_nok_file_name(self):
        czi_path = 'tests/data/test_image.czi'
        username: str = "ragnar"
         # Open the file in binary mode
        with open(czi_path, 'rb') as f:
            czi_filestorage = FileStorage(
            stream=f,
            filename=None,           # You can set this to whatever name you want
            content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

            czi_filestorage.filename = None
            with pytest.raises(GeneralError) as excinfo:  
                self.tfh.check_and_store_tempfiles([czi_filestorage], username)
            assert str(excinfo.value) == f"Got file without filename! {czi_filestorage}"
    
            
    def testf_create_user_temp_dir(self):
        czi_path = 'tests/data/test_image.czi'
        username = "ragnar"
        file_path = self.get_temp_ul_path(username,czi_path)
        
        user_ul_folder = conf.UPLOAD_FOLDER + "/" + username
        fp = os.path.join(user_ul_folder, *os.path.split(czi_path))
        
        assert(file_path == fp)
        assert(os.path.isdir(os.path.dirname(file_path)))
 
    def get_temp_ul_path(self,username: str, file: str):
        return os.path.join(conf.UPLOAD_FOLDER + "/" + username, *os.path.split(file))
    
    def test_remove_temp_files(self):
        czi_path = 'tests/data/test_image.czi'
        username: str = "ragnar"
         # Open the file in binary mode
        with open(czi_path, 'rb') as f:
            czi_filestorage = FileStorage(
            stream=f,
            filename=czi_path,           # You can set this to whatever name you want
            content_type='application/octet-stream')
            fd: FileData = self.tfh.check_and_store_tempfiles([czi_filestorage], username)
        
            self.tfh._remove_temp_files(fd)
     
            file_path = self.get_temp_ul_path(username,czi_path)
            assert(not os.path.exists(file_path))
