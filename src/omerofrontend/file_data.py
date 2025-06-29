import os
from typing import Optional
from threading import Lock

class FileData:
    
    
    #TODO: Implement constructor that takes filestoreage instead in order to be able to use FileData in futures context map
    
    def __init__(self,fileBaseNames):
        self.originalFileNames = []
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
        
    def setTempFilePaths(self,paths):
        self.tempPaths = paths
        self.basePath = os.path.dirname(paths[0])
        
    def getTempFilePaths(self) -> str:
        return self.tempPaths

    def getBasePath(self):
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
    
    def getUserName(self):
        return self.username
    
    def setFileAnnotations(self, annotations: dict[str,str]):
        self.annotations = annotations
        
    def getFileAnnotations(self) -> Optional[dict[str,str]]:
        return self.annotations

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

        os.rename(pathToRename, newName) 

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
    

class FileSet:
    
    def __init__(self, proj_name, dataset_name):
        self._mutex = Lock()
        self.files : list[FileData] = []
        self.proj_name = proj_name
        self.dataset_name = dataset_name
        
    def add_file(self,file: FileData):
        with self._mutex:
            self.files.append(file)
        
    def get_files(self) -> list[FileData]:
        return self.files
        
        
class FileSetManager:
    
    #def __init__(self):
    _mutex = Lock()
    filesets: dict[str, FileSet] = {}
        
    @classmethod
    def _construct_dict_string(cls, project_name: str, dataset_name: str):
        return project_name + "_" + dataset_name
            
    @classmethod
    def get_fileset(cls, project_name: str, dataset_name: str):
        with cls._mutex:
            dict_str = cls._construct_dict_string(project_name,dataset_name)
            if dict_str in cls.filesets:
                fs = cls.filesets[dict_str]
            else:
                fs = FileSet(project_name, dataset_name)
                cls.filesets[dict_str] = fs
                
        return fs
    
    @classmethod
    def add_file_to_fileset(cls, file: FileData, project_name: str, dataset_name: str):
        fs = cls.get_fileset(project_name, dataset_name)
        fs.add_file(file)
        
    @classmethod
    def get_filesets(cls) -> dict[str, FileSet]:
        return cls.filesets