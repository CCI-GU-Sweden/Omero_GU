import conf
import logger
import os
import datetime
import numpy as np
import re
import xml.etree.ElementTree as ET
from dateutil import parser

from rsciio import tia, emd, mrc
from pylibCZIrw import czi as pyczi
from ome_types import model
from ome_types.model.map import M
import tifffile

#Metadata function
def dict_crawler(dictionary:dict, search_key:str, case_insensitive:bool=False, partial_search:bool=False) -> list:
    def search(d, key):
        if isinstance(d, dict):
            for k, v in d.items():
                if (case_insensitive and k.lower() == key.lower()) or \
                   (partial_search and key.lower() in k.lower()) or \
                   (k == key):
                    yield v
                if isinstance(v, (dict, list)):
                    yield from search(v, key)
        elif isinstance(d, list):
            for item in d:
                yield from search(item, key)
    
    #security check
    result = list(search(dictionary, search_key))
    if len(result) == 0:
        result.append("")
    return result


def safe_get(data, keys, default=None):
    if not isinstance(keys, (list, tuple)):
        keys = keys.split('.')
    
    for key in keys:
        if isinstance(data, list):
            if isinstance(key, int):
                if 0 <= key < len(data):
                    data = data[key]
                else:
                    return default
            else:
                return default
        elif isinstance(data, dict):
            if key in data:
                data = data[key]
            else:
                return default
        else:
            return default
    return data


def optimize_bit_depth(image):
    """
    Optimize the bit depth of an image based on its range of values.
    Converts signed integers to unsigned integers if necessary.
    
    Args:
    image (numpy.ndarray): Input image array.
    
    Returns:
    numpy.ndarray: Image with optimized bit depth (always uint).
    int: Number of bits used in the optimized image.
    """
    # Convert to uint if the input is int
    if np.issubdtype(image.dtype, np.signedinteger):
        min_val = np.min(image)
        if min_val < 0:
            image = image - min_val  # Shift values to make them non-negative
    
    max_value = np.max(image)
    
    if max_value <= 255:
        return image.astype(np.uint8), 8
    elif max_value <= 65535:
        return image.astype(np.uint16), 16
    else:
        return image.astype(np.uint32), 32


def parse_xml_to_dict(element, namespaces):
    """Recursively parse XML element into a dictionary."""
    result = {}
    
    # Loop through child elements
    for child in element:
        # Strip the namespace if present
        tag = child.tag.split('}')[-1]
        
        # If the child has children, recurse
        if list(child):
            result[tag] = parse_xml_to_dict(child, namespaces)
        else:
            # Otherwise, get the text or attributes
            result[tag] = child.text if child.text is not None else child.attrib
            
    return result

def parse_xml_with_namespaces(xml_file):
    try:
        # Parse the XML file
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Define namespaces
        namespaces = {
            '': "http://schemas.datacontract.org/2004/07/Fei.SharedObjects",
            'i': "http://www.w3.org/2001/XMLSchema-instance",
        }
        
        # Parse the root element recursively
        return parse_xml_to_dict(root, namespaces)
    
    except ET.ParseError as e:
        print(f"Parse error: {e}")
        return None


def pair_emi_ser(files: list):
    paired_files = {}
    unpaired_files = []
    pairs = 0

    # First pass: collect all EMI files
    for file in files:
        name, ext = os.path.splitext(file.filename)
        if ext.lower() == '.emi':
            paired_files[name] = {'emi': file}

    # Second pass: match SER files and handle other files
    for file in files:
        name, ext = os.path.splitext(file.filename)
        if ext.lower() == '.ser':
            # Try to find a matching EMI file
            emi_match = None
            for emi_name in paired_files.keys():
                if name.startswith(emi_name) and re.match(r'_\d+$', name[len(emi_name):]):
                    emi_match = emi_name
                    break
            
            if emi_match:
                paired_files[emi_match]['ser'] = file
                pairs += 1
            else:
                unpaired_files.append(file)
        elif ext.lower() != '.emi':  # We've already handled EMI files
            unpaired_files.append(file)

    # Move incomplete pairs to unpaired_files
    for name, pair in list(paired_files.items()):
        if len(pair) != 2:
            unpaired_files.extend(pair.values())
            del paired_files[name]
            pairs -= 1

    logger.info(f"Found {pairs} pair(s) of EMI/SER files and {len(unpaired_files)} unpaired files.")
    
    return list(paired_files.values()) + unpaired_files


