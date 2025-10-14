#import traceback
from flask import request, Blueprint
#from .omero_connection import OmeroConnection
#from common import conf
from common import logger
# requirements: redis>=4
#import json, time
from omerofrontend.server_event_manager import ServerEventManager
import redis
from flask import Response, stream_with_context



sse_bp = Blueprint('sse_bp',__name__,url_prefix='/sse')


@sse_bp.route('/import_updates', methods=['GET'])
def import_updates_stream():
    @stream_with_context
    def generate():
        # Suggest a client retry backoff
        yield "retry: 1000\n\n"

        # Optional: disable uWSGI harakiri for this long-lived request
        try:
            import uwsgi  # type: ignore
            uwsgi.set_harakiri(0)
        except Exception:
            pass

        # Resume from the client's last seen event
        last = request.headers.get("Last-Event-ID")
        # "$" = only new items; if you want to replay history, start from "0-0"
        next_id = last or "$"

        last_heartbeat = time.time()

        try:
            while True:
                try:
                    # Block for new entries on the stream
                    
                    items = ServerEventManager.getEvent()
                    #items = r.xread({conf.RQ_QUEUE_NAME: next_id}, block=30000, count=100)
                    if items:
                        # items = [(stream_key, [(msg_id, fields), ...])]
                        # _, entries = items[0]
                        for msg_id, fields in items:
                            # Fields are bytes -> decode
                            etype = (fields.get(b"type") or b"message").decode()
                            raw_data = fields.get(b"data")
                            # If you stored JSON string in 'data', pass it through; else dump it.
                            if isinstance(raw_data, (bytes, bytearray)):
                                data_str = raw_data.decode()
                            else:
                                data_str = json.dumps(raw_data)

                            # SSE frame
                            yield (
                                f"event: {etype}\n"
                                f"id: {msg_id}\n"
                                f"data: {data_str}\n\n"
                            )
                            next_id = msg_id
                        last_heartbeat = time.time()
                    else:
                        # No events within XREAD_BLOCK_MS → heartbeat if needed
                        if time.time() - last_heartbeat >= 15:
                            yield "event: keep_alive\ndata: \"keep_alive\"\n\n"
                            last_heartbeat = time.time()

                except redis.ConnectionError as e:
                    logger.warning(f"Redis connection error in import_updates: {e}")
                    yield f'event: error\ndata: {json.dumps({"error": "redis_connection_error"})}\n\n'
                    time.sleep(0.5)  # brief backoff before trying again

        except GeneratorExit:
            logger.warning("client disconnected in import_updates")

    # Important headers for SSE behind Nginx/uWSGI
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # prevents proxy buffering in Nginx
    }
    return Response(generate(), headers=headers)
