import os
from threading import Lock
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import ezomero
import omero.constants.metadata
import omero
import xml.etree.ElementTree as ET
from omerofrontend.omero_connection import OmeroConnection
from omerofrontend import conf
from omerofrontend import logger
from omerofrontend.file_data import FileData

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, file_path, progress_func):
        self.file_path = file_path
        self.last_position = 0
        self.prog_fun = progress_func

    def on_any_event(self, event):
        return #reimplement to disable debug prints

    def on_modified(self, event):
        if event.src_path == self.file_path:
            with open(self.file_path, "r") as f:
                f.seek(self.last_position)
                new_data = f.read()
                self.last_position = f.tell()
                if new_data:
                    if new_data.startswith("FILE_UPLOAD"):
                        return

                    data = new_data.split(' ')
                    ratio = 100 * (float(data[0]) / float(data[1].rstrip()))
                    self.prog_fun(int(ratio))


mutex = Lock()

def setup_log_and_progress_files(import_file_stem):

    progress_log_file = conf.IMPORT_PROGRESS_DIR + conf.IMPORT_PROGRESS_FILE_STEM + "-" \
                        + import_file_stem + conf.IMPORT_LOG_FILE_EXTENSION
    import_log_file = conf.LOG_DIR + conf.IMPORT_LOG_FILE_STEM + "-" + import_file_stem + \
                        conf.IMPORT_LOG_FILE_EXTENSION
    logback_file = import_file_stem + "-" + conf.IMPORT_LOGBACK_FILE

    # 1. Parse the XML
    tree = ET.parse('logback.xml')
    root = tree.getroot()

    # 2. Modify the <file> element(s)
    for appender in root.findall(".//appender"):
        appender_name = appender.attrib.get("name")
        file_elem = appender.find("file")
        if appender_name == "IMPORT":
            if file_elem is not None:
                file_elem.text = import_log_file
        if appender_name == "PROGRESS":
            if file_elem is not None:
                file_elem.text = progress_log_file

    # 3. Save the modified XML
    tree.write(logback_file, encoding='utf-8', xml_declaration=True)

    return progress_log_file, import_log_file, logback_file


def safe_remove(filepath):
    try:
        os.remove(filepath)
    except FileNotFoundError:
        logger.warning(f"File not found, could not remove: {filepath}")
    except Exception as e:
        logger.warning(f"Error removing file {filepath}: {str(e)}")


def import_image(conn : OmeroConnection, fileData: FileData, dataset_id, meta_dict, batch_tag, progress_func, retry_func):
    # import the image

    omero_conn = conn.get_omero_connection()
    namespace = omero.constants.metadata.NSCLIENTMAPANNOTATION#pyright: ignore [reportAttributeAccessIssue, reportGeneralTypeIssues]

    done = False
    image_id = None
    rt = 1
    while not done:
        with mutex:
            retry_func(rt, conf.IMPORT_NR_OF_RETRIES)
            file_stem = Path(fileData.getConvertedFileName()).stem
            progress, log, logback_conf = setup_log_and_progress_files(file_stem)
            event_handler = FileChangeHandler(progress, progress_func)
            observer = Observer()
            observer.schedule(event_handler, path=conf.IMPORT_PROGRESS_DIR, recursive=False)
            observer.start()
            was_error = False
            #we need to catch exceptions from this and probably do a retry in some way!! !! !! !!
            try:
                image_id = ezomero.ezimport(conn=omero_conn,
                                            target=fileData.getConvertedFilePath(),
                                            dataset=dataset_id.getId(),
                                            ann=meta_dict,
                                            ns=namespace, logback=logback_conf)

                if image_id is None: #failed to import the image(s)
                    logger.warning(f"""ezomero.ezimport returned image id None.
                                        Try {rt} of {conf.IMPORT_NR_OF_RETRIES}""")
                    was_error = True

            except Exception as e:
                logger.warning(f"""ezomero.ezimport caused exception: {str(e)}.
                                        Try {rt} of {conf.IMPORT_NR_OF_RETRIES}""")
                was_error = True

            finally:
                rt += 1
                done = (not was_error) or not (was_error and  rt <= conf.IMPORT_NR_OF_RETRIES)
                observer.stop()
                observer.join()
                if (not done and was_error) or (done and not was_error):
                    for f in (progress, log, logback_conf):
                        safe_remove(f)

    #all retries done...
    if image_id is None: #failed to import the image(s)
        logger.warning("ezomero.ezimport returned image id None after all retries")
        raise ValueError(f"Failed to upload the image with ezomero after {conf.IMPORT_NR_OF_RETRIES} tries.")


    #additional tags:
    batch_tag = [str(x)+' '+str(batch_tag[x]) for x in batch_tag if batch_tag[x] != 'None']

    #add tag in the image
    for im in image_id: #in case of dual or more image in the same (generated by CD7)
        image = conn.getImage(im)

        tags = [meta_dict['Microscope'], str(meta_dict['Lens Magnification'])+"X", meta_dict['Image type']]
        tags += batch_tag
        for tag_value in tags:
            tag_value = str(tag_value)
            conn.setAnnotationOnImage(image,tag_value)

        # Add description
        if meta_dict.get('Description'):
            conn.setDescriptionOnImage(image, str(meta_dict.get('Description')))

        # Add comment
        if meta_dict.get("Comment"):
            conn.setCommentOnImage(image,meta_dict.get("Comment"))

    return image_id

#TODO: Move this function to OmeroConnection?
def check_duplicate_file(filename, dataset):
    for child in dataset.listChildren():
        if child.getName().startswith(filename):
            return True, child.getId()

    return False, None
