import os

class FileData:
    
    def __init__(self,files):
        self.originalFileNames = []
        for f in files:
            basename = os.path.basename(f.filename)
            self.originalFileNames.append(basename)
            ext = f.filename.split('.')[-1]
            if not ext == "ser" and not ext == "xml":
                self.mainFileExtension = ext
                self.mainFileName = basename
            else:
                self.dictFileExtension = ext
                self.dictFileName = basename
                        
    def getMainFileExtension(self):
        return self.mainFileExtension
        
    def getMainFileName(self):
        return self.mainFileName
        
    def getDictFileExtension(self):
        return self.dictFileExtension
    
    def getDictFileName(self):
        return self.dictFileName
        
    def setTempFilePaths(self,paths):
        self.tempPaths = paths
        self.basePath = os.path.dirname(paths[0])
        
    def getTempFilePaths(self):
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

    def setConvertedFileName(self, convertedName):
        self.convertedFileName = convertedName
        
    def getConvertedFileName(self):
        return self.convertedFileName

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
