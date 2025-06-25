from datetime import datetime
from unittest.mock import patch
from werkzeug.datastructures import FileStorage
from omerofrontend.file_data import FileData
from omerofrontend.omero_connection import OmeroConnection
from omerofrontend import image_funcs
from omerofrontend.file_importer import FileImporter
from omerofrontend.temp_file_handler import TempFileHandler
from omerofrontend.logger import logging

class FakeDataset:
    def __init__(self, value):
        self.value = value
        
    def getValue(self):
        return self.value


class TestFileImporter:

    @classmethod
    def setup_class(cls):
        cls.fi = FileImporter()
        logging.getLogger().info(f"Starting {cls.__name__}")
        
    @classmethod
    def teardown_class(cls):
        logging.getLogger().info(f"Stopping {cls.__name__}")
    
    def test_file_imports_emd(self):
        czi_path = 'tests/data/test_emd_file.emd'
        # Open the file in binary mode
        with open(czi_path, 'rb') as f:
            username = "gunnar"
            emd_filestorage = FileStorage(
            stream=f,
            filename=czi_path,           # You can set this to whatever name you want
            content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

            tfh = TempFileHandler()
            fileData = tfh.check_and_store_tempfiles([emd_filestorage], username)
            path, metadict = image_funcs.file_format_splitter(fileData)
            scopes = self.fi._get_scopes_metadata(metadict)
            assert path != fileData.getMainFileTempPath()
            assert(len(scopes) == 1)
            assert scopes[0] == 'Talos L120C'  
            self.fi._set_folder_and_converted_name(fileData,metadict, path)
            assert fileData.getConvertedFileName() == "test_emd_file.ome.tiff"
            self.do_file_imports(fileData, metadict, scopes)
            tfh._remove_temp_files(fileData)  # Clean up temp files after test
 
    def test_file_imports_czi(self):
        czi_path = 'tests/data/test_image.czi'
        # Open the file in binary mode
        with open(czi_path, 'rb') as f:
            username = "gunnar"
            czi_filestorage = FileStorage(
            stream=f,
            filename=czi_path,           # You can set this to whatever name you want
            content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

            tfh = TempFileHandler()
            fileData = tfh.check_and_store_tempfiles([czi_filestorage], username)
            path, metadict = image_funcs.file_format_splitter(fileData)
            scopes = self.fi._get_scopes_metadata(metadict)
            assert path == fileData.getMainFileTempPath()  #should be no conversion for .czi files
            assert(len(scopes) == 1)
            assert(scopes[0] == "LSM 980")  
            self.fi._set_folder_and_converted_name(fileData,metadict, path)
            assert fileData.getConvertedFileName() == "test_image.czi"
            self.do_file_imports(fileData, metadict, scopes)
            tfh._remove_temp_files(fileData)  # Clean up temp files after test

    def do_file_imports(self, fileData: FileData, metadict, scopes):

        conn = OmeroConnection()
        dataset = None
        with patch.object(conn,'get_or_create_project', return_value=55), patch.object(conn,'get_or_create_dataset', return_value=66),patch.object(conn,'get_dataset', side_effect=FakeDataset):
            now = datetime.now() # current date and time
            date_time = now.strftime("%m/%d/%Y, %H:%M:%S")
            dataset = self.fi._check_create_project_and_dataset_(scopes[0],date_time, conn)
            assert(dataset == 66)
            
        fname = fileData.getConvertedFileName()    
        with patch.object(conn,'check_duplicate_file', return_value=(False,None)), patch.object(conn,'compareImageAcquisitionTime', return_value=False):
            isDup = self.fi._check_duplicate_file_rename_if_needed(fileData,dataset,metadict,conn)
            assert(not isDup)
            assert(fname == fileData.getConvertedFileName())

        with patch.object(conn,'check_duplicate_file', return_value=(True,66)), patch.object(conn,'compareImageAcquisitionTime', return_value=True):
            isDup = self.fi._check_duplicate_file_rename_if_needed(fileData,dataset,metadict,conn)
            assert(isDup)
            assert(fname == fileData.getConvertedFileName())

            
        with patch.object(conn,'check_duplicate_file', return_value=(True,66)), patch.object(conn,'compareImageAcquisitionTime', return_value=False):
            isDup = self.fi._check_duplicate_file_rename_if_needed(fileData,dataset,metadict,conn)
            assert(not isDup)
            assert(fname != fileData.getConvertedFileName())
            
