import pytest
import io
from omerofrontend import conf
from omerofrontend.file_data import FileData
import os
from pathlib import Path
from omerofrontend.file_importer import FileImporter
from werkzeug.datastructures import FileStorage
import logging



class TestFileImporter:

    @classmethod
    def setup_class(cls):
        cls.fi = FileImporter()
        logging.getLogger().info(f"Starting {cls.__name__}")
        
    @classmethod
    def teardown_class(cls):
        logging.getLogger().info(f"Stopping {cls.__name__}")
    

    #def test_convert_functions(self):
        #TODO: Implement!!!

    def test_store_and_remove_temp_file_tif(self):
        tif_path = 'tests/data/test_data.tif'

        # Open the file in binary mode
        with open(tif_path, 'rb') as f:
            tif_filestorage = FileStorage(
            stream=f,
            filename=tif_path,           # You can set this to whatever name you want
            content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

            #filePath = os.path.join(conf.UPLOAD_FOLDER, *os.path.split(czi_path))
            filePath = os.path.join(conf.UPLOAD_FOLDER,os.path.basename(tif_path))
            res, fpath, file_size = self.fi._store_temp_file(tif_filestorage)
        
            assert(res)
            assert(fpath == filePath)
            #assert(os.path.isdir(os.path.dirname(filePath)))
            assert(os.path.exists(filePath))

            fileData = FileData(tif_filestorage)
            fileData.setTempFilePaths([fpath])
            fileData.setConvertedFileName(fpath)
            self.fi._remove_temp_files(fileData)

            assert(not os.path.exists(filePath))
            assert(len(os.listdir(os.path.dirname(filePath))) == 0 ) #empty dir


    def test_store_and_remove_temp_file_czi(self):
        czi_path = 'tests/data/test_image.czi'

        # Open the file in binary mode
        with open(czi_path, 'rb') as f:
            czi_filestorage = FileStorage(
            stream=f,
            filename=czi_path,           # You can set this to whatever name you want
            content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

            #filePath = os.path.join(conf.UPLOAD_FOLDER, *os.path.split(czi_path))
            filePath = os.path.join(conf.UPLOAD_FOLDER,os.path.basename(czi_path))
            res, fpath, file_size = self.fi._store_temp_file(czi_filestorage)
        
            assert(res)
            assert(fpath == filePath)
            #assert(os.path.isdir(os.path.dirname(filePath)))
            assert(os.path.exists(filePath))

            fileData = FileData(czi_filestorage)
            fileData.setTempFilePaths([fpath])
            fileData.setConvertedFileName(fpath)
            self.fi._remove_temp_files(fileData)

            assert(not os.path.exists(filePath))
            assert(len(os.listdir(os.path.dirname(filePath))) == 0 ) #empty dir
            
