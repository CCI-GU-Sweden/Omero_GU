from datetime import datetime
from dateutil import parser
import os.path
from unittest.mock import patch
from werkzeug.datastructures import FileStorage
from common.file_data import FileData
from common.omero_connection import OmeroConnection
from common import image_funcs
from omerofrontend.file_importer import FileImporter
from omerofrontend.temp_file_handler import TempFileHandler
from common.logger import logging
from common.omero_getter_ctx import OmeroGetterCtx

class FakeImage:
    def __init__(self, acqt, name = "", id=666):
        self.acqt = acqt
        self.name = name
        self.id = id
        
    def getAcquisitionDate(self):
        return self.acqt
    
    def getName(self):
        return self.name
    
    def getId(self):
        return self.id


class FakeDataset:
    def __init__(self, value, name, children: list[FakeImage] = []):
        self.value = value
        self.name = name
        self.children = children
        
    def getValue(self):
        return self.value
    
    def getName(self):
        return self.name
    
    def listChildren(self):
        return self.children

class OmeroGetterCtx_(OmeroGetterCtx):
    def __init__(self, omero_connection: OmeroConnection):
        super().__init__(omero_connection)


class FakeProject:
    def __init__(self,proj_name, ds_id, ds_name):
        self._val = proj_name
        self.ds_id = ds_id
        self.ds_name = ds_name
        
    def listChildren(self):
        return [FakeDataset(self.ds_id,self.ds_name)]


class OmeroConnection_(OmeroConnection):
    def __init__(self, host, port, session_token):
        self.host = host
        self.port = port
        self.omero_token = session_token
        #self.conn = BlitzGateway()
        
    def create_dataset(self, project_id: int, dataset_name: str):
        return 66
      
    def get_user_projects(self, user_id):
        return []
    
    def create_project(self, project_name):
        return 55  # Simulated project ID

    def get_or_create_dataset(self, project_id, dataset_name):
        return 66  # Simulated dataset ID


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

            def temp_cb(filename: str, prg:int):
                pass

            tfh = TempFileHandler()
            fileData = tfh.check_and_store_tempfiles([emd_filestorage], username, temp_cb)
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

            def temp_cb(filename: str, prg:int):
               pass

            tfh = TempFileHandler()
            fileData = tfh.check_and_store_tempfiles([czi_filestorage], username, temp_cb)
            path, metadict = image_funcs.file_format_splitter(fileData)
            scopes = self.fi._get_scopes_metadata(metadict)
            assert path == [fileData.getMainFileTempPath()]  #should be no conversion for .czi files
            assert(len(scopes) == 1)
            assert(scopes[0] == "LSM 980")  
            self.fi._set_folder_and_converted_name(fileData,metadict, path)
            assert fileData.getConvertedFileName() == "test_image.czi"
            self.do_file_imports(fileData, metadict, scopes)
            tfh._remove_temp_files(fileData)  # Clean up temp files after test

    def do_file_imports(self, fileData: FileData, metadict, scopes):

        conn = OmeroConnection_("localhost","5000","")
        dataset = None
        now = datetime.now() # current date and time
        date_time = now.strftime("%m/%d/%Y, %H:%M:%S")
        with patch.object(conn,'_get_object', return_value=FakeProject(date_time,66,"66")), patch.object(conn,'get_user_id',return_value=22):
            dataset, _ = self.fi._check_create_project_and_dataset_(scopes[0],date_time, conn)
            assert(dataset == 66)
            
        #conn2 = OmeroConnection_("localhost","5000","")
        fname = fileData.getConvertedFileName()
        with patch.object(conn,'_get_object', return_value=FakeDataset(12,"12")):
            isDup = self.fi._check_duplicate_file_rename_if_needed(fileData,dataset,metadict,conn)
            assert(not isDup)
            assert(fname == fileData.getConvertedFileName())

        acquisition_date_time = acquisition_date_time = parser.parse(metadict['Acquisition date'])
        dup_img = FakeImage(acquisition_date_time,fname,12)
        with patch.object(conn,'get_image', return_value=dup_img), patch.object(conn,'get_dataset', return_value=FakeDataset(66,"66", [dup_img])):
            isDup = self.fi._check_duplicate_file_rename_if_needed(fileData,dataset,metadict,conn)
            assert(isDup)
            assert(fname == fileData.getConvertedFileName())

            
        ndup_img = FakeImage(now,fname,12)
        with patch.object(conn,'get_image', return_value=ndup_img),patch.object(conn,'get_dataset', return_value=FakeDataset(66,"66",[ndup_img])):
            acquisition_date_time = parser.parse(metadict['Acquisition date'])
            acq_time = acquisition_date_time.strftime("%H-%M-%S")
            isDup = self.fi._check_duplicate_file_rename_if_needed(fileData,dataset,metadict,conn)
            assert(not isDup)
            new_file_name = ''.join(fname.split('.')[:1]+['_', acq_time,'.','.'.join(fname.split('.')[1:])])
            assert(new_file_name == fileData.getConvertedFileName())
            assert(fileData.getBasePath() + "/" + new_file_name == fileData.getConvertedFilePath())
            assert( os.path.isfile(fileData.getConvertedFilePath()))
            
