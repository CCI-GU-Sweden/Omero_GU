# -*- coding: utf-8 -*-
import mistune
import os
import json
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify,g, send_from_directory
from flask_cors import CORS
from werkzeug import Request
from omerofrontend import database
from common import conf
from common import logger
from omerofrontend.middle_ware import MiddleWare
from common import omero_connection
from omerofrontend.connection_blueprint import conn_bp, connect_to_omero
from omerofrontend.sse_blueprint import sse_bp
from omerofrontend.server_event_manager import ServerEventManager

#processed_files = {} # In-memory storage for processed files (for the session)

def create_app(test_config=None):
    
    Request.max_form_parts = 5000
    app = Flask(conf.APP_NAME)
    app.secret_key = conf.SECRET_KEY
    CORS(app)

    logger.setup_logger(conf.LOG_LEVEL)

    try:
        os.makedirs(conf.IMPORT_PROGRESS_DIR, exist_ok=True)
    except Exception:
        logger.error("Error in creating dir...exiting")
        return
    
    logger.info(f"***** Starting CCI Omero Frontend at {datetime.datetime.now() }******")
    
    if conf.DB_HANDLER == "sqlite":
        db = database.SqliteDatabaseHandler()
        logger.info("Using SQLite database... (is this a local instance?)")
        
    else:
        db = database.PostgresDatabaseHandler()
        logger.info("Using postgres database")
    
    ServerEventManager.assert_redis_up()
    db.initialize_database()
    middle_ware = MiddleWare(db)

    def my_render_template(*args, **kwargs):
        
        kwargs['is_test_instance'] = conf.USE_TEST_URL
        return render_template(*args,**kwargs)
    
    #Flask function
    @app.route('/') #Initial
    def index():
        logger.info("Enter index.html")
        return my_render_template('index.html')
    
    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')
    
    @app.route('/help')
    def help_page():
        logger.info("Enter help_page.html")
        markdown = mistune.create_markdown(escape=False)
        
        # Adjust the path as needed
        md_path = os.path.join(conf.STATIC_FOLDER, 'help.md')
        
        with open(md_path, 'r') as file:
            content = file.read()
        
        # Replace relative image paths with url_for
        content = content.replace('images/', url_for('static', filename='images/'))
        
        html = markdown(content)
        return my_render_template('help_page.html', content=html)
        
    @app.route('/login')
    def login():
        logger.info("Enter login.html")
        return redirect(conf.OMERO_LOGIN_URL)

    @app.route('/enter_token', methods=['GET', 'POST'])
    def enter_token():
        logger.info("Enter enter_token.html")
        if request.method == 'POST':
            session_token = request.form.get('session_token')
            logger.info(f"Session Uuid is: {session_token}")
            if session_token:
                session[conf.OMERO_SESSION_TOKEN_KEY] = session_token
                session[conf.OMERO_SESSION_HOST_KEY] = conf.OMERO_HOST
                session[conf.OMERO_SESSION_PORT_KEY] = conf.OMERO_PORT

                return redirect(url_for('upload'))
    
        return my_render_template('enter_token.html')

    def hasLoggedIn(session):
        return conf.OMERO_SESSION_TOKEN_KEY in session or conf.OMERO_SESSION_HOST_KEY in session
            
    @app.route('/upload')
    def upload():
        logger.info("Enter upload")
        if not hasLoggedIn(session):
            return redirect(url_for('enter_token'))
        return my_render_template('upload.html')

    @app.errorhandler(Exception)
    def handle_exception_error(e):
        return jsonify({
            "error": "Connection Error",
            "message": str(e),
            "status": 500
            }), 500

    @conn_bp.route('/import_images', methods=['POST'])
    def import_images():

        logger.debug("Enter import_images")
        if not hasLoggedIn(session):
            return jsonify({"error": "Not logged in"}), 401
                
        conn = getattr(g,conf.OMERO_G_CONNECTION_KEY)

        logger.debug(f"Files: {len(request.files)}, Fields: {len(request.form)}")
        # Retrieve the key-value pairs from the form data
        key_value_pairs = request.form.get('keyValuePairs')
        # Parse the JSON string into a Python dictionary or list
        if key_value_pairs:
            key_value_pairs = json.loads(key_value_pairs)
        else:
            return jsonify({"error": "No keyValuePairs found in the request"}), 400

        logger.debug(f"Received key-value pairs: {key_value_pairs}")

        # Assuming you want to handle key-value pairs (this is a placeholder logic)
        batch_tag = {}
        for pair in key_value_pairs:
            key = pair.get("key")
            value = pair.get("value", "None")  # Default to "None" if no value is provided
            logger.debug(f"adding key-value {key} {value}")
            batch_tag[key] = value.strip()

        logger.debug("receiving files")
        files = request.files.getlist('files')
        token = session.get(conf.OMERO_SESSION_TOKEN_KEY)
        groupname = conn.getDefaultOmeroGroup()
        username = conn.get_logged_in_user_full_name()
        res, status = middle_ware.import_files(files,batch_tag,username,groupname,token)

        if res:
            return jsonify({"status":"Ok"})
        else:
            return jsonify({"status":status}), 507
            
    @app.route('/get_projects', methods=['POST'])
    def get_projects():

        conn = getattr(g,conf.OMERO_G_CONNECTION_KEY)
        projects = conn.get_user_projects()

        return jsonify(projects)        
    
    @app.route('/create_project', methods=['POST'])
    def create_project():
        
        conn = getattr(g,conf.OMERO_G_CONNECTION_KEY)
        projects = conn.create_project(request.projectName) # type: ignore #ignore: pyright[reportAttributeAccessIssue]

        return jsonify(projects)        
    
    @app.route('/supported_file_formats', methods=['POST','GET'])
    def supported_formats():
        return jsonify({"folder_formats" : conf.ALLOWED_FOLDER_FILE_EXT,
                        "single_formats" : conf.ALLOWED_SINGLE_FILE_EXT})
    
    @app.route("/error_page", methods=['POST','GET'])
    def error_page():
        err_type = request.args.get('error_type')
        err_msg = request.args.get('message')
        return my_render_template('error_page.html',error_type=err_type, error_message=err_msg)
    
    @app.route('/log', methods=['POST'])
    def log():
        if request.is_json:
            data = request.json
            level = data.get('level')# type: ignore #ignore: pyright[reportAttributeAccessIssue]
            msg = data.get('message')# type: ignore #ignore: pyright[reportAttributeAccessIssue]
            logger.log(level, f"Client-side log: {msg}")
            return jsonify({"status": "logged"})
        else:
            return 'content type not supported', 415
    
    @app.route('/log_error', methods=['POST'])
    def log_error():
        error_data = request.json
        # Process the error data (e.g., log it)
        logger.error(f"Client-side error: {error_data}")
        return jsonify({"status": "Error logged"})
      
            
    @app.route('/logout')
    def logout():
        logger.info("User logged out. Clearing session")

        connect_to_omero()
        session.clear()  # Clear the session
        conn: omero_connection.OmeroConnection = getattr(g,conf.OMERO_G_CONNECTION_KEY)
        username = conn.get_logged_in_user_full_name()
        middle_ware.remove_user_upload_dir(username)
        conn.kill_session()
        return my_render_template("logged_out.html")
   
    @app.route('/build_info', methods=['GET'])
    def build_info():
        html = "<html><body><h3>Build Info</h3><br>"
        if "OPENSHIFT_BUILD_NAME" not in os.environ:
            html += "using a local build"
        else:
            for name, value in os.environ.items():
                html += f"{name}: {value}<br>"
             
        html += "<br/>"
        html += "<h3>Omero Server URLS</h3>"
        html += f"USE_TEST_URL: {conf.USE_TEST_URL}<br/>"
        html += f"OMERO_HOST: {conf.OMERO_HOST}<br/>"
        html += f"OMERO_BASE_URL: {conf.OMERO_BASE_URL}<br/>"
        html += "</body></html>"
        return html

    # @app.route('/import_updates')
    # def import_updates_stream():
    #     @stream_with_context
    #     def generate():
    #         yield "retry: 1000\n\n"
    #         try:
    #             while True:
    #                 try:
    #                     event = middle_ware.get_ssevent(5)
    #                     event_id: int = event['id']
    #                     event_str = (
    #                         f"event: {event['type']}\n"
    #                         f"id: {str(event_id)}\n"
    #                         f"data: {json.dumps(event['data'])}\n\n"
    #                     )
    #                     #logger.debug(f"Sending event {event_str} to client")
    #                     yield event_str
    #                 except queue.Empty:
    #                     ka_string = (
    #                         f"event: keep_alive\n"
    #                         f"data: {json.dumps('keep_alive')}\n\n"
    #                     )
    #                     yield ka_string
    #                     #logger.debug("Sending keep alive")
    #                 except ConnectionError as e:
    #                     logger.warning(f"Connection error in import_updates {str(e)}")
    #                     yield f"data: {json.dumps({'error': str(e)})}\n\n"
    #                     break
    #         except GeneratorExit:
    #             logger.warning("client disconnected in import_updates")
        
    #     #should check for ConnectinError exception!!!
    #     headers = {
    #         'Content-Type': 'text/event-stream',
    #         'Cache-Control': 'no-cache'
    #     }
    #     return Response(generate(), headers=headers)# pyright: ignore[reportCallIssue]
        
    app.register_blueprint(conn_bp)
    app.register_blueprint(sse_bp)
    return app

#%%main
if __name__ == '__main__': #standalone
    app = create_app()
    if app is not None:
        app.run(debug=True)