def pair_mrc_xml(files: list): #list of filename
    paired_files = {}
    unpaired_files = []
    pairs = 0
    
    # First pass: collect all mrc files
    for file in files:
        if isinstance(file, dict):
            unpaired_files.append(file)
            continue
        name, ext = os.path.splitext(file.filename)
        if ext.lower() == '.mrc':
            paired_files[name] = {'mrc': file}
    
    # Second pass: match XML files
    for file in files:
        if isinstance(file, dict):
            continue
        name, ext = os.path.splitext(file.filename)
        if ext.lower() == '.xml': # Try to find a matching XML file
            mrc_match = None
            for mrc_name in paired_files.keys():
                if name == mrc_name:
                    mrc_match = mrc_name
                    break
            if mrc_match and ext.lower() == '.xml':
                paired_files[mrc_match]['xml'] = file
                pairs += 1
            else:
                unpaired_files.append(file)
                
        elif ext.lower() != '.mrc':  # We've already handled mrc files, can be jpg or the dm
            unpaired_files.append(file)
    
    # Move incomplete pairs to unpaired_files
    for name, pair in list(paired_files.items()):
        if len(pair) != 2:
            unpaired_files.extend(pair.values())
            del paired_files[name]
            pairs -= 1
    
    logger.info(f"Found {pairs} pair(s) of MRC/XML files and {len(unpaired_files)} unpaired files.")
        
    return list(paired_files.values()) + unpaired_files

def file_format_splitter(fileData, verbose:bool):
    #different strategies in case of different file format
#    if isinstance(img_path, str):
    ext = fileData.getMainFileExtension().lower()
    img_path = fileData.getMainFileTempPath()
    logger.info(f"Received file is of format {ext}")
    if ext == "czi": #Light microscope format - CarlZeissImage
        converted_path = img_path
        key_pair = get_info_metadata_from_czi(img_path, verbose=verbose)
    elif ext == "emi": #Electron microscope format
        converted_path, key_pair = convert_emi_to_ometiff(img_path, verbose=verbose)
    elif ext == "emd": #Electron microscope format
        converted_path, key_pair = convert_emd_to_ometiff(img_path, verbose=verbose)
    elif ext == "tif": #Tif, but only SEM-TIF
        converted_path, key_pair = convert_semtif_to_ometiff(img_path, verbose=verbose)
    elif ext == "mrc":
#   elif isinstance(img_path, dict): #Electron microscope format
#      logger.info(f"Received a pair of files is of format {' '.join([img_path[x].split('.')[-1].lower() for x in img_path.keys()])}")
        converted_path, key_pair = convert_atlas_to_ometiff(img_path, verbose=verbose)
    
    return converted_path, key_pair

def get_info_metadata_from_czi(img_path, verbose:bool=True) -> dict:
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
    
    try:
        with pyczi.open_czi(img_path) as czidoc:
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
        if verbose: logger.info('Metadata made with %s version %s' %(app_name, app_version))
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
            
        if verbose: logger.info('Image made on %s' %(microscope))
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
        if verbose: logger.info('Image with dimension %s and pixel size of %s' %(size, physical_pixel_sizes))
            
        # Acquisition type (not fully correct with elyra)
        acq_type = metadata['Information']['Image']['Dimensions']['Channels']['Channel']
        if isinstance(acq_type, list):
            acq_type = acq_type[0].get('ChannelType', acq_type[0].get('AcquisitionMode', None))
            if acq_type == 'Unspecified':
                acq_type = metadata['Information']['Image']['Dimensions']['Channels']['Channel'][0].get('AcquisitionMode', None)
        elif isinstance(acq_type, dict):
            acq_type = acq_type.get('AcquisitionMode', None)
        if verbose: logger.info('Image acquired with a %s mode' %(acq_type))
            
        #lens info
        lensNA = metadata['Information']['Instrument']['Objectives']['Objective'].get('LensNA', None)
        if lensNA != None: lensNA = round(float(lensNA), 2)
        lensMag = metadata['Information']['Instrument']['Objectives']['Objective'].get('NominalMagnification', None)
        if lensMag != None: lensMag = int(lensMag)
        if verbose: logger.info('Objective lens used has a magnification of %s and a NA of %s' %(lensMag, lensNA))
            
        #processing (if any)
        processing = metadata['Information'].get('Processing', None)
        if processing is not None:
            pre_processed = list(processing.keys())
        if verbose: logger.info('Image preprocessed with %s' %(pre_processed))
            
        #other
        comment = metadata['Information']['Document'].get('Comment', None)
        description = metadata['Information']['Document'].get('Description', None)
        # creation_date = metadata['Information']['Document'].get('CreationDate', None)
        date_object = parser.isoparse(metadata['Information']['Document'].get('CreationDate', None))
        if verbose: logger.info('Image\n    Comment: %s,\n    Description: %s,\n    Creation date: %s' % (comment, description, creation_date))
           
    if verbose: logger.info("_"*25)
    
    mini_metadata = {'Microscope':microscope,
                     'Lens Magnification': lensMag,
                     'Lens NA': lensNA,
                     'Image type':acq_type,
                     'Physical pixel size':physical_pixel_sizes,
                     'Image Size':size,
                     'Comment':comment,
                     'Description':description,
                     'Acquisition date':date_object.strftime(conf.DATE_TIME_FMT),
                     }
    # Unpack Physical pixel size
    for axis, value in physical_pixel_sizes.items():
        mini_metadata[f'Physical pixel size {axis}'] = value
    
    # Unpack Image Size
    for axis, value in size.items():
        mini_metadata[f'Image Size {axis[-1]}'] = value
    
    del mini_metadata['Physical pixel size']
    del mini_metadata['Image Size']
    
    return mini_metadata       


