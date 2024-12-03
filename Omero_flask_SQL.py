# -*- coding: utf-8 -*-
"""
Created on Fri Nov 15 15:09:51 2024

@author: simon


TODO: Better disconnect #maybe not possible. OAuth timeout may be better! Or log out button (IT side)
TODO: extract some stats (date, group name, (username), microscope, file number, file total size, time for transfer)

local web server: http://127.0.0.1:5000/

"""
#Flask import
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
#omero and image import
# import omero
# from omero.cli import CLI
# from omero.gateway import BlitzGateway
#import ezomero
#general import
import os
from dateutil import parser
import datetime
#image metadata import
from pylibCZIrw import czi as pyczi
#logging import
import logging #info, warning, error and critical
import database
import omero_funcs

import sys

import config

logger = logging.getLogger(config.APP_NAME)

processed_files = {} # In-memory storage for processed files (for the session)

def create_app(test_config=None):

    app = Flask(config.APP_NAME)
    app.secret_key = 'your_secret_key_here'  # Change this to a random secret key

    logging.basicConfig(filename='omero_app.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')
    logging.getLogger(config.APP_NAME).addHandler(logging.StreamHandler(sys.stdout))
    logger.info("________________________________________")
    logger.info("Starting CCI omero frontend!")

    # Define a directory for storing uploaded files
    UPLOAD_FOLDER = 'uploads'
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    database.initialize_database()

    #Flask function
    @app.route('/') #decorator!
    def index():
        logger.info("Enter index.html")
        return render_template('index.html')

    @app.route('/login')
    def login():
        logger.info("Enter login.html")
        return redirect(config.OMERO_LOGIN_URL)

    @app.route('/enter_token', methods=['GET', 'POST'])
    def enter_token():
        logger. info("Enter enter_token.html")
        if request.method == 'POST':
            session_token = request.form.get('session_token')
            logger. info("Session Uuid is:" + session_token)
            if session_token:
                hostname = '130.241.39.241'
                port = '4064'
                
                try:
                    session_key, omero_host = omero_funcs.connect_to_omero(hostname, port, session_token)
                    if session_key:
                        logger. info("Connection to the omero server successful")
                        session['omero_session_key'] = session_key
                        session['omero_host'] = omero_host
                        return redirect(url_for('upload'))
                    else:
                        return "Failed to connect to OMERO", 400
                except Exception as e:
                    return f"Error connecting to OMERO: {str(e)}", 400
        
        return render_template('enter_token.html')

    @app.route('/upload')
    def upload():
        logger. info("Enter upload")
        if 'omero_session_key' not in session or 'omero_host' not in session:
            return redirect(url_for('enter_token'))
        return render_template('upload.html')

    @app.route('/import_images', methods=['POST'])
    def import_images():
        import time
        logger. info("Enter import_images")
        if 'omero_session_key' not in session or 'omero_host' not in session:
            return jsonify({"error": "Not logged in"}), 401
        
        session_key = session['omero_session_key']
        host = session['omero_host']
        
        # Create a client using the session key
#        client = omero.clients.BaseClient(host)
#        client.joinSession(session_key)
        
        # Create a BlitzGateway connection using the client
