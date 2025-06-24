

class OmeroFrontendException(Exception):
 
    """Base class for CCI omer ui exceptions"""
    def __init__(self, filename=None, message="Exception in program"):
        if filename:
            message = f"{message}: {filename}"
        super().__init__(message)
        self.filename = filename

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