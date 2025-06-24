from multiprocessing import Queue

#make sure these match javascript versions of same "structs"
PENDING = "pending"
STARTED = "started"
UPLOADING = "uploading"
PROGRESS = "progress"
SUCCESS = "success"

UNSUPPORTED_FORMAT = "unsupported_format"
DUPLICATE = "duplicate"
UNMATCHED = "unmatched"
ERROR = "error"

class ServerEventManager:
    
    _msg_q = Queue()
    
    @classmethod
    def send_started_event(cls,fileName):
        event = cls._generateEvent(fileName,STARTED,"preparing file...")
        cls.putEvent(event)   
       
    @classmethod
    def send_unsupported_event(cls,fileName, msg = ""):
        event = cls._generateEvent(fileName,UNSUPPORTED_FORMAT,f" {msg}")
        cls.putEvent(event)   
        
    @classmethod
    def send_uploading_event(cls,fileName):
        event = cls._generateEvent(fileName,UPLOADING,"Uploading file")
        cls.putEvent(event)   

    @classmethod
    def send_progress_event(cls,fileName,progress):
        event = cls._generateEvent(fileName,PROGRESS,str(progress))
        cls.putEvent(event)   

    @classmethod
    def send_success_event(cls,fileName,path, imageId):
        msg = f"Image id: {imageId}, stored at {path}"
        event = cls._generateEvent(fileName,SUCCESS,msg)
        cls.putEvent(event)   

    @classmethod
    def send_duplicate_event(cls,fileName):
        event = cls._generateEvent(fileName,DUPLICATE,"File already in current group")
        cls.putEvent(event)   
    
    @classmethod
    def send_error_event(cls,fileName,message):
        event = cls._generateEvent(fileName,ERROR,message)
        cls.putEvent(event)   
        
    @classmethod
    def send_retry_event(cls, filename, retry, maxTries):
        cls._put_event(filename,str(retry),str(maxTries),result="",type="retry_event")
    
    @classmethod
    def _put_event(cls,fileName,status,message,result="", type="message"):
        event = cls._generateEvent(fileName,status,message,result, type=type)
        cls.putEvent(event)
    
    @classmethod
    def _generateEvent(cls,fileName,status,message,result="", type="message"):
        
        event_data = { 
            
            "data" : { 
                "name" : fileName,
                "status" : status,
                "message" : message,
                "result" : result 
                },
            "type" : type 
            }
        
        return event_data
    
    @classmethod
    def getEvent(cls, timeout=None):
        event = cls._msg_q.get(timeout=timeout)
        return event
        
    @classmethod
    def putEvent(cls,event):
        cls._msg_q.put(event)  
    