import omero
from omero.cli import CLI
from omero.gateway import BlitzGateway, ProjectWrapper
import ezomero
import omero.rtypes
import logger


#the main connection object (BlitzGaterway). This should really be wrapped in a class
theConn = None
theHostname = None
theToken = None

def get_omero_connection():
    return theConn

def connect_to_omero(hostname, port, token):
    global theHostname
    theHostname = hostname
    
    global theToken
    theToken= token
    
    global theConn
    theConn = BlitzGateway(host=hostname,port=port)
    isConn = theConn.connect(token)
    
    return hostname, token, isConn



# def connect_to_omero(hostname, port, token):
#     logger.info("Enter function connect_to_omero")
#     cli = CLI()
#     cli.loadplugins()
    
#     login_args = ["login", "-s", hostname, "-k", token, "-p", port]
    
#     try:
#         cli.invoke(login_args)
#     except Exception as e:
#         logger. info(e)
#         return None, None
    
#     event_context = cli.get_event_context()
    
#     if event_context is None:
#         logger.info("Login failed: No event context returned.")
#         return None, None
    
#     logger.info("login done")
#     session_key = event_context.sessionUuid
    
#     logger.info("connection done")
#     cli = cli.getClient()
#     conn =BlitzGateway(client_obj=cli)
#     return session_key, hostname, conn


def get_user_project_if_it_exists(conn, project_name):
    projects = get_user_projects(conn)
    for p in projects:
        if p.getName() == project_name:
            return p
        
    return None
    

def get_or_create_project(conn, project_name):
    logger.debug("Setting or grabbing the Project")

    # Try to get the project
    project = get_user_project_if_it_exists(conn, project_name)
        
    if not project:
        # Create project using UpdateService
        p = omero.model.ProjectI()
        project = ProjectWrapper(obj=p,conn=conn)
        project.setName(project_name)
        project.save()
        logger.info(f"Created new project - ID: {project.getId()}, Name: {project_name}")
    
    
    return project.getId()

def get_logged_in_user_name(conn):
    return conn.getUser().getName()

def get_user_project_ids(conn):
    projects = []
    my_expId = conn.getUser().getId()
    for p in conn.listProjects(my_expId):         # Initially we just load Projects
        projects.append((p.getName(),p.getId()))
        
    return projects
    
def get_user_projects(conn):
    projects = []
    my_expId = conn.getUser().getId()
    for p in conn.listProjects(my_expId):         # Initially we just load Projects
        projects.append(p)
        
    return projects

    
def get_dataset_for_projects(conn, project_id):
    project = conn.getObject("Project", project_id)
    if not project:
        raise Exception(f"Project with ID {project_id} not found")

    datasets = []
    for dataset in project.listChildren():      # lazy-loading of Datasets here
        datasets.append(dataset)

    return datasets


def get_dataset_ids_for_projects(conn, project_id):
    project = conn.getObject("Project", project_id)
    if not project:
        raise Exception(f"Project with ID {project_id} not found")

    datasets = []
    for dataset in project.listChildren():      # lazy-loading of Datasets here
        datasets.append((dataset.getName(),dataset.getId()))

    return datasets


def get_or_create_dataset(conn, project_id, dataset_name):
    project = conn.getObject("Project", project_id)
    if not project:
        raise Exception(f"Project with ID {project_id} not found")


    data = [d for d in project.listChildren() if d.getName() == dataset_name]

    if len(data) > 0:
        dataset_id = data[0].getId()
        logger.debug(f"Dataset '{dataset_name}' already exists in project. Using existing dataset.")
    else:
        # Dataset doesn't exist, create it
        dataset = omero.model.DatasetI()
        dataset.setName(omero.rtypes.rstring(dataset_name))
        dataset = conn.getUpdateService().saveAndReturnObject(dataset)
        dataset_id = dataset.getId()

        # Link dataset to project
        link = omero.model.ProjectDatasetLinkI()
        link.setParent(omero.model.ProjectI(project_id, False))
        link.setChild(dataset)
        conn.getUpdateService().saveObject(link)
        
        logger.info(f"Created new dataset '{dataset_name}' with ID {dataset_id.getValue()} and linked to project.")
        
    return dataset_id

def import_image(conn, img_path, dataset_id, meta_dict):
    
    # import the image - work for the CCI IT!
    namespace = omero.constants.metadata.NSCLIENTMAPANNOTATION
    
    image_id = ezomero.ezimport(conn=conn,
                                target=img_path,
                                dataset=dataset_id.getId(),
                                ann=meta_dict,
                                ns=namespace)
    
    #add tag in the image as well 
    for im in image_id:
        image = conn.getObject("Image", im)
        
        # Add tags
        tags = [meta_dict['Microscope'], str(meta_dict['Lens Magnification'])+"X", meta_dict['Image type']]
        for tag_value in tags:
            tag_ann = None
            tag_value = str(tag_value)
            if tag_value[0].isdigit():
                tag_value = "_"+tag_value                
            for ann in conn.getObjects("TagAnnotation", attributes={'textValue': tag_value}):
                tag_ann = ann
            
            if not tag_ann:
                tag_ann = omero.gateway.TagAnnotationWrapper(conn)
                tag_ann.setValue(tag_value)
                tag_ann.save()
            
            image.linkAnnotation(tag_ann)
        
        # Add description
        if meta_dict.get('Description'):
            image.setDescription(str(meta_dict['Description']))
            image.save()
        
        # Add comment
        if meta_dict.get("Comment"):
            comment_ann = omero.gateway.CommentAnnotationWrapper(conn)
            comment_ann.setValue(meta_dict["Comment"])
            comment_ann.save()
            image.linkAnnotation(comment_ann)
    
    return image_id
