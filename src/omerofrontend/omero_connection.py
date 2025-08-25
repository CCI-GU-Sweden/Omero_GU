from threading import Lock
from datetime import datetime
from typing import Optional
import traceback
import omero
import omero.rtypes
from omero.gateway import BlitzGateway, DatasetWrapper
from omerofrontend import conf
from omerofrontend import logger




class OmeroConnection:
    
    _mutex = Lock()
    
    def __init__(self, hostname: str, port: str, token: str):
        self.omero_token = token
        self._connect_to_omero(hostname,port)
        
    def __del__(self):
        self._close_omero_connection()
    
    def kill_session(self):
        self._close_omero_connection(True)
        
    def get_omero_connection(self):
        return self.conn
    
    def _connect_to_omero(self, hostname, port):
        logger.info(f"Opening connection to OMERO with token: {self.omero_token}, hostname: {hostname}")    
        #self.omero_token = token

        self.conn = BlitzGateway(host=hostname, port=port)
        is_connected = self.conn.connect(self.omero_token)
    
        if not is_connected:
            logger.warning(f"Failed to connect to OMERO with token: {self.omero_token}")
            raise ConnectionError("Failed to connect to OMERO")

    def _close_omero_connection(self,hardClose=False):
        logger.info(f"Closing connection to OMERO with token: {self.omero_token}") #if self.omero_token is not None else logger.info("Closing connection to OMERO without token")
        if self.conn:
            self.conn.close(hard=hardClose)

    def get_user_project_if_it_exists(self, project_name):
        projects = self.get_user_projects()
        for p in projects:
            if p.getName() == project_name:
                return p
        
        return None

    def get_or_create_project(self, project_name) -> int:
        
        with self._mutex:
            logger.debug(f"Setting or grabbing the Project {self.conn}")

            # Try to get the project
            project = self.get_user_project_if_it_exists(project_name)
            
            if not project:
                # Create project using UpdateService
                p = omero.model.ProjectI() #type: ignore
                p.setName(omero.rtypes.rstring(project_name))
                project = self.conn.getUpdateService().saveAndReturnObject(p)
                
            proj_id = project.getId().getValue()
            logger.info(f"Using project - ID: {proj_id}, Name: {project_name}")
            return proj_id
            

    def get_user(self):
        return self.conn.getUser()

    def get_logged_in_user_name(self) -> str:
        user = self.conn.getUser()
        return user.getName() if user else "Unknown User"
    
    def get_logged_in_user_full_name(self) -> str:
        user = self.conn.getUser()
        return user.getFullName() if user else "Unknown User"
    
    def get_user_project_ids(self):
        projects = []
        user = self.conn.getUser()
        if user is None:
            logger.warning("No user is currently logged in.")
            return projects
        my_expId = user.getId()
        for p in self.conn.listProjects(my_expId):         # Initially we just load Projects
            projects.append((p.getName(),p.getId()))
            
        return projects
    
    def get_user_projects(self):
        projects = []
        user = self.conn.getUser()
        if user is None:
            logger.warning("No user is currently logged in.")
            return projects
        my_expId = user.getId()
        for p in self.conn.listProjects(my_expId):         # Initially we just load Projects
            projects.append(p)
            
        return projects
        
    def get_project_name(self, proj_id: int) -> str:
        project = self.conn.getObject("Project", proj_id)
        if not project:
            raise Exception(f"Project with ID {proj_id} not found")
        
        return project.getName()

    def get_dataset_name(self, dataset_id: int) -> str:
        dataset = self.conn.getObject("Dataset", dataset_id)
        if not dataset:
            raise Exception(f"dataset with id {dataset_id} does not exist")
        
        return dataset.getName()

        
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

    def get_or_create_dataset(self, project_id, dataset_name) -> int:
        
        project = self.conn.getObject("Project", project_id)
        if not project:
            raise Exception(f"Project with ID {project_id} not found")

        with self._mutex:

            data = [d for d in project.listChildren() if d.getName() == dataset_name]

            if len(data) > 0:
                dataset_id = data[0].getId().getValue()
                logger.debug(f"Dataset '{dataset_name}' already exists in project. Using existing dataset.")
            else:
                # Dataset doesn't exist, create it
                dataset = omero.model.DatasetI()
                dataset.setName(omero.rtypes.rstring(dataset_name))
                dataset = self.conn.getUpdateService().saveAndReturnObject(dataset)
                dataset_id = dataset.getId().getValue()

                # Link dataset to project
                link = omero.model.ProjectDatasetLinkI()
                link.setParent(omero.model.ProjectI(project_id, False))
                link.setChild(dataset)
                self.conn.getUpdateService().saveObject(link)
                
                logger.info(f"Created new dataset '{dataset_name}' with ID {dataset_id} and linked to project.")
            
        return dataset_id

    def get_dataset(self, dataSetId: int) -> Optional[DatasetWrapper]:
        return self.conn.getObject("Dataset", dataSetId)
        
    def getImage(self, imageID):
        return self.conn.getObject("Image", imageID)

    def check_duplicate_file(self, filename: str, datasetId: int):
        dataset = self.get_dataset(datasetId)
        if not dataset:
            logger.warning(f"Dataset with ID {datasetId} not found")
            return False, None
        
        for child in dataset.listChildren():
            if child.getName().startswith(filename):
                return True, child.getId()

        return False, None

    def compareImageAcquisitionTime(self,imageId, compareDate, fmtStr="%H-%M-%S") -> bool:
        image = self.getImage(imageId)
        if not image:
            logger.warning(f"Image with ID {imageId} not found")
            return False
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
                
    def getTagAnnotations(self,tag_value):
        attributes={'textValue': tag_value}
        return self.conn.getObjects("TagAnnotation", attributes=attributes)

    def get_tag_annotation(self,tag_value):
        # attributes={'textValue': tag_value}
        # return self.conn.getObject("TagAnnotation", attributes=attributes)
        the_tag = None
        for tag in self.getTagAnnotations(tag_value):
            if tag.getValue() == tag_value:
                the_tag = tag
                
        return the_tag

    def get_tag_annotation_id(self, tag_value) -> Optional[int]:
        tag = self.get_tag_annotation(tag_value)
        return tag.getId() if tag else None

    def get_comment_annotations(self):
        return self.conn.getObjects("CommentAnnotation")

    def get_comment_annotation(self, value):
        for comment_ann in self.get_comment_annotations():
            try:
                if not isinstance(comment_ann, omero.gateway.CommentAnnotationWrapper):
                    logger.warning(f"Annotation {comment_ann.getId()} is not a CommentAnnotationWrapper")
                    continue
                value = comment_ann.getValue()
                logger.info(f"Found comment annotation with value: {value}")

            except Exception as e:
                logger.error(f"Failed to get comment annotation: {str(e)} stack: {traceback.format_exc()}")
                continue
            
        return value

    def get_map_annotations(self):
        return self.conn.getObjects("MapAnnotation")

    # def get_map_annotation(self, name, value):
    #     for map_ann in self.get_map_annotations():
    #         try:
    #             if not isinstance(map_ann, omero.gateway.MapAnnotationWrapper):
    #                 logger.warning(f"Annotation {map_ann.getId()} is not a MapAnnotationWrapper")
    #                 continue
    #             val = map_ann.getValue()
    #             logger.info(f"Found map annotation {name} {val}")
    #         except Exception as e:
    #             logger.error(f"Failed to get map annotation: {str(e)} stack: {traceback.format_exc()}")
    #             continue
            
    #     return None

    #TODO: this is intrusive...need fix
    def get_map_annotation(self, name, value):
        for map_ann in self.get_map_annotations():
            if not isinstance(map_ann._obj, omero.model.MapAnnotationI):
                #logger.warning(f"Annotation {map_ann.getId()} is not a MapAnnotationWrapper")
                continue
            n, v = map_ann.getValue()[0]
            if n == name and v == value:
                return map_ann            
        return None

    def get_image_map_annotations(self, imageId):
        """
        Fetch all map annotations associated with a specific image.
        
        Args:
            imageId: The ID of the image for which to fetch map annotations.
        
        Returns:
            List of tuples containing key-value pairs from map annotations.
        """
        map_annotations = []
        image = self.conn.getObject("Image", imageId)
        if not image:
            logger.warning(f"Image with ID {imageId} not found")
            return map_annotations
        
        for ann in image.listAnnotations():
            if isinstance(ann, omero.gateway.MapAnnotationWrapper):
                map_annotations.extend(ann.getValue())
                
        return map_annotations

    def get_image_tags(self, imageId):
        """
        Fetch all tags associated with a specific image.
        
        Args:
            imageId: The ID of the image for which to fetch tags.
        
        Returns:
            List of tag values associated with the image.
        """
        tags = []
        image = self.conn.getObject("Image", imageId)
        if not image:
            logger.warning(f"Image with ID {imageId} not found")
            return tags
        
        for ann in image.listAnnotations():
            if isinstance(ann, omero.gateway.TagAnnotationWrapper):
                tags.append(ann.getValue())
                
        return tags

    def setGroupNameForSession(self, group):
        with self._mutex:
            self.conn.setGroupNameForSession(group)
        
    def getDefaultOmeroGroup(self) -> str:
        group = self.conn.getGroupFromContext()
        return str(group.getName())
    
    def setAnnotationOnImage(self, image, tag_value):
        with self._mutex:
            try:
                tag_ann = self.get_tag_annotation(tag_value)
                if not tag_ann:
                    logger.info(f"tag {tag_value} does not exist. Creating it")
                    tag_ann = omero.gateway.TagAnnotationWrapper(self.conn)
                    tag_ann.setValue(tag_value)
                    tag_ann.save()

                logger.info(f"linking tag {tag_value} to image {image.getId()}")
                image.linkAnnotation(tag_ann)
            except omero.ValidationException as e:
                logger.warning(f"Failed to insert the tag {tag_value} to image {image}: {str(e)}")
            except omero.ApiUsageException as e:
                 logger.warning(f"Failed to insert the tag {tag_value} to image {image}: {str(e)}")
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
