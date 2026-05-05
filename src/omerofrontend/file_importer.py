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

    def _build_time_suffixed_name(self, filename: str, acquisition_date_time: datetime.datetime) -> str:
        stem, ext = os.path.splitext(filename)
        return f"{stem}_{acquisition_date_time.strftime('%H-%M-%S')}{ext}"
    
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
        acquisition_date_time = meta_dict.get('Acquisition date')
        parsed_acquisition_date: datetime.datetime | None = None
        if acquisition_date_time:
            parsed_acquisition_date = parser.parse(acquisition_date_time)

        with OmeroGetterCtx(conn) as ogc:
            dup, childId = ogc.check_duplicate_file(fileData.getConvertedFileName(),dataset_id)

            if dup and childId is not None:
                if parsed_acquisition_date is not None: #no value for date time. Should NOT happen though
                    sameTime = ogc.compare_image_acquisition_time(childId,parsed_acquisition_date)
                    if sameTime:
                        return True
                    # Some OMERO backends normalize acquisition date/time differently;
                    # use the stored map annotation as a secondary exact-date check.
                    stored_acq_date = ogc.get_map_annotation_value(childId, 'Acquisition date')
                    expected_acq_date = parsed_acquisition_date.strftime(conf.DATE_TIME_FMT)
                    if stored_acq_date == expected_acq_date:
                        return True

            # Backward compatibility: older imports may already exist with the time-suffixed name.
            if parsed_acquisition_date is not None:
                alternate_name = self._build_time_suffixed_name(fileData.getConvertedFileName(), parsed_acquisition_date)
                dup_alt, child_alt_id = ogc.check_duplicate_file(alternate_name, dataset_id)
                if dup_alt and child_alt_id is not None:
                    sameTimeAlt = ogc.compare_image_acquisition_time(child_alt_id, parsed_acquisition_date)
                    if sameTimeAlt:
                        return True
                    stored_acq_date_alt = ogc.get_map_annotation_value(child_alt_id, 'Acquisition date')
                    expected_acq_date = parsed_acquisition_date.strftime(conf.DATE_TIME_FMT)
                    if stored_acq_date_alt == expected_acq_date:
                        return True

            if dup:
                if parsed_acquisition_date is None: #security
                    parsed_acquisition_date = datetime.datetime.now()

                new_name = self._build_time_suffixed_name(fileData.getConvertedFileName(), parsed_acquisition_date)
                fileData.renameFile(new_name)

        return False
        
    # def _importImages(self, fileData: FileData, dataset_id: int, batch_tag: dict[str,str], meta_dict: dict[str,str], conn: OmeroConnection):
        
    #     filename = fileData.getMainFileName()
    #     logger.info(f"Processing of {fileData.getTempFilePaths()}")

    #     pfun = functools.partial(ServerEventManager.send_progress_event,filename)
    #     rtFun = functools.partial(ServerEventManager.send_retry_event,filename)
    #     image_id = omero_funcs.import_image(conn, fileData, dataset_id, meta_dict, batch_tag, pfun, rtFun)
        
    #     return image_id#, dst_path
