import traceback
from flask import request, session, jsonify, Blueprint,g
from common.omero_connection import OmeroConnection
from common import conf
from common import logger
from common.omero_getter_ctx import OmeroGetterCtx

conn_bp = Blueprint('conn_bp',__name__,url_prefix='/')

@conn_bp.before_request
def connect_to_omero():
    
    token = session.get(conf.OMERO_SESSION_TOKEN_KEY)
    host = session.get(conf.OMERO_SESSION_HOST_KEY)
    port = session.get(conf.OMERO_SESSION_PORT_KEY)

    if not token or not host or not port:
        errStr = "No OMERO session token, host or port found in session. Please log in again."
        logger.error(errStr)
        raise ConnectionError(errStr)

    if not hasattr(g,conf.OMERO_G_CONNECTION_KEY) or getattr(g,conf.OMERO_G_CONNECTION_KEY) is None:
        connection = OmeroConnection(host,port,token)
        setattr(g,conf.OMERO_G_CONNECTION_KEY,connection)
            

@conn_bp.after_request
def dissconnect_from_omero(response):
    
    if hasattr(g,conf.OMERO_G_CONNECTION_KEY) and getattr(g,conf.OMERO_G_CONNECTION_KEY) is not None:
        conn = getattr(g,conf.OMERO_G_CONNECTION_KEY)
        del conn
        setattr(g, conf.OMERO_G_CONNECTION_KEY, None)

    return response

@conn_bp.errorhandler(413)
def handle_connection_413_e(e):
    logger.error(str(e))
    return jsonify(error=str(e)), 413


@conn_bp.errorhandler(500)
def handle_connection_error_e(e):
    logger.error(str(e))
    return jsonify(error=str(e)), 500


@conn_bp.errorhandler(ConnectionError)
def handle_connection_error(e):
    errStr = str(e) + ". Is your OMERO session token still valid?"
    logger.error(f"Connection error occured: {errStr}")
    return jsonify({
        "error": "Connection Error",
        "message": errStr,
        "status": 500
        }), 500


@conn_bp.errorhandler(Exception)
def handle_exception_error(e):
    errStr = str(e)
    logger.error(f"General Exception Error:{errStr} \n Trace:  {traceback.format_exc()}")
    return jsonify({
        "error": "General Error",
        "message": errStr,
        "status": 500
        }), 500


@conn_bp.route('/get_existing_tags', methods=['GET'])
def get_existing_tags():
    """
    Fetch all tags (keys and their values) from OMERO.
    """
    logger.info("Fetching tags from OMERO.")
    try:
        conn: OmeroConnection = getattr(g, conf.OMERO_G_CONNECTION_KEY)
        keys_and_values = {}
        
        # Fetch all keys from the OMERO server
        all_keys = conf.USER_VARIABLES
        for key in all_keys:
            with OmeroGetterCtx(conn) as ogc:
                values = ogc.get_tags_by_key(key)
                keys_and_values[key] = values
        
        return jsonify(keys_and_values)
    except Exception as e:
        logger.error(f"Error fetching keys and tags: {str(e)}")
        return jsonify({"error": str(e)}), 500

@conn_bp.route('/get_default_group', methods=['GET'])
def get_default_group():
    """Fetch the default group of the user"""
    try:
        conn: OmeroConnection = getattr(g, conf.OMERO_G_CONNECTION_KEY)
        group = conn.get_default_omero_group()
        logger.info(f"Default group is: {str(group)}")
        return jsonify(group)
        #function here
    except Exception as e:
        logger.error(f"Error fetching the default group: {str(e)}")
        return jsonify({"error": str(e)}), 500        

@conn_bp.route('/get_existing_groups', methods=['GET'])
def get_existing_groups():
    """
    Fetch groups
    """
    logger.info("Fetching groups from OMERO.")
    try:
        conn: OmeroConnection = getattr(g, conf.OMERO_G_CONNECTION_KEY)        
        return jsonify(conn.get_user_groups())
    except Exception as e:
        logger.error(f"Error fetching group: {str(e)}")
        return jsonify({"error": str(e)}), 500

@conn_bp.route('/set_group', methods=['POST'])
def set_group():
    try:
        data = request.get_json()
        group = data.get('group')
        if not group:
            logger.error("No 'group' key found in JSON.")
            return jsonify({"error": "No group provided"}), 400
        conn: OmeroConnection = getattr(g, conf.OMERO_G_CONNECTION_KEY)
        try:
            conn.set_group_name_for_session(group)
        except Exception as e:
            logger.error("Error setting group in OMERO!")
            return jsonify({"error": str(e)}), 500  # Return error message

        return jsonify({"message": f"Group set to {group}"}), 200

    except Exception as e:
        logger.error("Unexpected error occurred!")
        return jsonify({"error": str(e)}), 500

