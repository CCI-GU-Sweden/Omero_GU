from pathlib import Path
import platform
import locale
import omero
import hashlib
import omero.model
import omero.grid
import traceback
from typing import Callable, Optional
from omero.rtypes import rstring, rbool
from omero.model.enums import ChecksumAlgorithmSHA1160 # type: ignore
from omero_version import omero_version
from omero.callbacks import CmdCallbackI
from omerofrontend.file_data import FileData
from omerofrontend.omero_connection import OmeroConnection
from omerofrontend.exceptions import OmeroConnectionError, AssertImportError, ImportError
from omerofrontend import logger
from omerofrontend import conf

ProgressCallback = Optional[Callable[[int], None]]  # Define a type for the progress callback
RetryCallback = Optional[Callable[[str, int], None]]  # Define a type for the retry callback

class FileUploader:
    
    def __init__(self, conn: OmeroConnection) -> None:
        self._oConn = conn
        pass
    
    def upload_files(self, filedata: FileData, meta_dict: dict[str, str], tags: dict[str, str], dataset_id: int,  progress_cb: ProgressCallback = None, retry_cb: RetryCallback = None) -> list[int]:
        """Upload files to OMERO from local filesystem."""
        
        #TODO: errorhandling in this function is not very good, should be improved
        mrepo = self._get_managed_repo()
        if not mrepo:
            raise OmeroConnectionError("Managed repository not found.")
        
        fileset = self._create_fileset(filedata)
        
        annotations = self._create_annotation_objects(meta_dict, tags)
        description = meta_dict.get('Description', 'N/A')
        settings = self._create_settings(dataset_id, description, annotations)
        try:
            proc = mrepo.importFileset(fileset, settings)
        except Exception as ie:
            logger.error(f"Import exception: {str(ie)}, traceback: {traceback.format_exc()}")
            raise OmeroConnectionError(f"Failed to create import process: {str(ie)}")
          
        retry_cnt = 0
        done = False
        response = None
        while not done:
            try:
                hashes = self._upload_and_calculate_hash(proc,filedata, progress_cb)
                response = self._assert_import(proc, hashes)
                done = True
            except AssertImportError as aie:
                logger.error(f"Import assertion error: {str(aie)}")
                if retry_cb:
                    retry_cb(str(aie.filename), retry_cnt)
                retry_cnt += 1
                if retry_cnt >= conf.IMPORT_NR_OF_RETRIES:
                    logger.error(f"Maximum number of retries ({conf.IMPORT_NR_OF_RETRIES}) reached. Aborting import.")
                    done = True
                    proc.close()
                    raise ImportError(f"Import failed after {conf.IMPORT_NR_OF_RETRIES} retries: {str(aie)}")
                
            finally:
                proc.close()

        if response is None:
            raise ImportError("No response received from the import process. Import may have failed.")
            
        image_ids: list[int] = []                
        for objs in response.objects:
            if isinstance(objs, omero.model.ImageI): # type: ignore
                image = objs
                image_ids.append(image.getId().getValue())
                logger.info(f"Image {image.getName()} with ID {image.getId()} imported successfully.")
            elif isinstance(objs, omero.model.DatasetI): # type: ignore
                dataset = objs
                logger.info(f"Dataset {dataset.getName()} with ID {dataset.getId()} imported successfully.")
            else:
                logger.warning(f"Unexpected object type returned: {type(objs)}")

        return image_ids
    
    def _create_annotation_objects(self, meta_dict: dict[str, str], tags: dict[str,str]):

        result_list = []

        for k, v in meta_dict.items() | tags.items():
            if k == 'Comment' and v is not None:
                ca = omero.model.CommentAnnotationI() # type: ignore
                ca.setTextValue(rstring(v))
                result_list.append(ca)
                continue
            map_ann = self._oConn.get_map_annotation(k,v)
            if map_ann:
                id = map_ann.getId()
                logger.debug(f"Using existing map annotation for {k}: {id}")
                map_annotation = omero.model.MapAnnotationI(id) # type: ignore
            else:
                map_annotation = omero.model.MapAnnotationI() # type: ignore
            if type(v) is not str:
                v = str(v)
            value = omero.model.NamedValue(k, v) # type: ignore
            map_annotation.setMapValue([value])
            result_list.append(map_annotation)
        
        tags_list = []
        for k, v in tags.items():
            ti = omero.model.TagAnnotationI() # type: ignore
            ti.setTextValue(rstring(f"{k} {v}"))
            tags_list.append(ti)

        if len(tags_list) > 0:
            result_list.extend(tags_list)

        extra_tags_names = ['Microscope', 'Lens Magnification', 'Image type']
        extra_tags = []
        for tag_name in extra_tags_names:
            if tag_name in meta_dict:
                tagvalue = meta_dict[tag_name]
                if tag_name == 'Lens Magnification':
                    tagvalue = str(tagvalue) + 'X'  # Append 'x' to the lens magnification value
                if ta := self._oConn.get_tag_annotation_id(tagvalue):
                    ti = omero.model.TagAnnotationI(ta) # type: ignore
                else:
                    ti = omero.model.TagAnnotationI() # type: ignore
                ti.setTextValue(rstring(tagvalue))
                extra_tags.append(ti)

        if len(extra_tags) > 0:
           result_list.extend(extra_tags)
        
        return result_list

        
    def _get_managed_repo(self):
        
        if not self._oConn.conn:
            raise OmeroConnectionError("No connection to OMERO server established.")
        if not self._oConn.conn.c:
            raise OmeroConnectionError("No client connection available.")
        
        session = self._oConn.conn.c.getSession()  # Access the underlying client session
        if not session:
            raise OmeroConnectionError("No session available in the client connection.")
        
        shared_resources = session.sharedResources()

        repos = shared_resources.repositories()
        repoMap = list(zip(repos.proxies, repos.descriptions))
        prx = None
        for (prx, desc) in repoMap:
            if not prx:
                continue
            prx = omero.grid.ManagedRepositoryPrx.checkedCast(prx) # type: ignore
            if prx is not None:
                break
            
        return prx

    
    def _sha1(self, file : Path) -> str:
        """
        Calculates the local sha1 for a file.
        """
        from hashlib import sha1
        digest = sha1()
        with open(file, 'rb') as f:
            for block in iter(lambda: f.read(1024), b''):
                digest.update(block)
        
        return digest.hexdigest()


    def _create_fileset(self, filedata: FileData) -> omero.model.FilesetI: # type: ignore
        """Create a new Fileset from local files."""
        fileset = omero.model.FilesetI() # type: ignore
        for f in filedata.getTempFilePaths():
            entry = omero.model.FilesetEntryI() # type: ignore
            entry.setClientPath(rstring(f))
            fileset.addFilesetEntry(entry)
            # Fill version info
            system, node, release, version, machine, processor = platform.uname()
            client_version_info = [
                omero.model.NamedValue('omero.version', omero_version), # type: ignore
                omero.model.NamedValue('os.name', system), # type: ignore
                omero.model.NamedValue('os.version', release), # type: ignore
                omero.model.NamedValue('os.architecture', machine) # type: ignore
                ]
            try:
                client_version_info.append(
                    omero.model.NamedValue('locale', locale.getdefaultlocale()[0])) #type: ignore
            except Exception:  # pragma: no cover
                pass
            upload = omero.model.UploadJobI() #type: ignore
            upload.setVersionInfo(client_version_info)
            fileset.linkJob(upload)
            return fileset

    def _create_settings(self, datasset_id: int, description: str, annotations) -> omero.grid.ImportSettings: # type: ignore
        """Create ImportSettings and set some values."""
        settings = omero.grid.ImportSettings() # type: ignore
        settings.doThumbnails = rbool(True)
        settings.noStatsInfo = rbool(False)

        dataset = omero.model.DatasetI(datasset_id, False) # type: ignore
        settings.userSpecifiedTarget = dataset

        settings.userSpecifiedName = None #For images, this is the name if the image
        settings.userSpecifiedDescription = rstring(description)
        
        settings.userSpecifiedAnnotationList = annotations
        settings.userSpecifiedPixels = None
        settings.checksumAlgorithm = omero.model.ChecksumAlgorithmI() # type: ignore
        s = rstring(ChecksumAlgorithmSHA1160)
        settings.checksumAlgorithm.value = s

        return settings
        
    def _upload_and_calculate_hash(self, proc, filedata: FileData, progress_cb: ProgressCallback = None) -> list[str]:
        """Upload files to OMERO from local filesystem.
        Returns the SHA1 hash of the file for verification.
        """        
        hashes = []
        totSize: int = filedata.getTotalFileSize()
        totRead: int = 0
        for i, fobj in enumerate(filedata.getTempFilePaths()):
            rfs = proc.getUploader(i)
            digest = hashlib.sha1()  # Add 'import hashlib' at top
        
            try:
                with open(fobj, 'rb') as f:  # file is already a Path
                # Single-pass upload and hash calculation
                    offset = 0
                    while (block := f.read(1_000_000)):  # Walrus operator (Python 3.8+)
                        rfs.write(block, offset, len(block))
                        digest.update(block)
                        read_size = len(block)
                        totRead += read_size
                        offset += len(block)
                        if progress_cb:
                            progress_cb(int((totRead / totSize) * 100))
            except FileNotFoundError as fnf:
                error_msg = f"File not found during upload: {fnf.filename}"
                logger.error(error_msg)
                raise OmeroConnectionError(error_msg)
            finally:
                rfs.close()  # Ensure cleanup even if errors occur
        
            hashes.append(digest.hexdigest())

        return hashes

    #TODO: add filedata or filename as parameter for better error messages
    def _assert_import(self, proc, hashes):
        """Wait and check that we imported an image correctly."""
        if self._oConn.conn is None or self._oConn.conn.c is None:
            raise OmeroConnectionError("Could not assert file upload. No connection to OMERO server established.")
        handle = proc.verifyUpload(hashes)
        cb = CmdCallbackI(self._oConn.conn.c, handle)
        # https://github.com/openmicroscopy/openmicroscopy/blob/v5.4.9/components/blitz/src/ome/formats/importer/ImportLibrary.java#L631     
        while not cb.block(2000):
            logger.info('Waiting for import to finish...')
        rsp = cb.getResponse()
        if isinstance(rsp, omero.cmd.ERR): # type: ignore
            raise AssertImportError(message=str(rsp))
        return rsp
        