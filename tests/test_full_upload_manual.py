import pytest
#import logging
from queue import Queue, Empty
from werkzeug.datastructures import FileStorage
from omerofrontend.middle_ware import MiddleWare
from omerofrontend.omero_connection import OmeroConnection
from omerofrontend.database import SqliteDatabaseHandler
from omerofrontend import conf
from omerofrontend import logger

session_token = "5e869784-f5d4-4ec3-ad2d-745a1cd5bd8e" # Example session token, replace with valid token

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
        
    def upload_done(self, image_ids):
        logger.info(f"Upload completed with image IDs: {image_ids}")
        self._queue.put(image_ids)
        
    @pytest.mark.manual
    def test_full_upload_manual(self): 
        
        czi_path = 'tests/data/test_image.czi'
        # Open the file in binary mode
        with open(czi_path, 'rb') as f:
            czi_filestorage = FileStorage(
            stream=f,
            filename=czi_path,           # You can set this to whatever name you want
            content_type='application/octet-stream')  # Generic binary; adjust if you know the specific MIME type

            # Perform the upload using the middle ware
            t1 = 'Tag1'
            v1 = 'Value1'
            t2 = 'Tag2'
            v2 = 'Value2'
            scope = 'LSM 980'
            
            tags = {
                t1: v1,
                t2: v2
            }
            
            try:
                self._mw.import_files([czi_filestorage], tags, self._conn, self.upload_done)
                logger.info("File upload initiated successfully.")
            except Exception as e:
                logger.error(f"Error during file upload: {str(e)}")

        image_ids = []
        done = False        
        while not done:
            logger.info("Waiting for upload to complete...")
            try:
                image_ids = self._queue.get(timeout=3)  # Wait for up to 3 seconds for the queue to be filled
                done = True
            except Empty:
                logger.info("Queue is still empty, waiting for upload to complete...")
                continue
                         
        logger.info(f"Received image IDs: {image_ids}")
        
        
        #start tests
        assert len(image_ids) == 3, "wrong nr of image IDs were returned from the upload."
        tags = self._conn.get_image_tags(image_ids[0])  # Check if we can retrieve tags for the uploaded image
        assert f"{t1} {v1}" in tags, f"Tag {t1} with value {v1} not found in image tags."
        assert f"{t2} {v2}" in tags, f"Tag {t2} with value {v2} not found in image tags."
        assert scope in tags, f"Scope {scope} not found in image scopes."
        
        
