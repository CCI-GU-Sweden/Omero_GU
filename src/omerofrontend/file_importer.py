import functools
import os
import datetime
from dateutil import parser
from typing import Tuple
from omerofrontend.server_event_manager import ServerEventManager
from omerofrontend import image_funcs
from omerofrontend import omero_funcs
from omerofrontend import logger
from omerofrontend.omero_connection import OmeroConnection
from omerofrontend.file_data import FileData
from omerofrontend.exceptions import DuplicateFileExists

# class ImportStatus(Enum):
#     IDLE = 0,
#     RUNNING = 1
#     EXIT_OK = 2,
#     EXIT_FAILED = 3
    
class FileImporter:
    
    def import_image_data(self, fileData: FileData, batchtags, conn: OmeroConnection) -> Tuple[list[int], list[str]]:
        filename = fileData.getMainFileName()
        img_ids = []
        file_path, metadict = image_funcs.file_format_splitter(fileData)
        metadict = metadict | batchtags
        scopes = self._get_scopes_metadata(metadict)
        self._set_folder_and_converted_name(fileData,metadict,file_path)
        date_str = metadict['Acquisition date'] 
        dataset = self._check_create_project_and_dataset_(scopes[0], date_str, conn)
        if self._check_duplicate_file_rename_if_needed(fileData, dataset, metadict, conn):
            raise DuplicateFileExists(filename)

        img_ids = self._importImages(fileData, dataset, batchtags, metadict, conn)
        return (img_ids, scopes)

    def _check_create_project_and_dataset_(self,proj_name, date_str, conn: OmeroConnection):

        project_name = proj_name
        acquisition_date_time: datetime.datetime = parser.parse(date_str)
        dataset_name = acquisition_date_time.strftime("%Y-%m-%d")

        # Get or create project and dataset
        projID = conn.get_or_create_project(project_name)
        dataID = conn.get_or_create_dataset(projID, dataset_name)
        logger.info(f"Check ProjectID: {projID}, DatasetID: {dataID}")

        dataset = conn.getDataset(dataID)
        return dataset
        
    def _get_scopes_metadata(self, metadict) -> list:
        scopes = []
        scopes.append(metadict['Microscope'])
        return scopes
        
    #TODO: check with Simon if folder data is needed in metadata
    def _set_folder_and_converted_name(self, fileData: FileData, metadict, file_path: str):
        folder = os.path.basename(os.path.dirname(file_path))
        converted_filename = os.path.basename(file_path)
        fileData.setConvertedFileName(converted_filename)
        if folder != '': 
            metadict['Folder'] = folder

    def _check_duplicate_file_rename_if_needed(self, fileData: FileData, dataset, meta_dict, conn: OmeroConnection):
        #acquisition_date_time = parser.parse(meta_dict['Acquisition date'])
        dup, childId = conn.check_duplicate_file(fileData.getConvertedFileName(),dataset)
        if dup:
            acquisition_date_time = parser.parse(meta_dict['Acquisition date'])
            sameTime = conn.compareImageAcquisitionTime(childId,acquisition_date_time)
            if sameTime:
                return True
        
            file = fileData.getConvertedFileName() #?????????
            acq_time = acquisition_date_time.strftime("%H-%M-%S")
            new_name = ''.join(file.split('.')[:-1]+['_', acq_time,'.',file.split('.')[-1]])   
            fileData.renameFile(new_name)

        return False
        
    def _importImages(self, fileData: FileData, dataset, batch_tag, meta_dict, conn: OmeroConnection):
        
        filename = fileData.getMainFileName()
        logger.info(f"Processing of {fileData.getTempFilePaths()}")

        pfun = functools.partial(ServerEventManager.send_progress_event,filename)
        rtFun = functools.partial(ServerEventManager.send_retry_event,filename)
        image_id = omero_funcs.import_image(conn, fileData, dataset, meta_dict, batch_tag, pfun, rtFun)
        
        return image_id#, dst_path
