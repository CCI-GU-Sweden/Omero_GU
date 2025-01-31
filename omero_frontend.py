# -*- coding: utf-8 -*-
"""
Created on Fri Nov 15 15:09:51 2024

@author: simon



local web server: http://127.0.0.1:5000/

"""
from flask import Flask, render_template, request, redirect, url_for, session, jsonify,g
from connection_blueprint import conn_bp
import mistune
import os
from dateutil import parser
import datetime
import time
import database
import omero_funcs
import traceback
import conf
import logger
import image_funcs
import json

processed_files = {} # In-memory storage for processed files (for the session)

def create_app(test_config=None):

    app = Flask(conf.APP_NAME)
    app.secret_key = conf.SECRET_KEY

    logger.setup_logger()

    # Define a directory for storing uploaded files
    UPLOAD_FOLDER = 'uploads'
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    database.initialize_database()

    logger.info("***** Starting CCI Omero Frontend ******")

    #Flask function
    @app.route('/') #Initial
    def index():
        logger.info("Enter index.html")
        return render_template('index.html')
    
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

    @conn_bp.route('/import_images', methods=['POST'])
    def import_images():
        logger.info("Enter import_images")
        if not hasLoggedIn(session):
            return jsonify({"error": "Not logged in"}), 401
               
        import_time_start = time.time()
        
        try:
            conn = getattr(g,conf.OMERO_G_CONNECTION_KEY)
            batch_tag = {}
            
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
    
            
            files = request.files.getlist('files') #get the files to upload
            file_n = 0
            
            logger.info(f"Received files: {[file.filename for file in files]}")
            
            #pairs files for download
            files = image_funcs.pair_emi_ser(files)
            files = image_funcs.pair_mrc_xml(files)
            
            
            imported_files = []
            scopes = []
            total_file_size = 0
            # Create a temporary directory
            for item in files:
                file_paths = []
                if isinstance(item, dict):  # EMI/SER pair
                    if item.get('emi', None):
                        file_path, _ = image_funcs.store_temp_file(item['emi'])
                        t, file_size = image_funcs.store_temp_file(item['ser'])
                        filename = item['emi'].filename
                        #save both path
                        file_paths.append(file_path)
                        file_paths.append(t)
                        file_n += 1
                        
                    elif item.get('mrc', None):
                        file_path, _ = image_funcs.store_temp_file(item['xml'])
                        t, file_size = image_funcs.store_temp_file(item['mrc'])
                        filename = item['mrc'].filename
                        #save both path
                        file_paths.append(file_path)
                        file_paths.append(t)
                        file_path = {'xml':file_path,'mrc':t} #require a dict in this case
                        file_n += 1
                    
                else:   #CZI, EMD
                    filename = item.filename
                    _ , fext = os.path.splitext(filename)
                    
                    if not fext in conf.ALLOWED_FILE_EXT:
                        imported_files.append({
                                "name": os.path.basename(filename),
                                "status": "unsupported_format",
                                "message": "The file is not supported and will be skipped",
                                "path" : ""
                            })
                        continue
                    
                    file_path, file_size = image_funcs.store_temp_file(item)
                    file_n += 1

                total_file_size += file_size
                                
                try:
                    logger.info(f"Processing of {file_path}")
                    #Spliter functions required here for multiple file format support
                    file_path, meta_dict = image_funcs.file_format_splitter(file_path, verbose=True)
                    file_paths.append(file_path)
                    meta_dict = meta_dict | batch_tag #merge the batch tag to the meta_dictionnary
                    folder = os.path.basename(os.path.dirname(filename))
                    if folder != '': meta_dict['Folder'] = folder
                    logger.info(f"Metadata successfully extracted from {filename}")

                    scopes.append([meta_dict['Microscope']])
                    project_name = meta_dict['Microscope']
                    acquisition_date_time = parser.parse(meta_dict['Acquisition date'])
                    dataset_name = acquisition_date_time.strftime("%Y-%m-%d")
                    
                    # Get or create project and dataset
                    projID = conn.get_or_create_project(project_name)
                    dataID = conn.get_or_create_dataset(projID, dataset_name)
                    
                    logger.info(f"Check ProjectID: {projID}, DatasetID: {dataID}")
                    
                    # Check if image is already in the dataset and has the acquisition time
                    dataset = conn.getDataset(dataID)
                    file_exists = False
                    
                    dup, childId =  omero_funcs.check_duplicate_filename(conn,filename,dataset)
                    if dup:
                        sameTime = conn.compareImageAcquisitionTime(childId,acquisition_date_time)
                        if not sameTime: #same name but different acquisition times, rename the imported file 
                            acq_time = acquisition_date_time.strftime("%H-%M-%S")
                            new_name = ''.join(file_path.split('.')[:-1]+['_', acq_time,'.',file_path.split('.')[-1]])   
                            os.rename(file_path, new_name)
                            logger.info(f'Rename {file_path} to {new_name} in order to avoid name duplication')
                            file_path = new_name
                        else: #same file, a duplicate
                            file_exists = True
                    
                    if file_exists:
                        logger.info(f'{filename} already exists, skip.')
                        processed_files[filename] = 'duplicate'
                        imported_files.append({"name": os.path.basename(filename),
                                            "status": "duplicate",
                                            "message": "File already exists",
                                            "path":''
                                            })

                    else:
                        #import the file
                        logger.info(f'Importing {filename}.')
                        user = conn.get_logged_in_user_name()
                        index = user.find('@')
                        user_name = user[:index] if index != -1 else user
                        
                        dst_path = f'{user_name} / {project_name} / {dataset_name}'
                        image_id = omero_funcs.import_image(conn.get_omero_connection(), file_path, dataset, meta_dict, batch_tag)
                        processed_files[filename] = 'success'
                        logger.info(f"ezimport result for {filename}: {image_id}, path: {dst_path}")
                        
                        imported_files.append({
                            "name": os.path.basename(filename),
                            "status": "success",
                            "message": f"Successfully imported as Image ID: {image_id}",
                            "path" : f'{dst_path}'
                        })

                except Exception as e:
                    logger.error(f"Error during import of {filename}: {str(e)}, line: {traceback.format_exc()}")
                    processed_files[filename] = 'error'
                    imported_files.append({
                        "name": os.path.basename(filename),
                        "status": "error",
                        "message": str(e),
                        "path":''
                    })
                
                finally: #in any case, delete the whole content of the upload folder                    
                    for file in file_paths:
                        if os.path.exists(file):
                            os.remove(file)
                    logger.info(f"Deleting the temporary file(s): {file_paths}")
            
            # Only add an entry in the database (and log) if at least one transfer is successfull!
            if any(x["status"] == 'success' for x in imported_files):
                scope = None
                import_time = time.time() - import_time_start
                if len(scopes) > 0:
                    scope = sorted(scopes, key=scopes.count, reverse=True)[0] #take only one scope
                    if isinstance(scope, list):
                        if len(scope) > 0:
                            scope = scope[0]
    
                logger.info("Import done")
                
                #get some data
                user = conn.get_user()
                time_stamp = datetime.datetime.today().strftime('%Y-%m-%d')
                username = user.getFullName()
                group = conn.get_omero_connection().getGroupFromContext()
                groupname = group.getName()
    
                # security:
                groupname = str(groupname) if groupname else "Unknown Group"
                username = str(username) if username else "Unknown User"
                scope = str(scope) if scope else "Unknown Scope"
                file_n = int(file_n) if file_n else 0
                total_file_size = float(total_file_size) if total_file_size else 0.0
                import_time = float(import_time) if import_time else 0.0
                
                #show the data in the log
                logger.info('User information:')
                logger.info(f"    Time: {time_stamp}")
                logger.info(f"    Full Name: {username}")
                logger.info(f"    Current group: {groupname}")
                logger.info(f"    Main microscope: {scope}")
                logger.info(f"    File number: {file_n}")
                logger.info(f"    File total size (MB): {total_file_size /1024 / 1024}")
                logger.info(f"    Import time (s): {import_time}")
                logger.info("")
                
                # Insert data into the database
                database.insert_import_data(
                    time=time_stamp,
                    username=username,
                    groupname=groupname,
                    scope=scope,
                    file_count=file_n,
                    total_file_size_mb=total_file_size / 1024 / 1024,
                    import_time_s=import_time
                )
            
            else:
                logger.info("Import failed")
            
            
            return jsonify({"files": imported_files})
        
        except Exception as e:
            logger.error(f"Error during import process: {str(e)}")
            return jsonify({"error": str(e)}), 500
            
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
             
        html += "</body></html>"
        return html

    app.register_blueprint(conn_bp)
    return app

#%%main
if __name__ == '__main__': #standalone
    app = create_app()
    app.run(debug=True)