def convert_emi_to_ometiff(img_path: str, verbose: bool=True):
    """
    Convert .emi file to ome-tiff format.
    File NEED to finish with emi. A ser file need to be present in the same folder
    
    Args:
    img_path (str): Path to the .emi file
    
    Returns:
    str: Path to the output OME-TIFF file
    dict: Contains the key-pair values
    """
            
    if verbose: logger.info(f"Conversion to ometiff from emi required for {img_path}")
    
    try:
        data = tia.file_reader(img_path) #Required to pair the emi and ser file!
        
        if len(data) == 1:
            data = data[0]
        else:
            raise ValueError(f"Length of data at {len(data)} different of 1.")
        
        img_array = data['data']
        # img_array = img_array[ :, :, np.newaxis, np.newaxis, np.newaxis,]
        dimension_order = "XYCZT"
    except FileNotFoundError:
        raise FileNotFoundError("The file does not exist.")
    except Exception as e:
        raise ValueError(f"Error opening or reading metadata: {str(e)}")
    
    if verbose: logger.info(f"{img_path} successfully readen!")
    # img_array = img_array[np.newaxis, :, :]
    
    # Check if this is possible to reduce its bit size
    img_array, bit = optimize_bit_depth(img_array)
    
    key_pair = {
        'Microscope': dict_crawler(data, 'Microscope')[0],
        'Electron source': dict_crawler(data, 'Gun type')[0],
        'Beam tension': dict_crawler(data, 'High tension', partial_search=True)[0],
        'Camera': dict_crawler(data, 'CameraName', partial_search=True)[0],
        'Lens Magnification': dict_crawler(data, 'Magnification_x')[0],
        'Pixel size': dict_crawler(data, 'scale')[0],
        'Pixel unit': dict_crawler(data, 'units')[0],
        'Comment': dict_crawler(data, 'Comment')[0],
        'Defocus': dict_crawler(data, 'Defocus', partial_search=True)[0],
        'Image type': dict_crawler(data, 'Mode')[0],
        'Image Size X':dict_crawler(data, 'DetectorPixelHeight')[0],
        'Image Size Y':dict_crawler(data, 'DetectorPixelWidth')[0],
    }

    date_object = datetime.datetime.strptime(dict_crawler(data, 'AcquireDate')[0], '%a %b %d %H:%M:%S %Y')
    key_pair['Acquisition date'] = date_object.strftime(conf.DATE_TIME_FMT)
    
    #extra pair for the general metadata
    extra_pair = {
        'User': dict_crawler(data, 'User')[0],
        'Wehnelt index': dict_crawler(data, 'Wehnelt index')[0],
        'Mode': dict_crawler(data, 'Mode')[0],
        'Defocus': dict_crawler(data, 'Defocus', partial_search=True)[0],
        'Intensity': dict_crawler(data, 'Intensity', partial_search=True)[0],
        'Objective lens': dict_crawler(data, 'Objective lens', partial_search=True)[0],
        'Diffraction lens': dict_crawler(data, 'Diffraction lens', partial_search=True)[0],
        'Stage X': dict_crawler(data, 'Stage X', partial_search=True)[0],
        'Stage Y': dict_crawler(data, 'Stage Y', partial_search=True)[0],
        'Stage Z': dict_crawler(data, 'Stage Z', partial_search=True)[0],
        'C2 Aperture': dict_crawler(data, 'C2 Aperture', partial_search=True)[0],
        'OBJ Aperture': dict_crawler(data, 'OBJ Aperture', partial_search=True)[0],
        'Filter mode': dict_crawler(data, 'Filter mode')[0],
        'Comment': key_pair['Comment'],
        }
    
    if verbose: logger.info("Metadata extracted")
    # Create an OME object
    ome = model.OME()
    
    # Create an Image object
    image = model.Image(
        id="Image:0",
        name=os.path.basename(img_path),
        acquisition_date=date_object.strftime(conf.DATE_TIME_FMT),
        
        pixels = model.Pixels(
            id="Pixels:0",
            dimension_order=dimension_order,
            type=str(img_array.dtype),
            size_x=key_pair['Image Size X'],
            size_y=key_pair['Image Size Y'],
            size_c=1,
            size_z=1,
            size_t=1,
            physical_size_x=key_pair['Pixel size'],
            physical_size_x_unit=key_pair['Pixel unit'],
            physical_size_y=key_pair['Pixel size'],
            physical_size_y_unit=key_pair['Pixel unit'],
        )
    )
    
    
    # Add Image to OME
    ome.images.append(image)
    
    # Create MapAnnotation for custom metadata
    custom_metadata = model.MapAnnotation(
        id="Annotation:0",
        namespace="custom.ome.metadata",
        value=model.Map(ms=[M(k=_key, value=str(_value)) for _key, _value in extra_pair.items()])
        
    )
    
    # Add Instrument information
    instrument = model.Instrument(
        id = "Instrument:0",
        microscope=model.Microscope(
                                    type='Other',
                                    manufacturer=dict_crawler(data, 'Manufacturer')[0],
                                    model=key_pair['Microscope']
        ),
        detectors=[
            model.Detector(
                id="Detector:0",
                model=key_pair['Electron source'],
                voltage=key_pair['Beam tension'],
                voltage_unit=model.UnitsElectricPotential('kV'),
                ),
            model.Detector(
                id="Detector:1",
                model=key_pair['Camera'],
                ),
            ]
        )
    
    ome.instruments.append(instrument)
    ome.structured_annotations.extend([custom_metadata])
    # Create Objective for Magnification
    objective = model.Objective(
        id="Objective:0",
        nominal_magnification=float(key_pair['Lens Magnification'])
    )
    instrument.objectives.append(objective)
    
    # Convert OME object to XML string
    ome_xml = ome.to_xml()
    if verbose: logger.info("OME created")
    
    output_fpath = os.path.join(os.path.dirname(img_path), os.path.basename(img_path).replace(".emi", ".ome.tiff"))   
    
    # Write OME-TIFF file
    with tifffile.TiffWriter(output_fpath) as tif:
        tif.write(img_array, description=ome_xml, metadata={'axes': 'YX',})
    
    if verbose: logger.info(f"Ome-tiff written at {output_fpath}.")
    
    return output_fpath, key_pair


