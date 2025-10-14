import os
from threading import Lock
import redis
import json
from redis.exceptions import ConnectionError, TimeoutError, AuthenticationError, ResponseError
from common import conf

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
    
    #_msg_q = Queue()
    #_lock = Lock()
    _id_lock = Lock()
    _id_cntr : int = -1
    
    #use this only for testing
    USE_FAKE_REDIS = os.getenv("USE_FAKE_REDIS") == "1"
    if USE_FAKE_REDIS:
        import fakeredis
        r = fakeredis.FakeRedis(decode_responses=False)
    else:
        r = redis.Redis.from_url(conf.REDIS_URL)
    
    
    @classmethod
    def assert_redis_up(cls):
        try:
            return cls.r.ping()  # -> True (PONG) on success
        except AuthenticationError as e:
            raise RuntimeError("Redis auth failed (bad password or ACL).") from e
        except (ConnectionError, TimeoutError) as e:
            host = cls.r.connection_pool.connection_kwargs.get("host")
            port = cls.r.connection_pool.connection_kwargs.get("port")
            raise RuntimeError(f"Redis unreachable at {host}:{port}.") from e
        except ResponseError as e:
            # e.g., NOAUTH if password missing when server requires it
            raise

    
    @classmethod
    #def publish_import_update(cls, event_type: str, payload: dict, *, maxlen=10000):
    def publish_import_update(cls, event, *, maxlen=10000):
        """
            Writes an event to the Redis Stream consumed by /import_updates.
            - event_type: maps to SSE 'event:' line
            - payload: dict that will be JSON-encoded and sent as 'data:'
        """
        
        evt_type = event['type']
        data = event['data']
        
        return cls.r.xadd(
            conf.RQ_QUEUE_NAME,
            {"type": evt_type, "data": json.dumps(data)},
            maxlen=maxlen,
            approximate=True,  # ~ trimming for performance
        )
    
    @classmethod
    def read_import_updates(cls, last_id: str = "$", *, block_ms=30000, count=100):
        """
            Reads events from the Redis Stream consumed by /import_updates.
            - last_id: last ID received; use "$" to get only new events
            - block_ms: how long to block waiting for new events (ms)
            - count: max number of events to return at once
            Returns a list of (id, fields) tuples, where fields is a dict.
        """
        items = cls.r.xread({conf.RQ_QUEUE_NAME: last_id}, block=block_ms, count=count)
        if not items:
            return []
        _, entries = items[0] # pyright: ignore[reportIndexIssue]
        return entries  # list of (id, fields) tuples
    
    @classmethod
    def send_started_event(cls,fileName):
        cls._create_and_put_event(fileName,STARTED,"Starting upload to omero...")
       
    @classmethod
    def send_unsupported_event(cls,fileName, msg = ""):
        cls._create_and_put_event(fileName,UNSUPPORTED_FORMAT,f" {msg}")

    @classmethod
    def send_staging_event(cls,fileName, msg=""):
        cls._create_and_put_event(fileName,STAGING,msg)

    @classmethod
    def send_progress_event(cls,fileName,progress):
        cls._create_and_put_event(fileName,PROGRESS,"Upploading to Omero: " + str(progress) + "%")

    @classmethod
    def send_importing_event(cls,fileName):
        cls._create_and_put_event(fileName,IMPORTING,"")

    @classmethod
    def send_success_event(cls,fileName, path, imageId):
        msg = f"Image id: {imageId}, stored at {path}"
        cls._create_and_put_event(fileName,SUCCESS,msg)

    @classmethod
    def send_duplicate_event(cls,fileName):
        cls._create_and_put_event(fileName,DUPLICATE,"File already in current group")
    
    @classmethod
    def send_error_event(cls,fileName,message):
        cls._create_and_put_event(fileName,ERROR,message)
        
    @classmethod
    def send_retry_event(cls, filename, retry, maxTries):
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
        events = cls.read_import_updates()
        return events
        
    @classmethod
    def putEvent(cls,event):
        cls.publish_import_update(event)
    