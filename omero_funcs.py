import omero
from omero.cli import CLI
from omero.gateway import BlitzGateway
import ezomero
import logging
import config

logger = logging.getLogger(config.APP_NAME)

#OMERO functions
def create_omero_connection(host, session_key):
    session_key = session_key
    host = host
        
    # Create a client using the session key
    client = omero.clients.BaseClient(host)
    client.joinSession(session_key)
        
    # Create a BlitzGateway connection using the client
    conn = BlitzGateway(client_obj=client)
    return conn

def connect_to_omero(hostname, port, token):
    logger.info("Enter function connect_to_omero")
    cli = CLI()
    cli.loadplugins()
    
    login_args = ["login", "-s", hostname, "-k", token, "-p", port]
    
    try:
        cli.invoke(login_args)
    except Exception as e:
        logger. info(e)
        return None, None
    
    event_context = cli.get_event_context()
    
    if event_context is None:
        logger.info("Login failed: No event context returned.")
        return None, None
    
    logger.info("login done")
    session_key = event_context.sessionUuid
    
    logger.info("connection done")
    return session_key, hostname


def get_or_create_project(conn, project_name, verbose=False):
    if verbose:
        print("Setting or grabbing the Project")

    # Try to get the project
    projects = list(conn.getObjects("Project", attributes={"name": project_name}))
    
    if projects:
        project = projects[0]
        projID = project.getId()
        if verbose:
            print(f"Using existing project - ID: {projID}, Name: {project.getName()}")
    else:
        # Create project using UpdateService
        project = omero.model.ProjectI()
        project.setName(omero.rtypes.rstring(project_name))
        project = conn.getUpdateService().saveAndReturnObject(project)
        projID = project.getId().getValue()
        if verbose:
            print(f"Created new project - ID: {projID}, Name: {project_name}")
    
    return projID

def get_user_projects(conn):
    projects = []
    for p in conn.listProjects():         # Initially we just load Projects
        projects.append((p.getName(),p.getId()))
        
    return projects
    
def get_datasets_for_projects(conn, project_id):
    project = conn.getObject("Project", project_id)
    if not project:
        raise Exception(f"Project with ID {project_id} not found")

    datasets = []
    for dataset in project.listChildren():      # lazy-loading of Datasets here
        datasets.append((dataset.getName(),dataset.getId()))

    return datasets


def get_or_create_dataset(conn, project_id, dataset_name, verbose=False):
    project = conn.getObject("Project", project_id)
    if not project:
        raise Exception(f"Project with ID {project_id} not found")

    for dataset in project.listChildren():
        if dataset.getName() == dataset_name:
            if verbose:
                print(f"Dataset '{dataset_name}' already exists in project. Using existing dataset.")
            return dataset.getId()

    # Dataset doesn't exist, create it
    dataset = omero.model.DatasetI()
    dataset.setName(omero.rtypes.rstring(dataset_name))
    dataset = conn.getUpdateService().saveAndReturnObject(dataset)
    dataset_id = dataset.getId().getValue()

    # Link dataset to project
    link = omero.model.ProjectDatasetLinkI()
    link.setParent(omero.model.ProjectI(project_id, False))
    link.setChild(dataset)
    conn.getUpdateService().saveObject(link)
    
    if verbose:
        print(f"Created new dataset '{dataset_name}' with ID {dataset_id} and linked to project.")
    
    return dataset_id

def import_image(conn, img_path, dataset_id, meta_dict):
    
    # import the image - work for the CCI IT!
    namespace = omero.constants.metadata.NSCLIENTMAPANNOTATION
    image_id = ezomero.ezimport(conn,
                                img_path,
                                dataset=dataset_id,
                                ann=meta_dict,
                                ns=namespace,
                                )
    
    #add tag in the image as well 
    for im in image_id:
        image = conn.getObject("Image", im)
    
        
        # Add tags
        tags = [meta_dict['Microscope'], str(meta_dict['Lens Magnification'])+"X", meta_dict['Image type']]
        for tag_value in tags:
            tag_ann = None
            tag_value = str(tag_value)
            for ann in conn.getObjects("TagAnnotation", attributes={'textValue': tag_value}):
                tag_ann = ann
            
            if not tag_ann:
                tag_ann = omero.gateway.TagAnnotationWrapper(conn)
                tag_ann.setValue(tag_value)
                tag_ann.save()
            
            image.linkAnnotation(tag_ann)
        
        # Add description
        if meta_dict['Description']:
            image.setDescription(str(meta_dict['Description']))
            image.save()
        
        # Add comment
        if meta_dict["Comment"]:
            comment_ann = omero.gateway.CommentAnnotationWrapper(conn)
            comment_ann.setValue(meta_dict["Comment"])
            comment_ann.save()
            image.linkAnnotation(comment_ann)
    
    return image_id