def convert_emd_to_ometiff(img_path: str, verbose:bool=True):
    """
    Convert .emd file to ome-tiff format.
    
    Args:
    img_path (str): Path to the .emd file
    
    Returns:
    str: Path to the output OME-TIFF file
    dict: Contains the key-pair values
    """
    if verbose: logger.info(f"Conversion to ometiff from emd required for {img_path}")
    
    try:
        img = emd.file_reader(img_path)[0]
        img_array, bitdepth = optimize_bit_depth(img['data'])
    except FileNotFoundError:
        raise FileNotFoundError("The file does not exist.")
    except Exception as e:
        raise ValueError(f"Error opening or reading metadata: {str(e)}")
        
    data = img['original_metadata']
    if verbose: logger.info(f"{img_path} successfully readen!")  

    key_pair = {
        'Microscope': dict_crawler(data, 'InstrumentModel')[0],
        'Electron source': dict_crawler(data, 'SourceType')[0],
        'Beam tension': dict_crawler(data, 'AccelerationVoltage')[0],
        'Camera': dict_crawler(data, 'DetectorName')[0],
        'Lens Magnification': dict_crawler(data, 'NominalMagnification')[0],
        'Physical pixel size': dict_crawler(data, 'PixelSize')[0]['width'],
        'Physical pixel unit': dict_crawler(data, 'PixelUnitX')[0],
        'Defocus': dict_crawler(data, 'Defocus')[0],
        'Image Size X':dict_crawler(data, 'ImageSize')[0]['width'],
        'Image Size Y':dict_crawler(data, 'ImageSize')[0]['height'],
    }
    
    date_object = datetime.datetime.fromtimestamp(int(dict_crawler(data, 'AcquisitionDatetime')[0]['DateTime']))
    key_pair['Acquisition date'] = date_object.strftime(conf.DATE_TIME_FMT)
    mode = dict_crawler(data, 'TemOperatingSubMode')[0]+' '
    mode += dict_crawler(data, 'ObjectiveLensMode')[0]+' '
    mode += dict_crawler(data, 'HighMagnificationMode')[0]+' '
    key_pair['Image type'] = mode
    
    #extra pair for the general metadata        
    extra_pair = {
        'Mode': mode,
        'Defocus': dict_crawler(data, 'Defocus', partial_search=True)[0],
        'Lens intensity': dict_crawler(data, 'C2LensIntensity')[0],
        'Objective lens': dict_crawler(data, 'ObjectiveLensIntensity')[0],
        'Diffraction lens': dict_crawler(data, 'DiffractionLensIntensity')[0],
        'Tilt': dict_crawler(data, 'AlphaTilt')[0],
        'Stage X': dict_crawler(data, 'Position')[0]['x'],
        'Stage Y': dict_crawler(data, 'Position')[0]['y'],
        'Stage Z': dict_crawler(data, 'Position')[0]['z'],
        'C2 Aperture': dict_crawler(data, 'Aperture[C2].Name')[0]['value'],
        'OBJ Aperture': dict_crawler(data, 'Aperture[OBJ].Name')[0]['value'],
        'Filter mode': dict_crawler(data, 'EntranceApertureType')[0],
        }
    
    if verbose: logger.info("Metadata extracted")
    # Create an OME object
    ome = model.OME()
    
    # Create an Image object
    image = model.Image(
        id="Image:0",
        name=os.path.basename(img_path),
        acquisition_date=date_object.strftime(conf.DATE_TIME_FMT),
        
        pixels = model.Pixels(
            id="Pixels:0",
            dimension_order="XYCZT",
            type=str(img_array.dtype),
            size_x=key_pair['Image Size X'],
            size_y=key_pair['Image Size Y'],
            size_c=1,
            size_z=1,
            size_t=1,
            physical_size_x=key_pair['Physical pixel size'],
            physical_size_x_unit=key_pair['Physical pixel unit'],
            physical_size_y=key_pair['Physical pixel size'],
            physical_size_y_unit=key_pair['Physical pixel unit'],
        )
    )
    
    # Add Image to OME
    ome.images.append(image)
    
    # Create MapAnnotation for custom metadata
    custom_metadata = model.MapAnnotation(
        id="Annotation:0",
        namespace="custom.ome.metadata",
        value=model.Map(ms=[M(k=_key, value=str(_value)) for _key, _value in extra_pair.items()])
        
    )
    
    # Add Instrument information
    instrument = model.Instrument(
        id = "Instrument:0",
        microscope=model.Microscope(
                                    type='Other',
                                    manufacturer=dict_crawler(data, 'Manufacturer')[0],
                                    model=key_pair['Microscope']
        ),
        detectors=[
            model.Detector(
                id="Detector:0",
                model=key_pair['Electron source'],
                voltage=key_pair['Beam tension'],
                voltage_unit=model.UnitsElectricPotential('kV'),
                ),
            model.Detector(
                id="Detector:1",
                model=key_pair['Camera'],
                ),
            ]
        )
    
    ome.instruments.append(instrument)
    ome.structured_annotations.extend([custom_metadata])
    # Create Objective for Magnification
    objective = model.Objective(
        id="Objective:0",
        nominal_magnification=float(key_pair['Lens Magnification'])
    )
    instrument.objectives.append(objective)
    
    # Convert OME object to XML string
    ome_xml = ome.to_xml()
    if verbose: logger.info("OME created")
    
    output_fpath = os.path.join(os.path.dirname(img_path), os.path.basename(img_path).replace(".emd", ".ome.tiff"))
    
    # Write OME-TIFF file
    with tifffile.TiffWriter(output_fpath) as tif:
        tif.write(img_array, description=ome_xml, metadata={'axes': 'YX',})
        
    if verbose: logger.info(f"Ome-tiff written at {output_fpath}.")
    return output_fpath, key_pair


