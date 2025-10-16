import traceback
from datetime import datetime
from common import omero_connection
from common import logger
from common import conf
from omero.gateway import DatasetWrapper, MapAnnotationWrapper, CommentAnnotationWrapper, TagAnnotationWrapper
from omerofrontend.exceptions.exceptions import OmeroObjectNotFoundError

class OmeroGetterCtx:
    """
    Context manager for getting objects from omero
    """
    def __init__(self, omero_connection : omero_connection.OmeroConnection):
        self.conn = omero_connection

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass
    
    def get_project_name(self, proj_id: int) -> str:
        project = self.conn._get_object("Project", proj_id)
        if not project:
            raise OmeroObjectNotFoundError(f"Project with ID {proj_id} not found")
        
        return project.getName()
    
    def get_dataset_name(self, dataset_id: int) -> str | None:
        dataset: DatasetWrapper| None = self.conn.get_dataset(dataset_id)
        if dataset is None:
            raise OmeroObjectNotFoundError(f"dataset with id {dataset_id} does not exist")
        
        return dataset.getName()
    
    def get_or_create_dataset(self, project_id, dataset_name) -> int:
        
        project = self.conn._get_object("Project", project_id)
        if not project:
            raise OmeroObjectNotFoundError(f"Project with ID {project_id} not found")

        data = [d for d in project.listChildren() if d.getName() == dataset_name]

        if len(data) > 0:
            dataset_id = data[0].getId()
            logger.debug(f"Dataset '{dataset_name}' already exists in project. Using existing dataset.")
            return dataset_id

        dataset_id = self.conn.create_dataset(project_id, dataset_name)            
        return dataset_id

    def get_user_project_if_it_exists(self, project_name, user_id):
        projects = self.conn.get_user_projects(user_id)
        for p in projects:
            if p.getName() == project_name:
                return p
        
        return None

    def get_or_create_project(self, project_name, user_id) -> int:
        #logger.debug(f"Setting or grabbing the Project {}")
        # Try to get the project
        project = self.get_user_project_if_it_exists(project_name, user_id)
        if project:
            return project.getId()
            
        else:
            id = self.conn.create_project(project_name)
            return id
        

    def check_duplicate_file(self, filename: str, datasetId: int):
        dataset = self.conn.get_dataset(datasetId)
        if not dataset:
            logger.warning(f"Dataset with ID {datasetId} not found")
            return False, None
        
        for child in dataset.listChildren():
            if child.getName().startswith(filename):
                return True, child.getId()

        return False, None

    #return the first value of the given key or None
    def get_map_annotation_value(self, imageId, key):
        value = None
        image = self.conn.get_image(imageId)
        map_annotations = [ann for ann in image.listAnnotations() if isinstance(ann, MapAnnotationWrapper)] # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
        for map_ann in map_annotations:
            k_list = [x for x in map_ann.getValue() if x[0] == key]
            if len(k_list):
                value = k_list[0][1]
                break
            
        return value

    def compare_image_acquisition_time(self,imageId, compareDate, fmtStr="%H-%M-%S") -> bool:
        image = self.conn.get_image(imageId)
        if not image:
            logger.warning(f"Image with ID {imageId} not found")
            return False
        acq_time_obj = image.getAcquisitionDate()
        if not acq_time_obj:
            acq_time_str = self.get_map_annotation_value(imageId,"Acquisition date")
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
        for tag in self.conn._get_objects("TagAnnotation"): #grab all tag
            tags.append(tag.getValue())
        tags = [x.replace(key,'') for x in tags if x.startswith(key+' ')] #filter it

        return tags


    def get_tag_annotations(self,tag_value):
        attributes={'textValue': tag_value}
        return self.conn._get_objects("TagAnnotation", attributes)

    def get_tag_annotation(self,tag_value):
        the_tag = None
        for tag in self.get_tag_annotations(tag_value):
            if tag.getValue() == tag_value:
                the_tag = tag
                
        return the_tag

    def get_tag_annotation_id(self, tag_value) -> list[int] | None:
        tag = self.get_tag_annotation(tag_value)
        return tag.getId() if tag else None

    def get_comment_annotations(self):
        return self.conn._get_objects("CommentAnnotation")

    def get_comment_annotation(self, value):
        for comment_ann in self.get_comment_annotations():
            try:
                if not isinstance(comment_ann, CommentAnnotationWrapper): # pyright: ignore[reportAttributeAccessIssue]
                    logger.warning(f"Annotation {comment_ann.getId()} is not a CommentAnnotationWrapper")
                    continue
                value = comment_ann.getValue()
                logger.info(f"Found comment annotation with value: {value}")

            except Exception as e:
                logger.error(f"Failed to get comment annotation: {str(e)} stack: {traceback.format_exc()}")
                continue
            
        return value

    def get_map_annotations(self):
        try:
            logger.info("Fetching all map annotations")
            return self.conn._get_objects("MapAnnotation")
        except Exception as e:
            logger.error(f"Failed to get map annotations: {str(e)} stack: {traceback.format_exc()}")
            #ServerEventManager.send_error_event("N/A",f"Failed to get map annotations: {str(e)}")
            return []

    #TODO: this is intrusive...need fix
    def get_map_annotation(self, name, value):
        for map_ann in self.get_map_annotations():
            if not isinstance(map_ann, MapAnnotationWrapper): # pyright: ignore[reportAttributeAccessIssue]
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
        image = self.conn.get_image(imageId)
        if not image:
            logger.warning(f"Image with ID {imageId} not found")
            return map_annotations
        
        for ann in image.listAnnotations():
            if isinstance(ann, MapAnnotationWrapper): # pyright: ignore[reportAttributeAccessIssue]
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
        image = self.conn.get_image(imageId)
        if not image:
            logger.warning(f"Image with ID {imageId} not found")
            return tags
        
        for ann in image.listAnnotations():
            if isinstance(ann, TagAnnotationWrapper): # pyright: ignore[reportAttributeAccessIssue]
                tags.append(ann.getValue())
                
        return tags

    def set_annotation_on_image(self, image, tag_value):
        tag_ann = self.get_tag_annotation(tag_value)
        if tag_ann is None:
            tag_ann = self.conn.create_tag_annotation(tag_value)
            
        self.conn.set_annotation_on_image(image,tag_ann)
            