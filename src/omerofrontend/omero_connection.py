from . import conf
from . import logger
import omero
import omero.rtypes
import omero.api
from omero.gateway import BlitzGateway, ProjectWrapper, TagAnnotationWrapper
import omero.rtypes
from datetime import datetime

from threading import Thread, Lock


class OmeroConnection:
    
    _mutex = Lock()
    
    def __init__(self, hostname, port, token):
        self._connect_to_omero(hostname,port,token)
        
    def __del__(self):
        self._close_omero_connection()
    
    def kill_session(self):
        self._close_omero_connection(True)
        
    def get_omero_connection(self):
        return self.conn
    
    def _connect_to_omero(self, hostname, port, token):
        logger.info(f"Opening connection to OMERO with token: {token}, hostname: {hostname}")    
        self.omero_token = token

        self.conn = BlitzGateway(host=hostname, port=port)
        is_connected = self.conn.connect(token)
    
        if not is_connected:
            logger.warning(f"Failed to connect to OMERO with token: {token}")
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
        
        with self._mutex:
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

        with self._mutex:

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
        image = self.getImage(imageId)
        acq_time_obj = image.getAcquisitionDate()
        if not acq_time_obj:
            acq_time_str = self.getMapAnnotationValue(imageId,"Acquisition date")
            if acq_time_str:
                acq_time_obj = datetime.strptime(acq_time_str,conf.DATE_TIME_FMT)
            else:
                logger.warning(f"No acquisition date stored in image id {imageId}")
                return False        
        
        check_time = compareDate.strftime(fmtStr)
        acq_time = acq_time_obj.strftime(fmtStr)        
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

    def get_user_group(self):
        groups = []
        for group in self.conn.getGroupsMemberOf():
            groups.append(group.getName())
        return groups
                
    def getTagAnnotationIfItExists(self, tag_value):
        tag_gen = self.getTagAnnotations(tag_value)
        return next((x for x in tag_gen if x.geValue() == tag_value),None) 
        
                
    def getTagAnnotations(self,tag_value):
        attributes={'textValue': tag_value}
        return self.conn.getObjects("TagAnnotation", attributes=attributes)

    def getTagAnnotation(self,tag_value):
        attributes={'textValue': tag_value}
        return self.conn.getObject("TagAnnotation", attributes=attributes)

    def setGroupNameForSession(self, group):
        with self._mutex:
            self.conn.setGroupNameForSession(group)
        
    def getDefaultOmeroGroup(self):
        group = self.conn.getGroupFromContext()
        return group.getName()
    
    def setAnnotationOnImage(self, image, tag_value):
        with self._mutex:
            try:
                tag_ann = self.getTagAnnotationIfItExists(tag_value)
                if not tag_ann:
                    tag_ann = omero.gateway.TagAnnotationWrapper(self.conn)
                    tag_ann.setValue(tag_value)
                    tag_ann.save()

                image.linkAnnotation(tag_ann)
            except omero.ValidationException as e:
                logger.warning(f"Failed to insert the tag {tag_value} to image {image}: {str(e)}")
            except omero.ApiUsageException as e:
                logger.error(f"Failed to set/get tag annotations on image {image}: {str(e)}")
            except Exception as e:
                logger.error(f"Failed to set/get tag annotations on image {image}: {str(e)}")

    #return the first value of the given key or None
    def getMapAnnotationValue(self, imageId, key):
        value = None
        image = self.conn.getObject("Image", imageId)
        map_annotations = [ann for ann in image.listAnnotations() if isinstance(ann, omero.gateway.MapAnnotationWrapper)]
        for map_ann in map_annotations:
            k_list = [x for x in map_ann.getValue() if x[0] == key]
            if len(k_list):
                value = k_list[0][1]
                break
            
        return value
    
    def setDescriptionOnImage(self, image, descr):
        with self._mutex:
            image.setDescription(descr)
            image.save()

    def setCommentOnImage(self, image, comment):
        with self._mutex:
            comment_ann = omero.gateway.CommentAnnotationWrapper(self.conn)
            comment_ann.setValue(comment)
            comment_ann.save()
            image.linkAnnotation(comment_ann)