#        conn = BlitzGateway(client_obj=client)  
        conn = omero_funcs.create_omero_connection(host,session_key)
        import_time_start = time.time()
        logger. info("Connection to the Omero server done")
        
        if not conn:
            return jsonify({"error": "Failed to connect to OMERO"}), 400

        try:
            files = request.files.getlist('files')
            file_n = len(files)
            
            logger. info(f"Received files: {[file.filename for file in files]}")
            imported_files = []
            scopes = []
            total_file_size = 0
            # Create a temporary directory
            for img in files:
                filename = img.filename
                # Create subdirectories if needed
                file_path = os.path.join(UPLOAD_FOLDER, *os.path.split(filename))
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                file_size = len(img.read())
                total_file_size += file_size
                img.seek(0)

                
                try:
                    # Save file to temporary directory
                    if file_size <= config.MAX_SIZE_FULL_UPLOAD: #direct save
                        logger. info(f"File {filename} is smaller than {config.MAX_SIZE_FULL_UPLOAD / (1024 * 1024)} MB. Full upload will be used.")
                        img.save(file_path) #one go save
                    else: #chunk save
                        logger. info(f"File {filename} is larger than {config.MAX_SIZE_FULL_UPLOAD / (1024 * 1024)} MB. Chunked upload will be used.")
                        with open(file_path, 'wb') as f:
                            while chunk := img.stream.read(config.CHUNK_SIZE):
                                f.write(chunk)
                    
                    # Read metadata from the file
                    meta_dict = get_info_metadata(file_path, verbose=False)
                    logger. info(f"Metadata successfully extracted for {filename}")
                    
                    scopes.append([meta_dict['Microscope']])
                    project_name = meta_dict['Microscope']
                    dataset_name = parser.parse(meta_dict['Creation date']).strftime("%Y-%m-%d")
                    
                    # Get or create project and dataset
                    projID = omero_funcs.get_or_create_project(conn, project_name)
                    dataID = omero_funcs.get_or_create_dataset(conn, projID, dataset_name)
                    
                    logger. info(f"Check ProjectID: {projID}, DatasetID: {dataID}")
                    
                    # Check if image is already in the dataset
                    dataset = conn.getObject("Dataset", dataID)
                    file_exists = any(child.getName().startswith(os.path.basename(filename)) for child in dataset.listChildren())
                    
                    if file_exists:
                        processed_files[filename] = 'duplicate'
                        imported_files.append({"name": os.path.basename(filename),
                                            "status": "duplicate",
                                            "message": "File already exists"
                                            })

                    else:
                        #import the file
                        image_id = omero_funcs.import_image(conn, file_path, dataID, meta_dict)
                        processed_files[filename] = 'success'
                        logger. info(f"ezimport result for {filename}: {image_id}")
                        
                        imported_files.append({
                            "name": os.path.basename(filename),
                            "status": "success",
                            "message": f"Successfully imported as Image ID: {image_id}"
                        })


                except Exception as e:
                    logger. error(f"Error during import of {filename}: {str(e)}")
                    processed_files[filename] = 'error'
                    imported_files.append({
                        "name": os.path.basename(filename),
                        "status": "error",
                        "message": str(e)
                    })
                
                finally:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger. info(f"Successfully deleted temporary file: {file_path}")
                    else:
                        logger. warning(f"Temporary file not found for deletion: {file_path}")
            
            import_time = time.time() - import_time_start
            scope = sorted(scopes, key=scopes.count, reverse=True)[0] #take only one scope
            if isinstance(scope, list):
                if len(scope) > 0:
                    scope = scope[0]
            

            logger. info("Import done")
            
            #get some data
            user = conn.getUser()
            time = datetime.datetime.today().strftime('%Y-%m-%d')
            username = user.getFullName()
            group = conn.getGroupFromContext()
            groupname = group.getName()

            # cleaning:
            groupname = str(groupname) if groupname else "Unknown Group"
            username = str(username) if username else "Unknown User"
            scope = str(scope) if scope else "Unknown Scope"
            file_n = int(file_n) if file_n else 0
            total_file_size = float(total_file_size) if total_file_size else 0.0
            import_time = float(import_time) if import_time else 0.0
            
            # Insert data into the database
            database.insert_import_data(
                time=time,
                username=username,
                groupname=groupname,
                scope=scope,
                file_count=file_n,
                total_file_size_mb=total_file_size / 1024 / 1024,
                import_time_s=import_time
            )

            #show the data in the log
            logger. info('User information:')
            logger. info(f"    Time: {time}")
            logger. info(f"    Full Name: {username}")
            logger. info(f"    Current group: {groupname}")
            logger. info(f"    Main microscope: {scope}")
            logger. info(f"    File number: {file_n}")
            logger. info(f"    File total size (MB): {total_file_size /1024 / 1024}")
            logger. info(f"    Import time (s): {import_time}")
            
            
            return jsonify({"files": imported_files})
        
        except Exception as e:
            logger. error(f"Error during import process: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/get_projects', methods=['POST'])
    def get_projects():
        
        session_key = session['omero_session_key']
        host = session['omero_host']
        
        # Create a client using the session key
#        client = omero.clients.BaseClient(host)
#        client.joinSession(session_key)
        
        # Create a BlitzGateway connection using the client
#        conn = BlitzGateway(client_obj=client)  
        conn = omero_funcs.create_omero_connection(host,session_key)
        projects = omero_funcs.get_user_projects(conn)
        #options = ['Option 1', 'Option 2', 'Option 3']
        return jsonify(projects)        
    
    @app.route('/logout', methods=['POST'])
    def logout():
        session.clear()  # Clear the session
        return jsonify({"message": "Logged out successfully"}), 200


    return app




#Metadata function
def get_info_metadata(img, verbose:bool=True) -> dict:
    """
    Extract important metadata from a CZI image file.
    
    This function opens a CZI image file, reads its metadata, and extracts
    specific information such as microscope details, lens properties,
    image type, pixel size, image dimensions, and other relevant metadata.
    
    Args:
        img_path : The file path to the CZI image.
        verbose (bool, optional): If True, print detailed information during processing. Defaults to True.
    
    Returns:
        ImageMetadata: A dictionnary containing the extracted metadata.
    
    Raises:
        FileNotFoundError: If the specified image file does not exist.
        ValueError: If the file is not a valid CZI image or if metadata extraction fails.
    """
    
    # if verbose: print("Processing:"+" "*10+os.path.basename(img_path))
    try:
        if isinstance(img, str):
            # If img is a string (file path), use it directly
            with pyczi.open_czi(img) as czidoc:
                metadata = czidoc.metadata['ImageDocument']['Metadata']
    except FileNotFoundError:
        raise FileNotFoundError("The file does not exist.")
    except Exception as e:
        raise ValueError(f"Error opening or reading metadata: {str(e)}")
           
    #Initialization
    app_name = None
    app_version = None
    microscope = ''
    acq_type = None
    lensNA = None
    lensMag = None
    pre_processed = None
    comment = None
    description = None
    creation_date = None
                             
    #grab the correct version of the metadata
    app = metadata['Information'].get('Application', None)
    if app != None: #security check
        app_name = app['Name']
        app_version = app['Version']
        if verbose: print('Metadata made with %s version %s' %(app_name, app_version))
        #microscope name, based on the version of the metadata. Do NOT get ELYRA microscope
        #Another way will be to grab the IP address of the room and map it
        if 'ZEN' in app['Name'] and 'blue' in app['Name'] and app['Version'].startswith("3."): #CD7, 980
            microscope += metadata['Scaling']['AutoScaling'].get('CameraName', "") + ", "
            microscope += metadata['Information']['Instrument']['Microscopes']['Microscope'].get('@Name', None)
            #hardcoded part :(
            if 'Axiocam 705 mono' in microscope: microscope = microscope.replace('Axiocam 705 mono', 'LSM 980')
                
        elif 'ZEN' in app['Name'] and 'blue' in app['Name'] and app['Version'].startswith("2."): #Observer
            microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('@Name', None)
            
        elif 'AIM' in app['Name']: #ELYRA, 700, 880
            microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('System', None)
            #hardcoded part :(
            if 'Andor1' in microscope: microscope = microscope.replace('Andor1', 'Elyra')
            
        if verbose: print('Image made on %s' %(microscope))
        #pixel size (everything in the scaling)
        physical_pixel_sizes = {}
        for dim in metadata['Scaling']['Items']['Distance']:
            physical_pixel_sizes[dim['@Id']] = round(float(dim['Value'])*1e+6, 4)
            
        #image dimension
        dims = metadata['Information']['Image']
        size = {}
        for d in dims.keys():
            if 'Size' in d: #just the different Size (X,Y,Z,C,M,H...)
                size[d] = int(dims[d])
        if verbose: print('Image with dimension %s and pixel size of %s' %(size, physical_pixel_sizes))
            
        # Acquisition type (not fully correct with elyra)
        acq_type = metadata['Information']['Image']['Dimensions']['Channels']['Channel']
        if isinstance(acq_type, list):
            acq_type = acq_type[0].get('ChannelType', acq_type[0].get('AcquisitionMode', None))
            if acq_type == 'Unspecified':
                acq_type = metadata['Information']['Image']['Dimensions']['Channels']['Channel'][0].get('AcquisitionMode', None)
        elif isinstance(acq_type, dict):
            acq_type = acq_type.get('AcquisitionMode', None)
        if verbose: print('Image acquired with a %s mode' %(acq_type))
            
        #lens info
        lensNA = metadata['Information']['Instrument']['Objectives']['Objective'].get('LensNA', None)
        if lensNA != None: lensNA = round(float(lensNA), 2)
        lensMag = metadata['Information']['Instrument']['Objectives']['Objective'].get('NominalMagnification', None)
        if lensMag != None: lensMag = int(lensMag)
        if verbose: print('Objective lens used has a magnification of %s and a NA of %s' %(lensMag, lensNA))
            
        #processing (if any)
        processing = metadata['Information'].get('Processing', None)
        if processing is not None:
            pre_processed = list(processing.keys())
        if verbose: print('Image preprocessed with %s' %(pre_processed))
            
        #other
        comment = metadata['Information']['Document'].get('Comment', None)
        description = metadata['Information']['Document'].get('Description', None)
        creation_date = metadata['Information']['Document'].get('CreationDate', None)
        if verbose: print('Image\n    Comment: %s,\n    Description: %s,\n    Creation date: %s' % (comment, description, creation_date))
           
    if verbose: print("_"*25)
    
    mini_metadata = {'Microscope':microscope,
                     'Lens Magnification': lensMag,
                     'Lens NA': lensNA,
                     'Image type':acq_type,
                     'Physical pixel size':physical_pixel_sizes,
                     'Image Size':size,
                     'Comment':comment,
                     'Description':description,
                     'Creation date':creation_date,
                     }
    
    return mini_metadata       





#%%main
if __name__ == '__main__':
    initialize_database()
    #app.run(debug=True)