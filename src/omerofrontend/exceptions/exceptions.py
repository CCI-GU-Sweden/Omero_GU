

class OmeroFrontendException(Exception):
 
    """Base class for CCI omer ui exceptions"""
    def __init__(self, filename=None, message="Exception in program"):
        if filename:
            message = f"{message}: {filename}"
        super().__init__(message)
        self.filename = filename

class OmeroConnectionError(OmeroFrontendException):
    """Exception raised when the connection to OMERO server could not be established"""
    def __init__(self, message="Connection to OMERO server could not be established"):
        super().__init__(message)

class ImageNotSupported(OmeroFrontendException):
    """Exception raised when a file type or format is not supported."""
    def __init__(self, filename=None, message="File type is not supported"):
        super().__init__(filename, message)

class GeneralError(OmeroFrontendException):
    """Exception raised when an error not covered by other exceptions is generated"""
    def __init__(self, filename=None, message="General error"):
        super().__init__(filename, message)

class DuplicateFileExists(OmeroFrontendException):
    """Exception raised when the file already exists in the dataset. Dupliucate is same name and same acquisition time"""
    def __init__(self, filename=None, message="Duplicate file exists"):
        super().__init__(filename, message)

class MetaDataError(OmeroFrontendException):
    """Exception raised when some of the metadata could not be read, is missing or strange value"""
    def __init__(self, filename=None, message="Metadata could not be read"):
        super().__init__(filename, message)
        
class AssertImportError(OmeroFrontendException):
    """Exception raised when the import assertion fails"""
    def __init__(self, filename=None, message="Import assertion failed"):
        super().__init__(filename, message) 
        
class ImportError(OmeroFrontendException):
    """Exception raised when the import fails"""
    def __init__(self, filename=None, message="Import failed"):
        super().__init__(filename, message)
        
class OutOfDiskError(OmeroFrontendException):
    """Exception raised when temporary storage fails"""
    def __init__(self, filename=None, filepath : str = "", message="No space left on disk!"):
        super().__init__(filename, message)
        self.filepath : str = filepath