def convert_atlas_to_ometiff(img_path: dict, verbose:bool=False):
    """
    Convert atlas file (TEM likely MAPS), which is a pair of mrc and xml, to ome-tiff format.
    
    Args:
    img_path (dict): containing the path for the mrc and xml file
    
    Returns:
    str: Path to the output OME-TIFF file
    dict: Contains the key-pair values
    """
    if verbose: logger.info(f"Conversion to ometiff from mrc required for {img_path}")

    try:
        full_data = mrc.file_reader(img_path['mrc'])[0]
        img_array, bit = optimize_bit_depth(full_data['data'])
    except FileNotFoundError:
        raise FileNotFoundError("The file does not exist.")
    except Exception as e:
        logger.info(f"An error happened when trying to read the atlas file {img_path}\n It is required to be a dict: {e}")
        raise
    
    data = parse_xml_with_namespaces(img_path.get('xml', None))
    if data is None:
        raise ValueError("Error opening or reading metadata.")
    if verbose: logger.info(f"{img_path} successfully readen!") 
    
    key_pair = {
        'Microscope': dict_crawler(data, 'InstrumentModel')[0].split('-')[0],
        'Electron source': dict_crawler(data, 'Sourcetype')[0],
        'Beam tension': dict_crawler(data, 'AccelerationVoltage')[0],
        'Camera': safe_get(dict_crawler(data, 'camera')[0], ['Name']),
        'Lens Magnification': dict_crawler(data, 'NominalMagnification')[0],
        'Physical pixel size': safe_get(dict_crawler(data, 'pixelSize')[0], ['x', 'numericValue']),
        'Physical pixel unit': safe_get(dict_crawler(data, 'pixelSize')[0], ['x', 'unit', '_x003C_Symbol_x003E_k__BackingField']),
        'Defocus': dict_crawler(data, 'Defocus')[0],
        'Image Size X': img_array.shape[0],
        'Image Size Y': img_array.shape[1],
    }
    date_object = parser.isoparse(dict_crawler(data, 'acquisitionDateTime')[0])
    key_pair['Acquisition date'] = date_object.strftime(conf.DATE_TIME_FMT)
    
    mode = dict_crawler(data, 'ColumnOperatingMode')[0]+' '
    mode += dict_crawler(data, 'ColumnOperatingTemSubMode')[0]+' '
    mode += dict_crawler(data, 'ObjectiveLensMode')[0]+' '
    mode += dict_crawler(data, 'ProbeMode')[0]+' '
    mode += dict_crawler(data, 'ProjectorMode')[0]+' '
    key_pair['Image type'] = mode
    
    #extra pair for the general metadata        
    extra_pair = {
        'Mode': mode,
        'Defocus': dict_crawler(data, 'Defocus',)[0],
        'Lens intensity': dict_crawler(data, 'Intensity')[0],
        'Tilt': safe_get(dict_crawler(data, 'stage')[0], ['Position', 'A']),
        'Stage X': safe_get(dict_crawler(data, 'stage')[0], ['Position', 'X']),
        'Stage Y': safe_get(dict_crawler(data, 'stage')[0], ['Position', 'Y']),
        'Stage Z': safe_get(dict_crawler(data, 'stage')[0], ['Position', 'Z']),
        }
    
    # Create an OME object
    ome = model.OME()
    
    # Create an Image object
    image = model.Image(
        id="Image:0",
        name = os.path.basename(img_path['mrc']),
        acquisition_date=date_object.strftime(conf.DATE_TIME_FMT),
        
        pixels = model.Pixels(
            id="Pixels:0",
            dimension_order="XYCZT",
            type=str(img_array.dtype),
            size_x=key_pair['Image Size X'],
            size_y=key_pair['Image Size Y'],
            size_c=1,
            size_z=1,
            size_t=1,
            physical_size_x=key_pair['Physical pixel size'],
            physical_size_x_unit=key_pair['Physical pixel unit'],
            physical_size_y=key_pair['Physical pixel size'],
            physical_size_y_unit=key_pair['Physical pixel unit'],
        )
    )
    
    # Add Image to OME
    ome.images.append(image)
    
    # Create MapAnnotation for custom metadata
    custom_metadata = model.MapAnnotation(
        id="Annotation:0",
        namespace="custom.ome.metadata",
        value=model.Map(ms=[M(k=_key, value=str(_value)) for _key, _value in extra_pair.items()])
        
    )
    
    # Add Instrument information
    instrument = model.Instrument(
        id = "Instrument:0",
        microscope=model.Microscope(
                                    type='Other',
                                    model=key_pair['Microscope']
        ),
        detectors=[
            model.Detector(
                id="Detector:0",
                model=key_pair['Electron source'],
                voltage=key_pair['Beam tension'],
                voltage_unit=model.UnitsElectricPotential('kV'),
                ),
            model.Detector(
                id="Detector:1",
                model=key_pair['Camera'],
                ),
            ]
        )
    
    ome.instruments.append(instrument)
    ome.structured_annotations.extend([custom_metadata])
    # Create Objective for Magnification
    objective = model.Objective(
        id="Objective:0",
        nominal_magnification=float(key_pair['Lens Magnification'])
    )
    instrument.objectives.append(objective)
    
    # Convert OME object to XML string
    ome_xml = ome.to_xml()
    if verbose: logger.info("OME created")
    
    output_fpath = os.path.join(os.path.dirname(img_path['mrc']), os.path.basename(img_path['mrc']).replace(".mrc", ".ome.tiff"))
    
    # Write OME-TIFF file
    with tifffile.TiffWriter(output_fpath) as tif:
        tif.write(img_array, description=ome_xml, metadata={'axes': 'YX',})
        
    if verbose: logger.info(f"Ome-tiff written at {output_fpath}.")
    return output_fpath, key_pair


