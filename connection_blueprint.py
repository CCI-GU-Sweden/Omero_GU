from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Blueprint,g
from omero_connection import OmeroConnection
import conf, logger

conn_bp = Blueprint('conn_bp',__name__,url_prefix='/')

@conn_bp.before_request
def connect_to_omero():
    
    token = session.get(conf.OMERO_SESSION_TOKEN_KEY)
    host = session.get(conf.OMERO_SESSION_HOST_KEY)
    port = session.get(conf.OMERO_SESSION_PORT_KEY)

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

@conn_bp.errorhandler(500)
def handle_connection_error(e):
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


@conn_bp.route('/get_existing_tags', methods=['GET'])
def get_existing_tags():
    """
    Fetch all tags (keys and their values) from OMERO.
    """
    logger.info("Fetching tags from OMERO.")
    try:
        conn = getattr(g, conf.OMERO_G_CONNECTION_KEY)
        keys_and_values = {}
        
        # Fetch all keys from the OMERO server
        all_keys = conf.USER_VARIABLES
        for key in all_keys:
            values = conn.get_tags_by_key(key)
            keys_and_values[key] = values
        
        return jsonify(keys_and_values)
    except Exception as e:
        logger.error(f"Error fetching keys and tags: {str(e)}")
        return jsonify({"error": str(e)}), 500

    
