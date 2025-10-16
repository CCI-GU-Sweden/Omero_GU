from threading import Lock
import omero
import omero.rtypes
from omero.gateway import BlitzGateway, CommentAnnotationWrapper, DatasetWrapper, ImageWrapper
from common import logger

class OmeroConnection:
        
    def __init__(self, hostname: str, port: str, token: str):
        self.omero_token = token
        self.hostname = hostname
        self.port = port
        
        self._mutex = Lock()

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
        logger.info(f"Closing connection to OMERO with token: {self.omero_token}") if self.omero_token is not None else logger.info("Closing connection to OMERO without token")
        if self.conn:
            self.conn.close(hard=hardClose)

    def get_user(self):
        return self.conn.getUser()

    def get_user_id(self):
        return self.conn.getUserId()

    def get_logged_in_user_name(self) -> str:
        user = self.conn.getUser()
        return user.getName() if user else "Unknown User"
    
    def get_logged_in_user_full_name(self) -> str:
        user = self.conn.getUser()
        return user.getFullName() if user else "Unknown User"

    def get_user_groups(self):
        groups = []
        for group in self.conn.getGroupsMemberOf():
            groups.append(group.getName())
        return groups

    def get_default_omero_group(self) -> str:
        group = self.conn.getGroupFromContext()
        return str(group.getName())

    def get_user_project_ids(self, user_id):
        projects = []
        for p in self.conn.listProjects(user_id):         # Initially we just load Projects
            projects.append((p.getName(),p.getId()))
            
        return projects
    
    def get_user_projects(self, user_id):
        projects = []
        for p in self.conn.listProjects(user_id):         # Initially we just load Projects
            projects.append(p)
            
        return projects
        
    def get_dataset(self, dataSetId: int) -> DatasetWrapper | None:
        return self._get_object("Dataset", dataSetId)
        
    def get_image(self, imageID: int) -> ImageWrapper | None:
        return self._get_object("Image", imageID)
    
    def _get_objects(self, obj_type, filters=None):
         with self._mutex:
            match filters:
                case None:
                    return self.conn.getObjects(obj_type)
                case int() | str():
                    return self.conn.getObjects(obj_type, filters)
                case dict():
                    return self.conn.getObjects(obj_type, attributes=filters)
                case _:
                    raise ValueError("Invalid filter type in OmeroConnection._get_objects")        

    def _get_object(self, obj_type, filters=None):        
        with self._mutex:
            match filters:
                case None:
                    return self.conn.getObject(obj_type)
                case int() | str():
                    return self.conn.getObject(obj_type, filters)
                case dict():
                    return self.conn.getObject(obj_type, attributes=filters)
                case _:
                    raise ValueError("Invalid filter type in OmeroConnection._get_object")        

    def create_dataset(self, project_id: int, dataset_name: str):
        with self._mutex:
            dataset = omero.model.DatasetI() # pyright: ignore[reportAttributeAccessIssue]
            dataset.setName(omero.rtypes.rstring(dataset_name))
            dataset = self.conn.getUpdateService().saveAndReturnObject(dataset)
            dataset_id = dataset.getId()

            # Link dataset to project
            link = omero.model.ProjectDatasetLinkI() # pyright: ignore[reportAttributeAccessIssue]
            link.setParent(omero.model.ProjectI(project_id, False)) # pyright: ignore[reportAttributeAccessIssue]
            link.setChild(dataset)
            self.conn.getUpdateService().saveObject(link)
            dataset_id = dataset_id.getValue()
            logger.info(f"Created new dataset '{dataset_name}' with ID {dataset_id} and linked to project.")
            
        return dataset_id

    def create_project(self,project_name):
        p = omero.model.ProjectI() #type: ignore
        p.setName(omero.rtypes.rstring(project_name))
        project = self.conn.getUpdateService().saveAndReturnObject(p)
        logger.info(f"Created new project - ID: {project.getId().getValue()}, Name: {project_name}")
        project_id = project.getId().getValue()
        return project_id

    def create_and_link_local_attachment(self, attachment_file: str, image_id: int):
        img = self._get_object("Image",image_id)
        if img is None:
            logger.error(f"image with id {image_id} does not exist. No link created")
            return False
        
        file_ann = self.conn.createFileAnnfromLocalFile(
                    attachment_file,
                    mimetype="text/plain",  # Adjust as needed
                    desc="Optional description"
                )
        img.linkAnnotation(file_ann)
        return True

    def create_tag_annotation(self, tag_value):
        with self._mutex:
            logger.info(f"Creating tag {tag_value}")
            tag_ann = omero.gateway.TagAnnotationWrapper(self.conn) # pyright: ignore[reportAttributeAccessIssue]
            tag_ann.setValue(tag_value)
            tag_ann.save()

    def set_annotation_on_image(self, image, annotation):
        with self._mutex:
            try:
                logger.info(f"linking tag {annotation.getValue()} to image {image.getId()}")
                image.linkAnnotation(annotation)
            except omero.ValidationException as e: # pyright: ignore[reportAttributeAccessIssue]
                logger.warning(f"Failed to insert the tag {annotation.getValue()} to image {image}: {str(e)}")
            except omero.ApiUsageException as e: # pyright: ignore[reportAttributeAccessIssue]
                 logger.warning(f"Failed to insert the tag {annotation.getValue()} to image {image}: {str(e)}")
            except Exception as e:
                logger.error(f"Failed to set/get tag annotations on image {image}: {str(e)}")


    def set_description_on_image(self, image, descr):
        with self._mutex:
            image.setDescription(descr)
            image.save()

    def set_comment_on_image(self, image, comment):
        with self._mutex:
            comment_ann = CommentAnnotationWrapper(self.conn) # pyright: ignore[reportAttributeAccessIssue]
            comment_ann.setValue(comment)
            comment_ann.save()
            image.linkAnnotation(comment_ann)
