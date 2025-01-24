import logger
import omero
from omero.gateway import BlitzGateway, ProjectWrapper
import omero.rtypes


class OmeroConnection:
    def __init__(self, hostname, port, token):
        self._connect_to_omero(hostname,port,token)
        
    def __del__(self):
        self._close_omero_connection()
    
    def kill_session(self):
        self._close_omero_connection(True)
        
    def get_omero_connection(self):
        return self.conn
    
    def _connect_to_omero(self, hostname, port, token):
        logger.info(f"Opening connection to OMERO with token: {token}")    
        self.omero_token = token

        self.conn = BlitzGateway(host=hostname, port=port)
        is_connected = self.conn.connect(token)
    
        if not is_connected:
            logger.info(f"Failed to connect to OMERO with token: {token}")
            raise ConnectionError("Failed to connect to OMERO")

    def _close_omero_connection(self,hardClose=False):
        logger.info(f"Closing connection to OMERO with token: {self.omero_token}")
        if self.conn:
            self.conn.close(hard=hardClose)

    def get_user_project_if_it_exists(self, project_name):
        projects = self.get_user_projects()
        for p in projects:
            if p.getName() == project_name:
                return p
        
        return None

    def get_or_create_project(self, project_name):
        logger.debug(f"Setting or grabbing the Project {self.conn}")

        # Try to get the project
        project = self.get_user_project_if_it_exists(project_name)
            
        if not project:
            # Create project using UpdateService
            p = omero.model.ProjectI()
            project = ProjectWrapper(obj=p,conn=self.conn)
            project.setName(project_name)
            project.save()
            logger.info(f"Created new project - ID: {project.getId()}, Name: {project_name}")
        
        return project.getId()

    def get_user(self):
        return self.conn.getUser()

    def get_logged_in_user_name(self):
        return self.conn.getUser().getName()

    def get_user_project_ids(self):
        projects = []
        my_expId = self.conn.getUser().getId()
        for p in self.conn.listProjects(my_expId):         # Initially we just load Projects
            projects.append((p.getName(),p.getId()))
            
        return projects
    
    def get_user_projects(self):
        projects = []
        my_expId = self.conn.getUser().getId()
        for p in self.conn.listProjects(my_expId):         # Initially we just load Projects
            projects.append(p)
            
        return projects

        
    def get_dataset_for_projects(self, project_id):
        project = self.conn.getObject("Project", project_id)
        if not project:
            raise Exception(f"Project with ID {project_id} not found")

        datasets = []
        for dataset in project.listChildren():      # lazy-loading of Datasets here
            datasets.append(dataset)

        return datasets

    def get_dataset_ids_for_projects(self, project_id):
        project = self.conn.getObject("Project", project_id)
        if not project:
            raise Exception(f"Project with ID {project_id} not found")

        datasets = []
        for dataset in project.listChildren():      # lazy-loading of Datasets here
            datasets.append((dataset.getName(),dataset.getId()))

        return datasets

    def get_or_create_dataset(self, project_id, dataset_name):
        project = self.conn.getObject("Project", project_id)
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
            dataset = self.conn.getUpdateService().saveAndReturnObject(dataset)
            dataset_id = dataset.getId()

            # Link dataset to project
            link = omero.model.ProjectDatasetLinkI()
            link.setParent(omero.model.ProjectI(project_id, False))
            link.setChild(dataset)
            self.conn.getUpdateService().saveObject(link)
            
            logger.info(f"Created new dataset '{dataset_name}' with ID {dataset_id.getValue()} and linked to project.")
            
        return dataset_id

    def getDataset(self, dataID):
        return self.conn.getObject("Dataset", dataID)
        
    def getImage(self, imageID):
        return self.conn.getObject("Image", imageID)

    def compareImageAcquisitionTime(self,imageId,compareDate, fmtStr="%H-%M-%S"):
        image = self.conn.getImage(imageId)
        acq_time = image.getAcquisitionDate().strftime(fmtStr)
        check_time = compareDate.strftime(fmtStr)
        return check_time == acq_time

    def get_tags_by_key(self, key):
        """
        Fetch all tag values associated with a specific key.
        
        Args:
            conn: OMERO connection object.
            key: The key for which to fetch tag values.
        
        Returns:
            List of tag values.
        """
        tags = []
        for tag in self.conn.getObjects("TagAnnotation"): #grab all tag
            tags.append(tag.getValue())
        tags = [x.replace(key,'') for x in tags if x.startswith(key+' ')] #filter it

        return tags
