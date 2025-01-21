from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Blueprint,g
from omero_connection import OmeroConnection
import config

conn_bp = Blueprint('conn_bp',__name__,url_prefix='/')

@conn_bp.before_request
def connect_to_omero():
    
    token = session.get(config.OMERO_SESSION_TOKEN_KEY)
    host = session.get(config.OMERO_SESSION_HOST_KEY)
    port = session.get(config.OMERO_SESSION_PORT_KEY)

    if not hasattr(g,config.OMERO_G_CONNECTION_KEY) or getattr(g,config.OMERO_G_CONNECTION_KEY) is None:
        setattr(g,config.OMERO_G_CONNECTION_KEY,OmeroConnection(host,port,token))

@conn_bp.after_request
def dissconnect_from_omero(response):

    if hasattr(g,config.OMERO_G_CONNECTION_KEY) or getattr(g,config.OMERO_G_CONNECTION_KEY) is not None:
        conn = getattr(g,config.OMERO_G_CONNECTION_KEY)
        del conn
        setattr(g, config.OMERO_G_CONNECTION_KEY, None)
        return response
        
    
    
