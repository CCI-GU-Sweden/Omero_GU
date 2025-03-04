# -*- coding: utf-8 -*-
"""
Created on Fri Nov 15 15:09:51 2024

@author: simon



local web server: http://127.0.0.1:5000/

"""
from flask import Flask, render_template, request, redirect, url_for, session, jsonify,g,Response, send_from_directory
from connection_blueprint import conn_bp, connect_to_omero
import mistune
import os
import database
import omero_funcs
import conf
import logger
import json
import file_importer
import queue

processed_files = {} # In-memory storage for processed files (for the session)

def create_app(test_config=None):

    app = Flask(conf.APP_NAME)
    app.secret_key = conf.SECRET_KEY

    logger.setup_logger()

    # Define a directory for storing uploaded files
    UPLOAD_FOLDER = 'uploads'
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    logger.info("***** Starting CCI Omero Frontend ******")
    importer = file_importer.FileImporter()
    
    if conf.DB_HANDLER == "sqlite":
        db = database.SqliteDatabaseHandler()
        logger.info("Using SQLite database... (is this a local instance?)")
        
    else:
        db = database.PostgresDatabaseHandler()
        logger.info("Using postgres database")
    
    db.initialize_database()
    importer.setDatabaseHandler(db)
    
    #Flask function
    @app.route('/') #Initial
    def index():
        logger.info("Enter index.html")
        return render_template('index.html')
    
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
        return render_template('help_page.html', content=html)
        
    @app.route('/login')
    def login():
        logger.info("Enter login.html")
        return redirect(conf.OMERO_LOGIN_URL)

    @app.route('/enter_token', methods=['GET', 'POST'])
    def enter_token():
        logger.info("Enter enter_token.html")
        if request.method == 'POST':
            session_token = request.form.get('session_token')
            logger.info("Session Uuid is: " + session_token)
            if session_token:
                session[conf.OMERO_SESSION_TOKEN_KEY] = session_token
                session[conf.OMERO_SESSION_HOST_KEY] = conf.OMERO_HOST
                session[conf.OMERO_SESSION_PORT_KEY] = conf.OMERO_PORT

                return redirect(url_for('upload'))
    
        return render_template('enter_token.html')

    def hasLoggedIn(session):
        return conf.OMERO_SESSION_TOKEN_KEY in session or conf.OMERO_SESSION_HOST_KEY in session
            
    @app.route('/upload')
    def upload():
        logger.info("Enter upload")
        if not hasLoggedIn(session):
            return redirect(url_for('enter_token'))
        return render_template('upload.html')

    @app.errorhandler(Exception)
    def handle_exception_error(e):
        return jsonify({
            "error": "Connection Error",
            "message": str(e),
            "status": 500
            }), 500
    
    @conn_bp.route('/import_images', methods=['POST'])
    def import_images():
        logger.info("Enter import_images")
        if not hasLoggedIn(session):
            return jsonify({"error": "Not logged in"}), 401
               
        conn = getattr(g,conf.OMERO_G_CONNECTION_KEY)
            
        try:
            # Retrieve the key-value pairs from the form data
            key_value_pairs = request.form.get('keyValuePairs')
            
            # Parse the JSON string into a Python dictionary or list
            if key_value_pairs:
                key_value_pairs = json.loads(key_value_pairs)
            else:
                return jsonify({"error": "No keyValuePairs found in the request"}), 400
    
            # Example: Print key-value pairs or process them further
            logger.info(f"Received key-value pairs: {key_value_pairs}")
    
            # Assuming you want to handle key-value pairs (this is a placeholder logic)
            batch_tag = {}
            for pair in key_value_pairs:
                key = pair.get("key")
                value = pair.get("value", "None")  # Default to "None" if no value is provided
                batch_tag[key] = value.strip()

        except Exception as e:
            return jsonify({"error": str(e)}), 500 #may want to just continue?
    
        files = request.files.getlist('files')
        logger.info(f"Received file: {files}")
        
        res = importer.startImport(files,batch_tag,conn)
        
        if res:
            return jsonify({"status":"Ok"})
        else:
            return jsonify({"status":"Failed"})
            
    @app.route('/get_projects', methods=['POST'])
    def get_projects():

        conn = omero_funcs.get_omero_connection()
        projects = omero_funcs.get_user_projects(conn)

        return jsonify(projects)        
    
    @app.route('/create_project', methods=['POST'])
    def create_project():
        
        conn = omero_funcs.get_omero_connection()
        projects = omero_funcs.create_project(conn, request.projectName)

        return jsonify(projects)        
    
    @app.route('/supported_file_formats', methods=['POST','GET'])
    def supported_formats():
        return jsonify({"folder_formats" : conf.ALLOWED_FOLDER_FILE_EXT,
                        "single_formats" : conf.ALLOWED_SINGLE_FILE_EXT})
    
    @app.route("/error_page", methods=['POST','GET'])
    def error_page():
        err_type = request.args.get('error_type')
        err_msg = request.args.get('message')
        return render_template('error_page.html',error_type=err_type, error_message=err_msg)
    
    @app.route('/log', methods=['POST'])
    def log():
        if request.is_json:
            data = request.json
            level = data.get('level')
            msg = data.get('message')
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
        conn = getattr(g,conf.OMERO_G_CONNECTION_KEY)
        conn.kill_session()
        return redirect(url_for('index'))
   
    @app.route('/build_info', methods=['GET'])
    def build_info():
        html = "<html><body><h3>Build Info</h3><br>"
        if not "OPENSHIFT_BUILD_NAME" in os.environ:
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

    @app.route('/import_updates')
    def import_updates_stream():
        def generate():
            yield "retry: 1000\n"
            try:
                while True:
                    try:
                        event = importer.getEvent(2)
                        yield f"data: {json.dumps(event)}\n\n"
                    except queue.Empty as ee:
                        yield f"keep alive\n"
                    except ConnectionError as e:
                        logger.warning(f"Connection error in import_updates {str(e)}")
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                        break
            except GeneratorExit:
                logger.warning("client disconnected in import_updates")
        
        #should check for ConnectinError exception!!!
        return Response(generate(), mimetype='text/event-stream')

    app.register_blueprint(conn_bp)
    return app

#%%main
if __name__ == '__main__': #standalone
    app = create_app()
    app.run(debug=True)