def convert_semtif_to_ometiff(img_path: str, verbose:bool=False):
    """
    Convert SEM TIF file to ome-tiff format.
    
    Args:
    img_path (str): containing the path for the tif file
    
    Returns:
    str: Path to the output OME-TIFF file
    dict: Contains the key-pair values
    """
    if verbose: logger.info(f"Conversion to ometiff from tif required for {img_path}")
    try:
        with tifffile.TiffFile(img_path) as tif:
            cz_sem_metadata = dict(tif.pages[0].tags.get(34118).value)
            
            if verbose: logger.info(f"{img_path} metadata successfully readen!") 
            
            if cz_sem_metadata is None:
                raise TypeError("Image may be a tif, but not a SEM-TIF or metadata failed to be read")
            
            img_array = tif.asarray()
            if verbose: logger.info(f"{img_path} data successfully readen!") 
                               
            key_pair = {
            'Microscope': dict_crawler(cz_sem_metadata, 'dp_sem')[0][1],
            'Image type':dict_crawler(cz_sem_metadata, 'dp_final_lens')[0][1],
            'Lens Magnification': convert_magnification(dict_crawler(cz_sem_metadata, 'ap_mag')[0][1]),
            'WD value': dict_crawler(cz_sem_metadata, 'ap_wd')[0][1],
            'WD unit': dict_crawler(cz_sem_metadata, 'ap_wd')[0][2],
            'EHT value': dict_crawler(cz_sem_metadata, 'ap_actualkv')[0][1],
            'EHT unit': dict_crawler(cz_sem_metadata, 'ap_actualkv')[0][2],
            'I Probe value': dict_crawler(cz_sem_metadata, 'ap_iprobe')[0][1],
            'I Probe unit': dict_crawler(cz_sem_metadata, 'ap_iprobe')[0][2],
            'Signal A' : dict_crawler(cz_sem_metadata, 'dp_detector_channel')[0][1],
            'Signal B': dict_crawler(cz_sem_metadata, 'dp_implied_detector')[0][1],
            'Mixing' : dict_crawler(cz_sem_metadata, 'dp_mixing')[0][1],
            'Mixing proportion' : dict_crawler(cz_sem_metadata, 'ap_k2')[0][1],
            'Scan speed': dict_crawler(cz_sem_metadata, 'dp_scanrate')[0][1],
            'Dwell time value': dict_crawler(cz_sem_metadata, 'dp_dwell_time')[0][1],
            'Dwell time unit': dict_crawler(cz_sem_metadata, 'dp_dwell_time')[0][2],
            'Line Avg.Count': dict_crawler(cz_sem_metadata, 'ap_line_average_count')[0][1],
            'Vacuum Mode': dict_crawler(cz_sem_metadata, 'dp_vac_mode')[0][1],
            'Mag': dict_crawler(cz_sem_metadata, 'ap_mag')[0][1],
            'Mag Range': dict_crawler(cz_sem_metadata, 'dp_mag_range')[0][1],
            'Image Size X' : int(dict_crawler(cz_sem_metadata, 'dp_image_store')[0][1].split(' * ')[0]),
            'Image Size Y' : int(dict_crawler(cz_sem_metadata, 'dp_image_store')[0][1].split(' * ')[1]),
            'Physical pixel size': dict_crawler(cz_sem_metadata, 'ap_image_pixel_size')[0][1],
            'Physical pixel unit':dict_crawler(cz_sem_metadata, 'ap_image_pixel_size')[0][2],
            'Image depth': tif.pages[0].tags.get(258).value,
            'Comment': dict_crawler(cz_sem_metadata, 'sv_user_text')[0][1],
            }
                
            date = dict_crawler(cz_sem_metadata, 'ap_date')[0][1]
            time = dict_crawler(cz_sem_metadata, 'ap_time')[0][1]
            
            date_object = datetime.datetime.strptime(date+' '+time, "%d %b %Y %H:%M:%S")
            key_pair['Acquisition date'] = date_object.strftime(conf.DATE_TIME_FMT)
                                                  
            # Create an OME object
            ome = model.OME()
            
            # Create an Image object
            image = model.Image(
                id="Image:0",
                name = os.path.basename(img_path),
                acquisition_date=date_object.strftime(conf.DATE_TIME_FMT),
                
                pixels = model.Pixels(
                    id="Pixels:0",
                    dimension_order="XYCZT",
                    type=str(img_array.dtype),
                    size_x=key_pair['Image Size X'],
                    size_y=key_pair['Image Size Y'],
                    size_c=1,
                    size_z=1,
                    size_t=1,
                    physical_size_x=key_pair['Physical pixel size'],
                    physical_size_x_unit=key_pair['Physical pixel unit'],
                    physical_size_y=key_pair['Physical pixel size'],
                    physical_size_y_unit=key_pair['Physical pixel unit'],
                )
            )
            
            # Add Image to OME
            ome.images.append(image)
            
            # Create MapAnnotation for custom metadata
            custom_metadata = model.MapAnnotation(
                id="Annotation:0",
                namespace="custom.ome.metadata",
                value=model.Map(ms=[M(k=safe_encode(_key), value=safe_encode(_value)) for _key, _value in cz_sem_metadata.items()])
            )
            
            # Add Instrument information
            instrument = model.Instrument(
                id = "Instrument:0",
                microscope=model.Microscope(
                                            type='Other',
                                            model=key_pair['Microscope']
                ),
                detectors=[
                    model.Detector(
                        id="Detector:0",
                        voltage=key_pair['EHT value'],
                        voltage_unit=model.UnitsElectricPotential(key_pair['EHT unit']),
                        ),
                    ]
                )
            
            ome.instruments.append(instrument)
            ome.structured_annotations.extend([custom_metadata])
            # Create Objective for Magnification
            objective = model.Objective(
                id="Objective:0",
                nominal_magnification=float(key_pair['Lens Magnification'])
            )
            instrument.objectives.append(objective)
            
            # Convert OME object to XML string
            ome_xml = ome.to_xml()
            if verbose: logger.info("OME created")
            
            output_fpath = os.path.join(os.path.dirname(img_path), os.path.basename(img_path).replace(".tif", ".ome.tiff"))
            
            # Write OME-TIFF file
            with tifffile.TiffWriter(output_fpath) as tif:
                tif.write(img_array, description=ome_xml, metadata={'axes': 'YX',})
                
            if verbose: logger.info(f"Ome-tiff written at {output_fpath}.")
            
            return output_fpath, key_pair
        
    except FileNotFoundError:
        raise FileNotFoundError("The file does not exist.")

