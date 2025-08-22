from multiprocessing import Queue
#from omerofrontend import logger
from threading import Lock

#make sure these match javascript versions of same "structs"
PENDING = "pending"
STAGING = "staging"
STARTED = "started"
PROGRESS = "progress"
IMPORTING = "importing"
SUCCESS = "success"

UNSUPPORTED_FORMAT = "unsupported_format"
DUPLICATE = "duplicate"
UNMATCHED = "unmatched"
ERROR = "error"

class ServerEventManager:
    
    _msg_q = Queue()
    _lock = Lock()
    _id_lock = Lock()
    _id_cntr : int = -1
    
    @classmethod
    def send_started_event(cls,fileName):
        with cls._lock:
            cls._create_and_put_event(fileName,STARTED,"Starting upload to omero...")
       
    @classmethod
    def send_unsupported_event(cls,fileName, msg = ""):
        with cls._lock:
            cls._create_and_put_event(fileName,UNSUPPORTED_FORMAT,f" {msg}")

    @classmethod
    def send_staging_event(cls,fileName, msg=""):
        with cls._lock:
            cls._create_and_put_event(fileName,STAGING,msg)

    @classmethod
    def send_progress_event(cls,fileName,progress):
        with cls._lock:
            cls._create_and_put_event(fileName,PROGRESS,"Upploading to Omero: " + str(progress) + "%")

    @classmethod
    def send_importing_event(cls,fileName):
        with cls._lock:
            cls._create_and_put_event(fileName,IMPORTING,"")

    @classmethod
    def send_success_event(cls,fileName, path, imageId):
        with cls._lock:
            msg = f"Image id: {imageId}, stored at {path}"
            cls._create_and_put_event(fileName,SUCCESS,msg)

    @classmethod
    def send_duplicate_event(cls,fileName):
        with cls._lock:
            cls._create_and_put_event(fileName,DUPLICATE,"File already in current group")
    
    @classmethod
    def send_error_event(cls,fileName,message):
        with cls._lock:
            cls._create_and_put_event(fileName,ERROR,message)
        
    @classmethod
    def send_retry_event(cls, filename, retry, maxTries):
        with cls._lock:
            cls._create_and_put_event(filename,str(retry),str(maxTries),result="",type="retry_event")
    
    
    ###############################
    ## Do not use these methods directly, use the above ones instead
    ###############################
    
    @classmethod
    def _create_and_put_event(cls,fileName,status,message,result="", type="message"):
        event = cls._generateEvent(fileName,status,message,result, type=type)
        cls.putEvent(event)
    
    @classmethod
    def _get_next_id(cls):
        with cls._id_lock:
            cls._id_cntr += 1
            return cls._id_cntr
    
    @classmethod
    def _generateEvent(cls,fileName,status,message,result="", type="message"):
        
        event_data = { 
            
            "data" : { 
                "name" : fileName,
                "status" : status,
                "message" : message,
                "result" : result,
                },
            "type" : type,
            "id" : cls._get_next_id() 
            }
        
        return event_data
    
    @classmethod
    def getEvent(cls, timeout=None):
        #with cls._lock:
        event = cls._msg_q.get(timeout=timeout)
        #logger.debug(f"Getting event {event['id']} from queue")  
        return event
        
    @classmethod
    def putEvent(cls,event):
        #with cls._lock:
        cls._msg_q.put(event)
        #logger.debug(f"Putting event to queue {event['id']} in queue")  
    