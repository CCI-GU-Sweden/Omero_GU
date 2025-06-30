import pytest
#import logging
from queue import Queue, Empty
from werkzeug.datastructures import FileStorage
from omerofrontend.middle_ware import MiddleWare
from omerofrontend.omero_connection import OmeroConnection
from omerofrontend.database import SqliteDatabaseHandler
from omerofrontend import conf
from omerofrontend import logger

session_token = "d2122204-5754-463e-9291-ba22ae64f75a" # Example session token, replace with valid token

t1 = 'Tag1'
v1 = 'Value1'
t2 = 'Tag2'
v2 = 'Value2'

tags = {
    t1: v1,
    t2: v2
}

class TestFullUploadManual:

    @classmethod
    def setup_class(cls):
        db = SqliteDatabaseHandler()
        cls._mw = MiddleWare(db)
        cls._conn = OmeroConnection(conf.OMERO_HOST,conf.OMERO_PORT,session_token)
        cls._queue = Queue()
        logger.setup_logger()
        
    @classmethod
    def teardown_class(cls):
        pass
        
    def upload_done(self, image_ids, result: bool):
        logger.info(f"Upload completed with image IDs: {image_ids}")
        self._queue.put((image_ids, result))
        
    def wait_and_assert(self, scope, extrak, extrav):
        image_ids = []
        done = False
        result = False
        while not done:
            logger.info("Waiting for upload to complete...")
            try:
                (image_ids, result) = self._queue.get(timeout=5)  # Wait for up to 3 seconds for the queue to be filled
                done = True
            except Empty:
                logger.info("Queue is still empty, waiting for upload to complete...")
                continue
                         
        logger.info(f"Received image IDs: {image_ids}")
        
        #start tests
        assert result, "Upload did not complete successfully."
        assert len(image_ids) >= 1, "No image IDs were returned from the upload."
        tags = self._conn.get_image_tags(image_ids[0])  # Check if we can retrieve tags for the uploaded image
        assert f"{t1} {v1}" in tags, f"Tag {t1} with value {v1} not found in image tags."
        assert f"{t2} {v2}" in tags, f"Tag {t2} with value {v2} not found in image tags."
        assert scope in tags, f"Scope {scope} not found in image scopes."
        
        kv_pairs = self._conn.get_image_map_annotations(image_ids[0])
        assert kv_pairs is not None, "Key-value pairs should not be None."
        assert ('Microscope', scope) in kv_pairs, f"Expected scope {scope}"
        assert (extrak,extrav) in kv_pairs, f"Expected {extrak} to be {extrav}."
        assert (t1, v1) in kv_pairs, f"Expected {t1} to be {v1}"
        assert (t2, v2) in kv_pairs, f"Expected {t2} to be {v2}"
        
    @pytest.mark.manual
    def test_full_upload_manual(self): 
        
        file_paths = ['tests/data/test_image.czi','tests/data/sample6_001.tif']
        mags = ['63', '22370.0']
        scopes = ['LSM 980', 'GeminiSEM 450']
        
        for i, file in enumerate(file_paths):
        # Open the file in binary mode
            with open(file, 'rb') as f:
                filestorage = FileStorage(
                stream=f,
                filename=file,           # You can set this to whatever name you want
                content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

                # Perform the upload using the middle ware
                try:
                    self._mw.import_files([filestorage], tags, self._conn, self.upload_done)
                    logger.info("File upload initiated successfully.")
                except Exception as e:
                    logger.error(f"Error during file upload: {str(e)}")
                    
                self.wait_and_assert(scopes[i], 'Lens Magnification', mags[i])

        #file_paths = [('tests/data/49944_A1_0001_1.ser','tests/data/49944_A1_0001.emi'),('tests/data/Atlas_1.mrc','tests/data/Atlas_1.xml')]
        file_paths = [('tests/data/Atlas_1.mrc','tests/data/Atlas_1.xml'),('tests/data/49944_A1_0001_1.ser','tests/data/49944_A1_0001.emi')]
        #mags = ['63', '22370.0']
        electron_sources = ['Thermionic', 'LaB6']
        scopes = ['Talos L120C', 'Talos L120C']
        
        for i, file in enumerate(file_paths):
        # Open the file in binary mode
            with open(file[0], 'rb') as f1, open(file[1], 'rb') as f2:
                f1_storage = FileStorage(
                stream=f1,
                filename=file[0],           # You can set this to whatever name you want
                content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

                f2_storage = FileStorage(
                    stream=f2,
                    filename=file[1],           # You can set this to whatever name you want
                    content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

                # Perform the upload using the middle ware
                try:
                    self._mw.import_files([f1_storage,f2_storage], tags, self._conn, self.upload_done)
                    logger.info("File upload initiated successfully.")
                except Exception as e:
                    logger.error(f"Error during file upload: {str(e)}")
                    
                self.wait_and_assert(scopes[i], 'Electron source', electron_sources[i])

        
