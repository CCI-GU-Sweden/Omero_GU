import os
import datetime
from typing import Tuple
from dateutil import parser
from omerofrontend import image_funcs
from omerofrontend import logger
from omerofrontend.omero_connection import OmeroConnection
from omerofrontend.file_data import FileData
from omerofrontend.exceptions import DuplicateFileExists
from omerofrontend.file_uploader import RetryCallback, ProgressCallback, ImportStartedCallback, FileUploader
    
class FileImporter:
    
    def import_image_data(self, fileData: FileData, batchtags: dict[str,str], progress_cb: ProgressCallback, retry_cb: RetryCallback, import_cb: ImportStartedCallback, conn: OmeroConnection) -> tuple[list[str], list[int], str]:
        filename = fileData.getMainFileName()
        file_path, metadict = image_funcs.file_format_splitter(fileData)
        scopes = self._get_scopes_metadata(metadict)
        self._set_folder_and_converted_name(fileData,metadict,file_path)
        date_str = metadict['Acquisition date'] 
        dataset_id, proj_id = self._check_create_project_and_dataset_(scopes[0], date_str, conn)
        if self._check_duplicate_file_rename_if_needed(fileData, dataset_id, metadict, conn):
            raise DuplicateFileExists(filename)

        fu = FileUploader(conn)
        image_ids, omero_path = fu.upload_files(fileData, metadict, batchtags, dataset_id, proj_id, progress_cb, retry_cb, import_cb)
        return scopes, image_ids, omero_path

    def _check_create_project_and_dataset_(self,proj_name: str, date_str: str, conn: OmeroConnection) -> Tuple[int,int]:

        project_name = proj_name
        acquisition_date_time: datetime.datetime = parser.parse(date_str)
        dataset_name = acquisition_date_time.strftime("%Y-%m-%d")

        # Get or create project and dataset
        projID = conn.get_or_create_project(project_name)
        dataID = conn.get_or_create_dataset(projID, dataset_name)
        logger.debug(f"Check ProjectID: {projID}, DatasetID: {dataID}")

        return dataID, projID
        
    def _get_scopes_metadata(self, metadict) -> list:
        scopes = []
        scopes.append(metadict['Microscope'])
        return scopes
        
    #TODO: check with Simon if folder data is needed in metadata
    def _set_folder_and_converted_name(self, fileData: FileData, metadict: dict[str,str], file_path: str):
        folder = os.path.basename(os.path.dirname(file_path))
        converted_filename = os.path.basename(file_path)
        fileData.setConvertedFileName(converted_filename)
        if folder != '': 
            metadict['Folder'] = folder

    def _check_duplicate_file_rename_if_needed(self, fileData: FileData, dataset_id: int, meta_dict: dict[str,str], conn: OmeroConnection):
        dup, childId = conn.check_duplicate_file(fileData.getConvertedFileName(),dataset_id)
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
        
    # def _importImages(self, fileData: FileData, dataset_id: int, batch_tag: dict[str,str], meta_dict: dict[str,str], conn: OmeroConnection):
        
    #     filename = fileData.getMainFileName()
    #     logger.info(f"Processing of {fileData.getTempFilePaths()}")

    #     pfun = functools.partial(ServerEventManager.send_progress_event,filename)
    #     rtFun = functools.partial(ServerEventManager.send_retry_event,filename)
    #     image_id = omero_funcs.import_image(conn, fileData, dataset_id, meta_dict, batch_tag, pfun, rtFun)
        
    #     return image_id#, dst_path