def convert_magnification(mag_str):
    """Convert magnification string like '81.20 K X' to a real number."""
    
    # Extract numeric part and unit using regex
    match = re.match(r"([\d\.]+)\s*([KMG]?)\s*X", mag_str, re.IGNORECASE)
    
    if not match:
        raise ValueError(f"Invalid magnification format: {mag_str}")
    
    value, unit = match.groups()
    value = float(value)  # Convert string to float
    
    # Scale based on unit
    multiplier = {"": 1, "K": 1e3, "M": 1e6, "G": 1e9}
    
    return value * multiplier.get(unit.upper(), 1)

def safe_encode(value):
    """Convert values to safe string representation, handling non-ASCII and tuple/list."""
    if isinstance(value, (tuple, list)):
        # Convert nested tuples and lists by recursively processing all items
        return "(" + ", ".join(safe_encode(item) for item in value) + ")"
    
    elif isinstance(value, bool):
        # Convert bool to 'True'/'False' strings
        return str(value)
    
    elif isinstance(value, (int, float)):
        # Convert int/float to string
        return str(value)
    
    elif isinstance(value, str):
        #hard code some conversion
        if '\xb5' in value: value = value.replace('\xb5', 'micron')
        elif '\xb0' in value: value = value.replace('\xb0', 'degree')
        elif '\xb2' in value: value = value.replace('\xb2', '^')
        # Try encoding to ASCII first, fallback to UTF-8 if needed
        try:
            # Check for non-ASCII and raise an error to trigger the fallback
            value.encode('ascii')
        except UnicodeEncodeError:
            # If encoding fails, try UTF-8 encoding
            value = value.encode('utf-8').decode('utf-8')
        
        return value
    
    return str(value)  # Ensure everything else (e.g., None) is converted to string


def delete(file_path:str):
    if os.path.exists(file_path):
        os.remove(file_path)
        logger.info(f"Successfully deleted temporary file: {file_path}")
    else:
        logger.warning(f"Temporary file not found for deletion: {file_path}")
