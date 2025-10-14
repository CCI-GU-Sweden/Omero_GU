import os
from typing import Optional

class FileData:
    
    #TODO: Implement constructor that takes filestoreage instead in order to be able to use FileData in futures context map
    
    def __init__(self,fileBaseNames):
        self.originalFileNames = []
        self._upload_paths: list[str] = []
        self.annotations: Optional[dict[str,str]] = None
        self.username: Optional[str] = None
        for f in fileBaseNames:
            basename = f #only last part of path, like 'filename.ext'
            self.originalFileNames.append(basename)
            ext = f.split('.')[-1]
            if not ext == "ser" and not ext == "xml":
                self.mainFileExtension: str = ext
                self.mainFileName: str = basename
            else:
                self.dictFileExtension:str = ext
                self.dictFileName:str = basename
                        
    def getMainFileExtension(self) -> str:
        return self.mainFileExtension
        
    def getMainFileName(self) -> str:
        return self.mainFileName
        
    def getDictFileExtension(self) -> str:
        return self.dictFileExtension
    
    def getDictFileName(self) -> str:
        return self.dictFileName
        
    def setTempFilePaths(self, paths: list[str]):
        self.tempPaths = paths
        self.basePath = os.path.dirname(paths[0])
        
    def getTempFilePaths(self) -> list[str]:
        return self.tempPaths
    
    def addTempFilePaths(self, paths: list[str]) -> None:
        import os
        cur = {os.path.normpath(p) for p in self.getTempFilePaths()}
        new = {os.path.normpath(p) for p in paths}
        self.setTempFilePaths(list(cur | new))

    def getBasePath(self) -> str:
        return self.basePath

    def getMainFileTempPath(self) -> str:
        main_p = ""
        for p in self.tempPaths:
            if self.getMainFileName() in str(p):
                main_p = p
        
        return main_p

    def getDictFileTempPath(self):
        dict_p = ""
        for p in self.tempPaths:
            if self.getDictFileName() in str(p):
                dict_p = p
        
        return dict_p
    
    def setUserName(self, username: str):
        self.username = username
    
    def getUserName(self) -> Optional[str]:
        return self.username

    def setUploadFilePaths(self, paths: list[str]) -> None:
        self._upload_paths = list(paths)

    def getUploadFilePaths(self) -> list[str]:
        # fallback to single path if legacy code set only one
        try:
            if self._upload_paths:
                return self._upload_paths
        except AttributeError:
            pass
        # keep backward compatibility
        single = self.getUploadFilePath()
        return [single] if single else []

    # def setFileAnnotations(self, annotations: dict[str,str]):
    #     self.annotations = annotations
        
    # def getFileAnnotations(self) -> Optional[dict[str,str]]:
    #     return self.annotations

    def hasAttachmentFile(self) -> bool:
        return hasattr(self, 'dictFileExtension') and self.dictFileExtension == "xml"
    
    def getAttachmentFile(self) -> Optional[str]:
        if self.hasAttachmentFile():
            return self.getDictFileTempPath()
        else:
            return None

    def getUploadFilePath(self) -> str:
        if self.hasConvertedFileName():
            return self.getConvertedFilePath()

        return self.getMainFileTempPath()

    def hasConvertedFileName(self):
        return hasattr(self, 'convertedFileName')
    
    def getConvertedFilePath(self):
        return self.basePath + "/" + self.getConvertedFileName()
    
    def setConvertedFileName(self, convertedName):
        self.convertedFileName = convertedName
        
    def getConvertedFileName(self):
        return self.convertedFileName

    def renameFile(self, newName: str):
        
        pathToRename = self.tempPaths[0]        
        if self.hasConvertedFileName():
            pathToRename = self.basePath + "/" + self.getConvertedFileName()
            self.setConvertedFileName(newName)

        os.rename(pathToRename, self.basePath + "/" + newName) 

    def setFileSizes(self, sizes):
        self.fileSizes = sizes
        
    def getFileSizes(self):
        return self.fileSizes

    def getNrOfFiles(self):
        return len(self.originalFileNames)
    
    def getTotalFileSize(self):
        tot = 0
        for s in self.fileSizes:
            tot += int(s)
            
        return tot
    
