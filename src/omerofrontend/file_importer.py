import os
import datetime
from typing import Tuple
from dateutil import parser
from common import conf
from common import image_funcs
from common import logger
from common.omero_connection import OmeroConnection
from common.file_data import FileData
from omerofrontend.exceptions import DuplicateFileExists
from omerofrontend.file_uploader import RetryCallback, ProgressCallback, ImportStartedCallback, FileUploader
from common.omero_getter_ctx import OmeroGetterCtx

class FileImporter:
    
    def import_image_data(self, fileData: FileData, batchtags: dict[str,str], progress_cb: ProgressCallback, retry_cb: RetryCallback, import_cb: ImportStartedCallback, conn: OmeroConnection) -> tuple[list[str], list[int], str]:
        filename = fileData.getMainFileName()
        file_path, metadict = image_funcs.file_format_splitter(fileData) #file_path is a list of str

        fileData.addTempFilePaths(file_path)

        #conn: OmeroConnection = OmeroConnection(hostname=conf.OMERO_HOST, port=conf.OMERO_PORT, token=token)
        scopes = self._get_scopes_metadata(metadict)
        self._set_folder_and_converted_name(fileData, metadict, file_path)
        date_str = metadict.get('Acquisition date', datetime.datetime.now().strftime(conf.DATE_TIME_FMT)) 
        dataset_id, proj_id = self._check_create_project_and_dataset_(scopes[0], date_str, conn)

        fu = FileUploader(conn)
        omero_path_last = ""
        image_ids_all: list[int] = []
        for path in file_path:
            #fileData.setUploadFilePaths([path])
            fileData.setConvertedFileName(os.path.basename(path))
            if self._check_duplicate_file_rename_if_needed(fileData, dataset_id, metadict, conn):
                continue
            
            image_ids, omero_path = fu.upload_files(fileData, metadict, batchtags, dataset_id, proj_id, progress_cb, retry_cb, import_cb)

            image_ids_all.extend(image_ids)
            omero_path_last = omero_path

        if not image_ids_all:
            logger.info(f"All files were duplicates for file {filename}")
            raise DuplicateFileExists(filename)

        return scopes, image_ids_all, omero_path_last

    def _check_create_project_and_dataset_(self,proj_name: str, date_str: str, conn: OmeroConnection) -> Tuple[int,int]:

        project_name = proj_name
        acquisition_date_time: datetime.datetime = parser.parse(date_str)
        dataset_name = acquisition_date_time.strftime("%Y-%m-%d")

        with OmeroGetterCtx(conn) as ogc:
        # Get or create project and dataset
            user_id = conn.get_user_id()
            projID = ogc.get_or_create_project(project_name,user_id)
            dataID = ogc.get_or_create_dataset(projID, dataset_name)
            logger.debug(f"Check ProjectID: {projID}, DatasetID: {dataID}")

        return dataID, projID
        
    def _get_scopes_metadata(self, metadict) -> list:
        scopes = []
        scopes.append(metadict.get('Microscope', 'Undefined'))
        return scopes
        
    def _set_folder_and_converted_name(self, fileData: FileData, metadict: dict[str,str], file_path: list[str]):
        first_path = file_path[0]
        folder = os.path.basename(os.path.dirname(first_path)) or ''
        converted_filename = os.path.basename(first_path)
        fileData.setConvertedFileName(converted_filename)
        if folder != '':
            metadict['UploadFolder'] = folder

    def _check_duplicate_file_rename_if_needed(self, fileData: FileData, dataset_id: int, meta_dict: dict[str,str], conn: OmeroConnection):
        
        with OmeroGetterCtx(conn) as ogc:
            dup, childId = ogc.check_duplicate_file(fileData.getConvertedFileName(),dataset_id)

            if dup:
                acquisition_date_time = meta_dict.get('Acquisition date')
                if acquisition_date_time: #no value for date time. Should NOT happen though
                    acquisition_date_time = parser.parse(acquisition_date_time)
                    sameTime = ogc.compare_image_acquisition_time(childId,acquisition_date_time)
                    if sameTime:
                        return True
                else: #security
                    acquisition_date_time = datetime.datetime.now()
            
                file = fileData.getConvertedFileName() #?????????
                acq_time = acquisition_date_time.strftime("%H-%M-%S")
                new_name = ''.join(file.split('.')[:1]+['_', acq_time,'.','.'.join(file.split('.')[1:])])
                fileData.renameFile(new_name)

        return False
        
    # def _importImages(self, fileData: FileData, dataset_id: int, batch_tag: dict[str,str], meta_dict: dict[str,str], conn: OmeroConnection):
        
    #     filename = fileData.getMainFileName()
    #     logger.info(f"Processing of {fileData.getTempFilePaths()}")

    #     pfun = functools.partial(ServerEventManager.send_progress_event,filename)
    #     rtFun = functools.partial(ServerEventManager.send_retry_event,filename)
    #     image_id = omero_funcs.import_image(conn, fileData, dataset_id, meta_dict, batch_tag, pfun, rtFun)
        
    #     return image_id#, dst_path
