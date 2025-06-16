from pathlib import Path
import platform
import locale
import omero
import sys
import omero.model
from omero.rtypes import rstring, rbool
from omero.model.enums import ChecksumAlgorithmSHA1160
from omero.model import NamedValue, ChecksumAlgorithmI#, FilesetI, FilesetEntryI, UploadJobI
from omero_version import omero_version
from omero.callbacks import CmdCallbackI
from .omero_connection import OmeroConnection

#from typing import List

class FileUploader:
    
    def __init__(self, conn: OmeroConnection) -> None:
        self.oConn = conn
        pass
    
    
    def getManagedRepo(self):
        session = self.oConn.conn.c.getSession()  # Access the underlying client session
        shared_resources = session.sharedResources()

        repos = shared_resources.repositories()
        repoMap = list(zip(repos.proxies, repos.descriptions))
        prx = None
        for (prx, desc) in repoMap:
            if not prx:
                continue
            prx = omero.grid.ManagedRepositoryPrx.checkedCast(prx)
            #prx.importFileSet(fs)
            if prx:
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
        
        
        # with open(file.name, 'rb') as f:
        #     try:
        #         while True:
        #             block = f.read(1024)
        #             if not block:
        #                 break
        #         digest.update(block)
        #     finally:
        #         f.close()

        return digest.hexdigest()

    def create_fileset(self, fileList: list[Path]):
        """Create a new Fileset from local files."""
        fileset = omero.model.FilesetI()
        for f in fileList:
            entry = omero.model.FilesetEntryI()
            entry.setClientPath(rstring(f))
            fileset.addFilesetEntry(entry)
            # Fill version info
            system, node, release, version, machine, processor = platform.uname()
            client_version_info = [
                NamedValue('omero.version', omero_version),
                NamedValue('os.name', system),
                NamedValue('os.version', release),
                NamedValue('os.architecture', machine)
                ]
            try:
                client_version_info.append(
                    NamedValue('locale', locale.getdefaultlocale()[0]))
            except:
                pass
            upload = omero.model.UploadJobI()
            upload.setVersionInfo(client_version_info)
            fileset.linkJob(upload)
            return fileset

    def create_settings(self):
        """Create ImportSettings and set some values."""
        settings = omero.grid.ImportSettings()
        settings.doThumbnails = rbool(True)
        settings.noStatsInfo = rbool(False)
        settings.userSpecifiedTarget = None
        settings.userSpecifiedName = None
        settings.userSpecifiedDescription = None
        settings.userSpecifiedAnnotationList = None
        settings.userSpecifiedPixels = None
        settings.checksumAlgorithm = ChecksumAlgorithmI()
        s = rstring(ChecksumAlgorithmSHA1160)
        settings.checksumAlgorithm.value = s
        return settings
    
    def full_import(self, client, fs_path, wait=-1):
        """Re-usable method for a basic import."""
        mrepo = client.getManagedRepository()
        files = get_files_for_fileset(fs_path)
        assert files, 'No files found: %s' % fs_path
        fileset = create_fileset(files)
        settings = create_settings()
        proc = mrepo.importFileset(fileset, settings)
        try:
            return assert_import(client, proc, files, wait)
        finally:
            proc.close()
            
    def upload_files(self, proc, fileNames: list[Path]):
        """Upload files to OMERO from local filesystem."""
        ret_val = []
        for i, fobj in enumerate(fileNames):
            rfs = proc.getUploader(i)
            try:
                with open(fobj.absolute(), 'rb') as f:
                    print ('Uploading: %s' % fobj)
                    offset = 0
                    block = []
                    rfs.write(block, offset, len(block))
                    # Touch
                    while True:
                        block = f.read(1000 * 1000)
                        if not block:
                            break
                        rfs.write(block, offset, len(block))
                        offset += len(block)
                    ret_val.append(self._sha1(Path(fobj)))
            finally:
                rfs.close()
        return ret_val
    
    def assert_import(self, proc, files, wait):
        """Wait and check that we imported an image."""
        hashes = self.upload_files(proc, files)
        print ('Hashes:\n  %s' % '\n  '.join(hashes))
        handle = proc.verifyUpload(hashes)
        cb = CmdCallbackI(self.oConn.conn.c, handle)
        # https://github.com/openmicroscopy/openmicroscopy/blob/v5.4.9/components/blitz/src/ome/formats/importer/ImportLibrary.java#L631     
        # if wait == 0:
        #     cb.close(False)
        #     return None
        # if wait < 0:
        while not cb.block(2000):
            sys.stdout.write('.')
            sys.stdout.flush()
        sys.stdout.write('\n')
        # else:
        #cb.loop(1, 1000)
        rsp = cb.getResponse()
        if isinstance(rsp, omero.cmd.ERR):
            raise Exception(rsp)
        assert len(rsp.pixels) > 0
        return rsp
        