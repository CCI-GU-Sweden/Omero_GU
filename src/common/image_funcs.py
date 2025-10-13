"""
Large function that extract key-value pairs from metadata and/or convert image file to ome-tiff

require a file data object

NEED to return a list of path/str AND a key-value pair dictionnary

What minimum entries does the key-value pair dictionnary need?
    assert('Image Size X' in meta_dict)
    assert('Image Size Y' in meta_dict)
    assert('Acquisition date' in meta_dict)
    assert('Physical pixel size X' in meta_dict)
    assert('Physical pixel size Y' in meta_dict)
    assert('Microscope' in meta_dict)
"""

import os
import math
import datetime
import re
import json
from dateutil import parser
from pathlib import Path
from rsciio import tia, emd, mrc
import numpy as np
import tifffile
import xml.etree.ElementTree as ET
from ome_types import model
from ome_types.model import Microscope_Type, Pixels_DimensionOrder

from ome_types.model import Map
from ome_types.model.simple_types import PixelType, UnitsLength
from common import conf
from common import logger
from common.file_data import FileData
from omerofrontend.exceptions import MetaDataError, ImageNotSupported
from typing import Dict, Any

#Let's use the czi tools to extract the metadata
from pylibCZIrw import czi as pyczi
from czitools.read_tools import read_tools
from aicspylibczi import CziFile #required for the planetable

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

def _sanitize_meta(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        # drop null-ish
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        # stringify complex types
        if isinstance(v, (dict, list, set, tuple)):
            try:
                out[k] = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                out[k] = str(v)
        else:
            out[k] = str(v) if not isinstance(v, (str, int, float, bool)) else v
    return out

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

def choose_levels(y, x, target_min=1024):
    # include the full-res level in the count
    L = 1 + max(0, math.ceil(math.log2(max(y, x) / target_min)))
    return max(int(L), 1)

def write_tiff_pyramid(out_file:str,
                       array, 
                       ome_xml,
                       metadata,
                       pxl_size:tuple,
                       subresolutions:int,
                       extra_tags: list = [()],
                       tile: tuple = (512, 512),
                       worker_n:int = 2
                       ):
    """
    Write a tif pyramid on disk.

    Args:
        - out_file: str
            output file path. str.
        - array: np.array
            input image data
        - ome_xml: str or None
            input OME-XML
        - metadata: dict or None
            input metadata
        - pxl_size: tuple
            pixel size (x,y)
        - subresolutions: int
            number of pyramid levels to create
        :param extra_tags: list of tuples. Default is [()]. follow convention: tagid (int), type ("s"), start(0), xml_text, False
        :param tile: size of tiles to generate. Default is (512, 512)
        :param worker_n: number of workers to use when writing the file. Default is 2.

    Returns:
        None
    """
    pxlx_size, pxly_size = pxl_size[0], pxl_size[1]
 
    if ome_xml:
        with tifffile.TiffWriter(out_file, bigtiff=True) as tif:
            tif.write(
                array,
                subifds=subresolutions-1,
                description=ome_xml,
                resolution=(pxlx_size, pxly_size),
                photometric="minisblack",
                extratags=extra_tags if len(extra_tags[0])>0 else None,
                tile=tile,
                maxworkers=worker_n,
            )
            
            for level in range(1, subresolutions):
                mag = 2 ** level
                tif.write(
                    array[..., ::mag, ::mag],
                    resolution=(pxlx_size*(2**level), pxly_size*(2**level)),
                    subfiletype=1,
                    photometric="minisblack",
                    compression="zlib",
                    predictor=True,
                    tile=tile,
                    maxworkers=worker_n,
                )
    
    elif metadata:
        # Convert µm/px -> pixels per centimeter
        px_cm = pxlx_size * 1e-4
        py_cm = pxly_size * 1e-4
        xres0 = 1.0 / px_cm
        yres0 = 1.0 / py_cm

        with tifffile.TiffWriter(out_file, bigtiff=True) as tif:
            tif.write(
                array,
                subifds=subresolutions-1,
                metadata=metadata,
                resolution=(xres0, yres0),
                resolutionunit="CENTIMETER",
                extratags=extra_tags,
                photometric="minisblack",
                tile=tile,
                maxworkers=worker_n,
            )
            
            for level in range(1, subresolutions):
                mag = 2 ** level
                tif.write(
                    array[..., ::mag, ::mag],
                    subfiletype=1,
                    resolution=(xres0/mag, yres0/mag),
                    resolutionunit="CENTIMETER",
                    photometric="minisblack",
                    compression="zlib",
                    predictor=True,
                    tile=tile,
                    maxworkers=worker_n,
                )
    

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
        logger.error(f"XML parse error: {e}")
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
    """
    This function pairs the .mrc and .xml files. The pairing is done by matching
    the name of the .xml file with the corresponding .mrc file.
    
    Args:
        files (list): List of filenames, including both .mrc and .xml files.

    Returns:
        list: A list of paired files and unpaired files.
    """
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

def mapping(microscope):
    #Map potential name to the more convential name
    micro_mapping = {#LM
                     '2842001059':'LSM 980',
                     'LSM 880, AxioObserver':'LSM 880',
                     'LSM 710, Axio Examiner': 'LSM 710',
                     'LSM 700, AxioObserver': 'LSM 700',
                     'Celldiscoverer 7':'CD7',
                     '4652000027-1': 'CD7',
                     'Elyra 7 DUOLINK':'Elyra 7',
                     'Axio Imager.Z2':'Imager',
                     'Axio Observer.Z1 / 7':'Observer',
                     #EM
                     'TALOS': 'Talos L120C',
                     'Talos': 'Talos L120C',
                     'Microscope TalosL120C 120 kV D5838 CryoTwin':'Talos L120C',
                     'i':'Talos L120C',
                     'Gemini':'Gemini SEM 450',
                     'GeminiSEM 450':'Gemini SEM 450',
                     #Other
                     None:'Undefined',
                     }
    
    if microscope in micro_mapping.keys():
        microscope = micro_mapping[microscope]
    
    return microscope

def get_info_metadata_from_czi(img_path : Path) -> dict:
    """
    Extract important metadata from a CZI image file.
    
    This function opens a CZI image file, reads its metadata, and extracts
    specific information such as microscope details, lens properties,
    image type, pixel size, image dimensions, and other relevant metadata.
    
    Args:
        img_path : The file path to the CZI image.
    
    Returns:
        ImageMetadata: A dictionnary containing the extracted metadata.
    
    Raises:
        FileNotFoundError: If the specified image file does not exist.
        ValueError: If the file is not a valid CZI image or if metadata extraction fails.
    """
    
    if not img_path.exists():
        raise FileNotFoundError(f"The file {img_path} does not exist.")
    
    try:
        with pyczi.open_czi(str(img_path)) as czidoc:
            metadata = czidoc.metadata['ImageDocument']['Metadata']
    except Exception as e:
        logger.error(f"Error opening or reading metadata: {str(e)}")
        raise ValueError(f"Error opening or reading metadata: {img_path}")

           
    #Initialization
    app_name = None
    app_version = None
    microscope = None
    acq_type = None
    lensNA = None
    lensMag = None
    pre_processed = None
    comment = None
    description = None
    creation_date = None
                                
    #grab the correct version of the metadata
    app = metadata['Information'].get('Application', None)
    if app is not None: #security check
        app_name = app['Name']
        app_version = app['Version']
        logger.debug('Metadata made with %s version %s' %(app_name, app_version))
        #Another way will be to grab the IP address of the room and map it
        #microscope name, based on the version of the metadata
        if 'ZEN' in app['Name'] and app['Version'].startswith("3."): #CD7, 980, Elyra
            microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('UserDefinedName', None)
            if microscope is None:
                microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('@Name', None)
            if microscope is None:
                microscope = metadata['Scaling']['AutoScaling'].get('CameraName', None)

        elif 'ZEN' in app['Name'] and app['Version'].startswith("2.6"): #Observer, Imager
            microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('@Name', None)
            
        elif 'AIM' in app['Name']: #700, 880, 710
            microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('System', None)

        microscope = mapping(microscope)
            
        logger.debug('Image made on %s' %(microscope))
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
        logger.debug('Image with dimension %s and pixel size of %s' %(size, physical_pixel_sizes))
            
        # Acquisition type (not fully correct with elyra)
        acq_type = metadata['Information']['Image']['Dimensions']['Channels']['Channel']
        if isinstance(acq_type, list):
            acq_type = acq_type[0].get('ChannelType', acq_type[0].get('AcquisitionMode', None))
            if acq_type == 'Unspecified':
                acq_type = metadata['Information']['Image']['Dimensions']['Channels']['Channel'][0].get('AcquisitionMode', None)
        elif isinstance(acq_type, dict):
            acq_type = acq_type.get('AcquisitionMode', None)
        logger.debug('Image acquired with a %s mode' %(acq_type))
            
        #lens info
        lensNA = metadata['Information']['Instrument']['Objectives']['Objective'].get('LensNA', None)
        if lensNA is not None: 
            lensNA = round(float(lensNA), 2)
        lensMag = metadata['Information']['Instrument']['Objectives']['Objective'].get('NominalMagnification', None)
        if lensMag is not None: 
            lensMag = int(lensMag)
        logger.debug('Objective lens used has a magnification of %s and a NA of %s' %(lensMag, lensNA))
            
        #processing (if any)
        processing = metadata['Information'].get('Processing', None)
        if processing is not None:
            pre_processed = list(processing.keys())
            logger.debug('Image preprocessed with %s' %(pre_processed))
            
        #other
        comment = metadata['Information']['Document'].get('Comment', None)
        description = metadata['Information']['Document'].get('Description', None)
        #creation_date = metadata['Information']['Document'].get('CreationDate', None)
        date_object = parser.isoparse(metadata['Information']['Document'].get('CreationDate', None))
        creation_date = date_object.strftime(conf.DATE_TIME_FMT)
        logger.debug(
                        f"Image\n    Comment: {comment if comment else 'No comment'},\n" 
                        f"Description: {description if description else 'No description'},\n"
                        f"Creation date: {creation_date if creation_date else 'No creation date'}"
                    )    
    else:
        return {}
         
    logger.debug("_"*25)
    
    mini_metadata = {'Microscope':microscope,
                     'Lens Magnification': lensMag,
                     'Lens NA': lensNA,
                     'Image type':acq_type,
                     'Physical pixel size':physical_pixel_sizes,
                     'Image Size':size,
                     'Comment':comment,
                     'Description':description,
                     'Acquisition date': creation_date,
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

def pixel_type_to_ome(string:str):
    if string == "Gray8":
        return PixelType.UINT8.value
    elif string == "Gray16":
        return PixelType.UINT16.value
    elif string == "Gray32Float":
        return PixelType.FLOAT.value
    
def unit_converter(string:str):
    if string == "nanometer":
        return UnitsLength.NANOMETER.value
    else: #assume it is ok
        return string
    #TODO add other units

def ome_extraction(full_metadata, output_name, scene_idx) -> model.OME:
    """
    Extract OME metadata from the full_metadata object obtained from a CZI file. Read the subblock using aicsczi to get the plane information..
    Confirmed to work with Zeiss LSM 700 and 710 files.
    Failed with files from LSM 900 (missing information in the metadata).
    Not tested on LSM 880, 980, Elyra, Lightsheet - but likely to fail as well.
    Parameters:
    - full_metadata: The metadata object from the CZI file. It should contain all necessary information about the image acquisition.
    - output_name: The name of the output file, used for naming the image in the OME metadata.
    - scene_idx: The index of the scene being processed, used for multi-scene CZI files.
    Returns:
    - An OME object containing the extracted metadata.
    """

    full_meta = full_metadata.czi_box.ImageDocument.Metadata
    meta_dict = full_meta.to_dict()
    
    if full_metadata.ismosaic: #read_tool load the full image, not the mosaic
        size_x = full_metadata.array6d_size[-1]
        size_y = full_metadata.array6d_size[-2]
    else:
        size_x = full_metadata.image.SizeX
        size_y = full_metadata.image.SizeY
    
    if full_metadata.image.SizeB or full_metadata.image.SizeH or full_metadata.image.SizeI or full_metadata.image.SizeR or full_metadata.image.SizeV:
        pass
       
    # Create an OME object
    ome = model.OME()

    #OBJECTIVE LENS
    czi_objectives = full_metadata.objective

    objectives_list = []
    for idx in range(len(czi_objectives.name)):
        ome_objective = model.Objective(id=czi_objectives.Id[idx])
        ome_objective.lens_na = float(czi_objectives.NA[idx]) if czi_objectives.NA[idx] is not None else np.nan
        ome_objective.nominal_magnification = float(czi_objectives.objmag[idx]) if czi_objectives.objmag[idx] is not None else np.nan #or totalmag
        immersion_value = czi_objectives.immersion[idx]
        ome_objective.immersion = model.Objective_Immersion(immersion_value) if immersion_value in model.Objective_Immersion._value2member_map_ else None
        ome_objective.model = str(czi_objectives.name[idx])
        
        objectives_list.append(ome_objective)

    #LASER #TODO correct in case of presence of other lightsource
    laser_lines = dict_crawler(meta_dict, "Lasers")[0]
    ome_laser = []
    if isinstance(laser_lines, dict):
        laser_lines = laser_lines.get("Laser", [])
        for idx, line in enumerate(laser_lines):
            laser = model.Laser(id="LightSource:"+str(idx+1))
            laser.power = float(line.get("LaserPower", 0)) * 1000
            laser.model = str(line.get("LaserName", ""))
            wavelenght = str(line.get("LaserName", ""))
            wavelenght = [int(m.group(1)) for m in re.finditer(r"(?<!\d)(\d{3,4})(?!\d)", wavelenght)]
            if len(wavelenght) != 0:
                wavelenght = wavelenght[0] if 330 <= wavelenght[0] <= 1700 else None
                if wavelenght:
                    laser.wavelength = float(wavelenght)
            ome_laser.append(laser)
    
    #LIGHTSOURCE #TODO fix for other microscopes
    ome_lightsources = []
    lightsources = dict_crawler(meta_dict, "LightSources")[0]
    if isinstance(lightsources, dict):
        lightsources = lightsources.get("LightSource", [])
        for idx, light in enumerate(lightsources):
            ome_lightsource = model.LightSource(id=light.get("@Id", "LightSource:"+str(idx+1)))
            power = light.get("Power", None)
            if power:
                ome_lightsource.power = float(power)
            ome_lightsources.append(ome_lightsource)

    #DETECTOR
    czi_detectors = full_metadata.detector
    ome_detectors = []
    for idx in range(len(czi_detectors.Id)):
        detector = model.Detector(id=czi_detectors.Id[idx])
        gain = czi_detectors.gain[idx]
        if gain:
            detector.gain = float(gain)
        amp_gain = czi_detectors.amplificationgain[idx]
        if amp_gain:
            detector.amplification_gain = amp_gain
        detector.model = str(czi_detectors.model[idx]) if czi_detectors.model[idx] is not None else ""
        zoom = czi_detectors.zoom[idx]
        if zoom:
            detector.zoom = float(zoom)
        detector_type = str(czi_detectors.modeltype[idx])
        detector.type = model.Detector_Type(detector_type) if detector_type in model.Detector_Type._value2member_map_ else None

        ome_detectors.append(detector)

    #FILTERS   
    filters = dict_crawler(meta_dict, "Filters")[0]
    ome_filters = []
    if isinstance(filters, dict):
        filters = filters.get("Filter", [])
        if isinstance(filters, dict):
            filters = [filters]

        for idx, f in enumerate(filters):
            ome_filter = model.Filter(id=f.get("@Id", "Filter:"+str(idx+1)))
            
            tr_range = model.TransmittanceRange()
            cut_in = float(f["TransmittanceRange"].get("CutIn", 0))
            if cut_in != 0:
                tr_range.cut_in = cut_in
            cut_out = float(f["TransmittanceRange"].get("CutOut", 0))
            if cut_out != 0:
                tr_range.cut_out = cut_out
                        
            ome_filter.transmittance_range = tr_range
            
            ome_filters.append(ome_filter)
        
    #FILTERSETS
    filtersets = dict_crawler(meta_dict, "FilterSets")[0]
    ome_filtersets = []
    if isinstance(filtersets, dict):
        filtersets= filtersets.get("FilterSet", [])
        if isinstance(filtersets, dict):
            filtersets = [filtersets]       

        for idx, f in enumerate(filtersets): 
            
            ome_filterset = model.FilterSet(id=f.get("@Id", "FilterSet:"+str(idx+1))) 
            
            em_filter = f.get("EmissionFilters", {}).get("EmissionFilterRef", {}).get("@Id", None)
            if em_filter:
                ome_filterset.emission_filters = [model.FilterRef(id=em_filter)]
            
            ex_filter = f.get("ExcitationFilters", {}).get("ExcitationFilterRef", {}).get("@Id", None)
            if ex_filter:
                ome_filterset.excitation_filters = [model.FilterRef(id=ex_filter)]
            
            ome_filtersets.append(ome_filterset)
        
    
    #CREATE OME Instrument part
    micro = model.Microscope()
    micro.model = full_metadata.microscope.System
    instr = model.Instrument(id="Instrument:1",
                             microscope=micro,
                             lasers=ome_laser,
                             objectives=objectives_list,
                             detectors=ome_detectors,
                             filters=ome_filters,
                             filter_sets=ome_filtersets)
    ome.instruments = [instr]

    #PLANETABLE
    aicsczi = CziFile(full_metadata.filepath)
    subblocks = aicsczi.read_subblock_metadata(S=scene_idx)
    
    planes = []
    for block in subblocks:
        pos = block[0]
        meta = block[1]
        if float(pos.get("M", 0)) > 0:
            continue

        #initialize value for the position
        position_x = math.nan
        position_y = math.nan
        position_z = math.nan
        delta_t = 0
        if meta != "":#TODO - parsing example to add the Plane info (localization) to the metadata
            #print('METADATA: '+meta)
            pass
            
        pl_kwargs: Dict[str, Any] = dict(the_t=pos.get('T'),
                                         the_z=pos.get('Z'),
                                         the_c=pos.get('C'),
                                         position_x=position_x,
                                         position_y=position_y,
                                         position_z=position_z,
                                         delta_t=delta_t)
        planes.append(model.Plane(**pl_kwargs))
    
    #Channel
    channels = dict_crawler(meta_dict.get("Information", {}).get("Image", {}), "Channels")
    ome_channels = []
    types = []
    for ch_idx in range(len(full_metadata.channelinfo.dyes)):
        ome_channel = model.Channel(id = "Channel:"+str(ch_idx))
        types.append(full_metadata.channelinfo.pixeltypes[ch_idx])
        
        #basic and minimal information
        ome_channel.name = full_metadata.channelinfo.dyes[ch_idx]
        ome_channel.color = full_metadata.channelinfo.colors[ch_idx]
        ome_channel.samples_per_pixel = 1
        
        #Advance settings from the whole metadata
        ch = channels[0]
        if isinstance(ch, dict):
            ch = ch.get("Channel")
            if isinstance(ch, list):
                ch = ch[ch_idx]

        if isinstance(ch, dict):
            #illumination, acquisition and contrast
            acq_mode = str(ch.get("AcquisitionMode", "Other"))
            ome_channel.acquisition_mode = model.Channel_AcquisitionMode(acq_mode) if acq_mode in model.Channel_AcquisitionMode._value2member_map_ else None
            illu_type = str(ch.get("IlluminationType", "Other"))
            ome_channel.illumination_type = model.Channel_IlluminationType(illu_type) if illu_type in model.Channel_IlluminationType._value2member_map_ else None
            contrast_m = str(ch.get("ContrastMethod", "Other"))
            ome_channel.contrast_method = model.Channel_ContrastMethod(contrast_m) if contrast_m in model.Channel_ContrastMethod._value2member_map_ else None
            #excitation, emission and fluor
            ext_w = ch.get("ExcitationWavelength", None)
            if ext_w:
                ome_channel.excitation_wavelength = float(ext_w)
            emi_w = ch.get("EmissionWavelength", None)
            if emi_w:
                ome_channel.emission_wavelength = float(emi_w)
            ome_channel.fluor = str(ch.get("Fluor", "None"))
            
            #light source settings
            lss = ch.get("LightSourcesSettings", {}).get("LightSourceSettings", None)
            if ext_w:
                ext_w = int(float(ext_w))
            if isinstance(lss, dict):
                lss = [lss]
            if lss:
                for idx, ls in enumerate(lss):
                    wavelenght = ls.get("Wavelength")
                    if wavelenght and ext_w == int(float(wavelenght)): #check that the excitation is the same!
                        ome_lss = model.LightSourceSettings(id=ls.get("LightSource", {}).get("@Id"))
                        attenuation = ls.get("Attenuation")
                        if attenuation:
                            ome_lss.attenuation = float(attenuation)
                        if wavelenght:
                            ome_lss.wavelength = float(wavelenght)
                        ome_channel.light_source_settings = ome_lss
            
            #detector settings
            ds = ch.get("DetectorSettings", None)
            if ds:
                ome_ds = model.DetectorSettings(id=ds.get("Detector").get("@Id"))
                ome_ds.offset = float(ds.get("Offset"))
                ome_ds.gain = float(ds.get("Gain"))
                binning = str(ds.get("Binning"))
                ome_ds.binning = model.Binning(binning) if binning in model.Binning._value2member_map_ else None
                ome_channel.detector_settings = ome_ds

        ome_channels.append(ome_channel)
    
    #CREATE THE PIXEL OBJECT
    pixels = model.Pixels(
        id="Pixels:1",
        dimension_order=model.Pixels_DimensionOrder.XYCZT,
        big_endian = False,
        interleaved = False,
        type = model.PixelType(pixel_type_to_ome(types[0])),
        size_x = full_metadata.image.SizeX if not full_metadata.ismosaic else size_x,
        size_y = full_metadata.image.SizeY if not full_metadata.ismosaic else size_y,
        size_c = full_metadata.image.SizeC if full_metadata.image.SizeC is not None else 1,
        size_z = full_metadata.image.SizeZ if full_metadata.image.SizeZ is not None else 1,
        size_t = full_metadata.image.SizeT if full_metadata.image.SizeT is not None else 1,
        physical_size_x = float(full_metadata.scale.X),
        physical_size_y = float(full_metadata.scale.Y),
        physical_size_z = float(full_metadata.scale.Z) if full_metadata.image.SizeZ is not None else None,
        channels = ome_channels,    
        )
    #pixels size unit - default is micron
    if full_metadata.scale.unit != "micron":
        pixels.physical_size_x_unit = UnitsLength(unit_converter(full_metadata.scale.unit))
        pixels.physical_size_y_unit = UnitsLength(unit_converter(full_metadata.scale.unit))
        if full_metadata.image.SizeZ is not None:
            pixels.physical_size_z_unit = UnitsLength(unit_converter(full_metadata.scale.unit))
        
    pixels.tiff_data_blocks = [model.TiffData()]
    pixels.planes = planes
    
    # Create the Image object
    date_object = parser.isoparse(full_metadata.creation_date)
    
    image = model.Image(
        id="Image:1",
        name = output_name,
        acquisition_date = date_object,
        pixels = pixels,
    )
    image.instrument_ref = model.InstrumentRef(id="Instrument:1")
    #objective settings
    obj_settings = dict_crawler(meta_dict, "ObjectiveSettings")[0]
    if isinstance(obj_settings, dict):
        obj_immersion = obj_settings.get("Medium", "Other")
        obj_immersion = obj_immersion if obj_immersion in model.Objective_Immersion._value2member_map_ else "Other"
        image.objective_settings = model.ObjectiveSettings(
            id = str(obj_settings.get("ObjectiveRef", {}).get("@Id")),
            medium = model.ObjectiveSettings_Medium(obj_immersion),
            refractive_index = float(obj_settings.get("RefractiveIndex", 0))
            )

    ome.images.append(image)
    
    return ome

def convert_czi_to_ometiff(filename: str, output:str="") -> list[str]:
    """
    Convert a CZI file to one or more OME-TIFF files, one per scene.
    The output files are named based on the input file name, with scene information appended if multiple scenes exist.
    If an output directory or base name is provided, it is used accordingly.
    Parameters:
    - file: str or Path : Path to the input CZI file.
    - output: str : Optional path to the output directory or base name for the OME-TIFF files.
    Returns:
    - List of str to the created OME-TIFF files.
    """
    if isinstance(filename, str):
        in_path = Path(filename)
    else:
        in_path = filename

    if output:
        out_path = Path(output)
        if out_path.suffix:  # looks like a file path
            dest_dir = out_path.parent
            base_stem = out_path.stem
            # strip a trailing ".ome" if someone passed "name.ome.tiff" as base
            if base_stem.endswith(".ome"):
                base_stem = base_stem[:-4]
        else: # directory
            dest_dir = out_path
            base_stem = in_path.stem
    else:
        dest_dir = in_path.parent
        base_stem = in_path.stem
        
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    out_files = []
    
    with pyczi.open_czi(filename) as czidoc:
        metadata = czidoc.metadata["ImageDocument"]["Metadata"]
        size = {}
        dims = metadata['Information']['Image']
        for d in dims.keys():
            if 'Size' in d: #just the different Size (X,Y,Z,C,M,H,S...)
                size[d] = int(dims[d])
        scene = dims.get("Dimensions", {}).get("S", {}).get("Scenes", {}).get("Scene", []) #list
        if isinstance(scene, dict):  #if only one scene, it is stored as a dict!
            scene = [scene]
        n_scenes = size.get("SizeS", len(scene))
        
        for scene_idx in range(n_scenes):
            #grab the information about the scene
            well_name = scene[scene_idx].get('@Name', None)
            index_n = scene[scene_idx].get('@Index', None)

            #add the information to the output name
            extra = ""
            if n_scenes > 1:
                if well_name:
                    extra += "_"+well_name
                if index_n:
                    extra += "_Scene"+str(index_n)
            
            #name the output file
            out_name = f"{base_stem}{extra}.ome.tiff"
            out_file = dest_dir / out_name
            out_files.append(out_file)
            
            #Heavy part: read the whole array for the scene using the read_tools from czitools
            array, full_metadata = read_tools.read_6darray(filename, planes={"S":(scene_idx, scene_idx)})

            #Annoying part: build the ome metadata from the full_metadata
            ome = ome_extraction(full_metadata, out_name, scene_idx)
            ome_xml = ome.to_xml() #build the xml
            ome_xml = "<?xml version=\"1.0\"?>\n" + ome.to_xml() #add the header
            #TODO maybe build the whole ome with multi level? just need to duplicate the image part and update the pixel size in it
            pxlx_size = float(ome.images[0].pixels.physical_size_x)
            pxly_size = float(ome.images[0].pixels.physical_size_y)

            # return full_metadata
            if array is not None:
                array = array[0] #first scene - should have only one
                array = array.transpose("T", "Z", "C", "Y", "X")
            else:
                raise ValueError("Array returned from read_tools.read_6darray is None.")
            
            sr = choose_levels(len(array["Y"]), len(array["X"]))
            write_tiff_pyramid(out_file, array, ome_xml, metadata=None,
                               pxl_size=(pxlx_size, pxly_size), subresolutions=sr)
            
    return [str(p) for p in out_files]

def convert_emi_to_ometiff(img_path: str):
    """
    Convert .emi file to ome-tiff format.
    File NEED to finish with emi. A ser file need to be present in the same folder
    
    Args:
    img_path (str): Path to the .emi file
    
    Returns:
    str: Path to the output OME-TIFF file
    dict: Contains the key-pair values
    """
            
    logger.debug(f"Conversion to ometiff from emi required for {img_path}")
    
    try:
        data = tia.file_reader(img_path) #Required to pair the emi and ser file!
        
        if len(data) == 1:
            data = data[0]
        else:
            raise MetaDataError(img_path, f"Length of data at {len(data)} different of 1.")
        
        img_array = data['data']
        # img_array = img_array[ :, :, np.newaxis, np.newaxis, np.newaxis,]
    except FileNotFoundError:
        raise FileNotFoundError(f"The file {img_path} does not exist.")
    # except Exception as e:
    #     raise ValueError(f"Error opening or reading metadata: {str(e)}")
    
    logger.debug(f"{img_path} successfully readen!")
        # Check if this is possible to reduce its bit size
    dimension_order = Pixels_DimensionOrder.XYCZT
    img_array, _ = optimize_bit_depth(img_array)
      
    key_pair = {
        'Microscope':mapping(dict_crawler(data, 'Microscope')[0][1]),
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
    date_str = date_object.strftime(conf.DATE_TIME_FMT)
    key_pair['Acquisition date'] = date_str
    
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
    
    logger.debug("Metadata extracted")
    # Create an OME object
    ome = model.OME()
    
    # Create an Image object
    image = model.Image(
        id="Image:0",
        name=os.path.basename(img_path),
        acquisition_date=datetime.datetime.strptime(date_str,conf.DATE_TIME_FMT),
        
        pixels = model.Pixels(
            id="Pixels:0",
            dimension_order=dimension_order,
            type=model.PixelType(str(img_array.dtype)),
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
        value=model.Map(ms=[Map.M(k=_key, value=str(_value)) for _key, _value in extra_pair.items()])
        
    )
    
    # Add Instrument information
    instrument = model.Instrument(
        id = "Instrument:0",
        microscope=model.Microscope(
                                    type=Microscope_Type.OTHER,
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
    ome.structured_annotations.extend([custom_metadata]) #type: ignore
    # Create Objective for Magnification
    objective = model.Objective(
        id="Objective:0",
        nominal_magnification=float(key_pair['Lens Magnification'])
    )
    instrument.objectives.append(objective)
    
    # Convert OME object to XML string
    ome_xml = ome.to_xml()
    logger.debug("OME created")
    
    output_fpath = os.path.join(os.path.dirname(img_path), os.path.basename(img_path).replace(".emi", ".ome.tiff"))   
    
    # Write OME-TIFF file
    sr = choose_levels(img_array.shape[0], img_array.shape[1], target_min=4096)
    write_tiff_pyramid(output_fpath, img_array, ome_xml, metadata=None,
                       pxl_size=(key_pair['Pixel size'], key_pair['Pixel size']), subresolutions=sr)

    #with tifffile.TiffWriter(output_fpath) as tif:
    #    tif.write(img_array, description=ome_xml, metadata={'axes': 'YX',})
    
    logger.debug(f"Ome-tiff written at {output_fpath}.")

    key_pair = _sanitize_meta(key_pair)
    
    return output_fpath, key_pair


def convert_emd_to_ometiff(img_path: str):
    """
    Convert .emd file to ome-tiff format.
    
    Args:
    img_path (str): Path to the .emd file
    
    Returns:
    str: Path to the output OME-TIFF file
    dict: Contains the key-pair values
    """
    logger.debug(f"Conversion to ometiff from emd required for {img_path}")
    
    img = emd.file_reader(img_path)[0]
    img_array, bitdepth = optimize_bit_depth(img['data'])
        
    data = img['original_metadata']
    logger.debug(f"{img_path} successfully readen!")  

    key_pair = {
        'Microscope': mapping(dict_crawler(data, 'InstrumentModel')[0].split('-')[0]),
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
    date_str = date_object.strftime(conf.DATE_TIME_FMT)
    key_pair['Acquisition date'] = date_str
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
    
    logger.debug("Metadata extracted")
    # Create an OME object
    ome = model.OME()
    
    # Create an Image object
    image = model.Image(
        id="Image:0",
        name=os.path.basename(img_path),
        acquisition_date=datetime.datetime.strptime(date_str,conf.DATE_TIME_FMT),
        pixels = model.Pixels(
            id="Pixels:0",
            dimension_order=model.Pixels_DimensionOrder.XYCZT,
            type=model.PixelType(str(img_array.dtype)),
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
        value=model.Map(ms=[Map.M(k=_key, value=str(_value)) for _key, _value in extra_pair.items()])
        
    )
    
    # Add Instrument information
    instrument = model.Instrument(
        id = "Instrument:0",
        microscope=model.Microscope(
                                    type=Microscope_Type.OTHER,
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
    ome.structured_annotations.extend([custom_metadata])#type: ignore
    # Create Objective for Magnification
    objective = model.Objective(
        id="Objective:0",
        nominal_magnification=float(key_pair['Lens Magnification'])
    )
    instrument.objectives.append(objective)
    
    # Convert OME object to XML string
    ome_xml = ome.to_xml()
    logger.debug("OME created")
    
    output_fpath = os.path.join(os.path.dirname(img_path), os.path.basename(img_path).replace(".emd", ".ome.tiff"))
    
    # Write OME-TIFF file
    sr = choose_levels(img_array.shape[0], img_array.shape[1])
    write_tiff_pyramid(output_fpath, img_array, ome_xml, metadata=None,
                       pxl_size=(key_pair['Physical pixel size'], key_pair['Physical pixel size']), subresolutions=sr)

    #old, simple tif writer
    #with tifffile.TiffWriter(output_fpath) as tif:
    #    tif.write(img_array, description=ome_xml, metadata={'axes': 'YX',})
        
    logger.debug(f"Ome-tiff written at {output_fpath}.")
    return output_fpath, key_pair


def convert_atlas_to_ometiff(img_path: dict):
    """
    Convert atlas file (TEM likely MAPS), which is a pair of mrc and xml, to ome-tiff format.
    
    Args:
    img_path (dict): containing the path for the mrc and xml file
    
    Returns:
    str: Path to the output OME-TIFF file
    dict: Contains the key-pair values
    """
    logger.debug(f"Conversion to ometiff from mrc required for {img_path}")

    if 'mrc' in img_path:
        full_data = mrc.file_reader(img_path['mrc'])[0]
        img_array, _ = optimize_bit_depth(full_data['data'])
        output_fpath = img_path['mrc']
    elif 'tiff' in img_path:
        full_data = tifffile.imread(img_path['tiff'])
        img_array, _ = optimize_bit_depth(full_data)
        output_fpath = img_path['tiff']
    else:
        raise ValueError(f"Extension of the file {img_path} is not supported")
    
    data = parse_xml_with_namespaces(img_path.get('xml', None))
    if data is None:
        raise ValueError("Error opening or reading metadata.")
    logger.debug(f"{img_path} successfully readen!") 
    
    key_pair = {
        'Microscope': mapping(dict_crawler(data, 'InstrumentModel')[0].split('-')[0]),
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
    date_str = date_object.strftime(conf.DATE_TIME_FMT)
    key_pair['Acquisition date'] = date_str
    
    mode = dict_crawler(data, 'ColumnOperatingMode')[0]+' '
    mode += dict_crawler(data, 'ColumnOperatingTemSubMode')[0]+' '
    mode += dict_crawler(data, 'ObjectiveLensMode')[0]+' '
    mode += dict_crawler(data, 'ProbeMode')[0]+' '
    mode += dict_crawler(data, 'ProjectorMode')[0]+' '
    key_pair['Image type'] = mode

    #extra pair for the general metadata        
    # extra_pair = {
    #     'Mode': mode,
    #     'Defocus': dict_crawler(data, 'Defocus',)[0],
    #     'Lens intensity': dict_crawler(data, 'Intensity')[0],
    #     'Tilt': safe_get(dict_crawler(data, 'stage')[0], ['Position', 'A']),
    #     'Stage X': safe_get(dict_crawler(data, 'stage')[0], ['Position', 'X']),
    #     'Stage Y': safe_get(dict_crawler(data, 'stage')[0], ['Position', 'Y']),
    #     'Stage Z': safe_get(dict_crawler(data, 'stage')[0], ['Position', 'Z']),
    #     }
    
    # # Create an OME object
    # ome = model.OME()
    
    # # Create an Image object
    # image = model.Image(
    #     id="Image:0",
    #     name = os.path.basename(img_path['mrc']),
    #     acquisition_date=datetime.datetime.strptime(date_str,conf.DATE_TIME_FMT),
        
    #     pixels = model.Pixels(
    #         id="Pixels:0",
    #         dimension_order=Pixels_DimensionOrder.XYCZT,
    #         type=model.PixelType(str(img_array.dtype)),
    #         size_x=key_pair['Image Size X'],
    #         size_y=key_pair['Image Size Y'],
    #         size_c=1,
    #         size_z=1,
    #         size_t=1,
    #         physical_size_x=key_pair['Physical pixel size'],
    #         physical_size_x_unit=key_pair['Physical pixel unit'],
    #         physical_size_y=key_pair['Physical pixel size'],
    #         physical_size_y_unit=key_pair['Physical pixel unit'],
    #     )
    # )
    

    # # Add Image to OME
    # ome.images.append(image)
    
    # # Create MapAnnotation for custom metadata
    # custom_metadata = model.MapAnnotation(
    #     id="Annotation:0",
    #     namespace="custom.ome.metadata",
    #     value=model.Map(ms=[Map.M(k=_key, value=str(_value)) for _key, _value in extra_pair.items()])
        
    # )
    
    # # Add Instrument information
    # instrument = model.Instrument(
    #     id = "Instrument:0",
    #     microscope=model.Microscope(
    #                                 type=Microscope_Type.OTHER,
    #                                 model=key_pair['Microscope']
    #     ),
    #     detectors=[
    #         model.Detector(
    #             id="Detector:0",
    #             model=key_pair['Electron source'],
    #             voltage=key_pair['Beam tension'],
    #             voltage_unit=model.UnitsElectricPotential('kV'),
    #             ),
    #         model.Detector(
    #             id="Detector:1",
    #             model=key_pair['Camera'],
    #             ),
    #         ]
    #     )
    
    # ome.instruments.append(instrument)
    # ome.structured_annotations.extend([custom_metadata])#type: ignore
    # # Create Objective for Magnification
    # objective = model.Objective(
    #     id="Objective:0",
    #     nominal_magnification=float(key_pair['Lens Magnification'])
    # )
    # instrument.objectives.append(objective)
    
    # # Convert OME object to XML string
    # ome_xml = ome.to_xml()
    # logger.debug("OME created")
    
    # output_fpath = os.path.join(os.path.dirname(img_path['mrc']), os.path.basename(img_path['mrc']).replace(".mrc", ".ome.tiff"))
    
    # # Write OME-TIFF file
    # with tifffile.TiffWriter(output_fpath) as tif:
    #     tif.write(img_array, description=ome_xml, metadata={'axes': 'YX',})
        
    # logger.debug(f"Ome-tiff written at {output_fpath}.")
    return output_fpath, key_pair


def extract_tags_from_tif(img_path: str) -> dict[str, Any]:
    with tifffile.TiffFile(img_path) as tf:
        tags: dict[str, Any] = {}
        pages = tf.pages
        for i in range(len(pages)):
            page = pages[i]
            for tag in page.tags.values():  # type: ignore
                name = getattr(tag, "name", None) or f"TAG_{tag.code}"
                key = name if name not in tags else f"{name}[{i}]"

                if tag.code in conf.VENDOR_TAG_IDS or name in conf.VENDOR_TAG_NAMES:
                    tags[key] = tag.value       # <-- keep raw, no decode
                    continue

                val = tag.value
                if isinstance(val, (bytes, bytearray)):
                    try:
                        val = val.decode("utf-8", "replace")
                    except Exception:
                        pass
                else:
                    val = str(val)
                tags[key] = val
        return tags
    
def convert_tif_to_ometiff(fileData: FileData):
    img_path = fileData.getMainFileTempPath()


    # if hasattr(fileData, 'dictFileName'): #less pythonic than try?
    try:
        try:
            atlasPair = {}
            atlasPair[fileData.getDictFileExtension()] = fileData.getDictFileTempPath()
            atlasPair[fileData.getMainFileExtension()] = img_path
            return convert_atlas_to_ometiff(atlasPair)
        except ValueError:
            pass
    except AttributeError:
        pass #no dict, assume xml is embedded in the tif, as a tag

    #extract the tags form the tiff
    tif_tags = extract_tags_from_tif(img_path)
    
    if "CZ_SEM" in tif_tags:
        return convert_semtif_to_ometiff(img_path, tif_tags)
    elif "FibicsXML" in tif_tags:
        return convert_fibics_to_ometiff(img_path, tif_tags)
    else:
        logger.info("Unsupported tif, checking if ome")

        nominal_magnification_value = 'None'
        pxl_size = '1'
        scope_name = "Undefined"
        #TODO should be able to get the model from my own ome converter

        try:
            ome_metadata = tif_tags.get('ImageDescription')
            if ome_metadata:
                nominal_magnification_value = re.search(r'NominalMagnification="([^"]*)"', ome_metadata)
                if nominal_magnification_value:
                    nominal_magnification_value = nominal_magnification_value.group(1)
                else:
                    nominal_magnification_value = 'None'

                pxl_size = re.search(r'PhysicalSizeX="([^"]*)"', ome_metadata)
                if pxl_size:
                    pxl_size = pxl_size.group(1)
                else:
                    pxl_size = '1'
            else:
                logger.warning("Basic tif, simple import with prefilled key-value pairs triggered")
        except KeyError:
            logger.warning("Basic tif, simple import with prefilled key-value pairs triggered")

        metadata = {'Microscope':scope_name,
                    'Acquisition date':datetime.datetime.now().strftime(conf.DATE_TIME_FMT),
                    'Image Size X':tif_tags.get('ImageWidth', "None"),
                    'Image Size Y':tif_tags.get('ImageLength', "None"),
                    'Lens Magnification': nominal_magnification_value,
                    'Physical pixel size X': pxl_size,
                    'Physical pixel size Y': pxl_size,
                    }
        
        for key, value in metadata.items():
            logger.info(f"{key}: {value}")

        return img_path, metadata
    
       


def convert_semtif_to_ometiff(img_path: str, tif_tags: dict) -> tuple[str, dict]:
    """
    Convert SEM TIF file to ome-tiff format.
    
    Args:
    img_path (str): containing the path for the tif file
    
    Returns:
    str: Path to the output OME-TIFF file
    dict: Contains the key-pair values
    """
    cz_sem_metadata = dict(tif_tags["CZ_SEM"])
        
    logger.debug(f"{img_path} metadata successfully readen!") 

    #construct mag string
    mag_str_list = list(map(str,dict_crawler(cz_sem_metadata, 'ap_mag')[0]))
    mag_str = " ".join(mag_str_list)
                        
    key_pair = {
    'Microscope': mapping(dict_crawler(cz_sem_metadata, 'dp_sem')[0][1]),
    'Image type':dict_crawler(cz_sem_metadata, 'dp_final_lens')[0][1],
    'Lens Magnification': convert_magnification(mag_str),
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
    'Physical pixel size X': dict_crawler(cz_sem_metadata, 'ap_image_pixel_size')[0][1],
    'Physical pixel size Y': dict_crawler(cz_sem_metadata, 'ap_image_pixel_size')[0][1],
    'Image depth': tif_tags.get("BitsPerSample", "8"),
    'Comment': dict_crawler(cz_sem_metadata, 'sv_user_text')[0][1],
    }
        
    date = dict_crawler(cz_sem_metadata, 'ap_date')[0][1]
    time = dict_crawler(cz_sem_metadata, 'ap_time')[0][1]
    
    date_object = datetime.datetime.strptime(date+' '+time, "%d %b %Y %H:%M:%S")
    date_str = date_object.strftime(conf.DATE_TIME_FMT)
    key_pair['Acquisition date'] = date_str

    output_fpath = img_path
    
    return output_fpath, key_pair

    #legacy code in case we want to write the ome-tiff from semtif
    # with tifffile.TiffFile(img_path) as tif:
        #img_array = tif.asarray()
                                                
        # Create an OME object
        # ome = model.OME()
        
        # # Create an Image object
        # image = model.Image(
        #     id="Image:0",
        #     name = os.path.basename(img_path),
        #     acquisition_date=datetime.datetime.strptime(date_str, conf.DATE_TIME_FMT),
            
        #     pixels = model.Pixels(
        #         id="Pixels:0",
        #         dimension_order= Pixels_DimensionOrder.XYCZT,
        #         type=model.PixelType(str(img_array.dtype)),
        #         size_x=key_pair['Image Size X'],
        #         size_y=key_pair['Image Size Y'],
        #         size_c=1,
        #         size_z=1,
        #         size_t=1,
        #         physical_size_x=key_pair['Physical pixel size'],
        #         physical_size_x_unit=key_pair['Physical pixel unit'],
        #         physical_size_y=key_pair['Physical pixel size'],
        #         physical_size_y_unit=key_pair['Physical pixel unit'],
        #     )
        # )
        
        # # Add Image to OME
        # ome.images.append(image)
        
        # # Create MapAnnotation for custom metadata
        # custom_metadata = model.MapAnnotation(
        #     id="Annotation:0",
        #     namespace="custom.ome.metadata",
        #     value=model.Map(ms=[Map.M(k=safe_encode(_key), value=safe_encode(_value)) for _key, _value in cz_sem_metadata.items()])
        # )
        
        # # Add Instrument information
        # instrument = model.Instrument(
        #     id = "Instrument:0",
        #     microscope=model.Microscope(
        #                                 type=Microscope_Type.OTHER,
        #                                 model=key_pair['Microscope']
        #     ),
        #     detectors=[
        #         model.Detector(
        #             id="Detector:0",
        #             voltage=key_pair['EHT value'],
        #             voltage_unit=model.UnitsElectricPotential(key_pair['EHT unit']),
        #             ),
        #         ]
        #     )
        
        # ome.instruments.append(instrument)
        # ome.structured_annotations.extend([custom_metadata])#type: ignore
        # # Create Objective for Magnification
        # objective = model.Objective(
        #     id="Objective:0",
        #     nominal_magnification=float(key_pair['Lens Magnification'])
        # )
        # instrument.objectives.append(objective)
        
        # # Convert OME object to XML string
        # ome_xml = ome.to_xml()
        # logger.debug("OME created")
        
        # output_fpath = os.path.join(os.path.dirname(img_path), os.path.basename(img_path).replace(".tif", ".ome.tiff"))
        
        # # Write OME-TIFF file
        # with tifffile.TiffWriter(output_fpath) as tif:
        #     tif.write(img_array, description=ome_xml, metadata={'axes': 'YX',})
            
        # logger.debug(f"Ome-tiff written at {output_fpath}.")
        

def convert_fibics_to_ometiff(img_path: str, tif_tags: dict):

    #grab the data
    with tifffile.TiffFile(img_path) as tif:
        array = tif.asarray()
    #prepare the output path
    out_name = f"{Path(img_path).stem}.ome.tiff"
    dest_dir = Path(img_path).parent
    out_file = str(dest_dir / out_name)
    #brut force approach to extract the pixel size from the FibicsXML tag
    FLOAT = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
    re_Ux = re.compile(rf"<\s*Ux\s*>\s*({FLOAT})\s*<\s*/\s*Ux\s*>", re.I)
    re_Uy = re.compile(rf"<\s*Uy\s*>\s*({FLOAT})\s*<\s*/\s*Uy\s*>", re.I)
    re_Vx = re.compile(rf"<\s*Vx\s*>\s*({FLOAT})\s*<\s*/\s*Vx\s*>", re.I)
    re_Vy = re.compile(rf"<\s*Vy\s*>\s*({FLOAT})\s*<\s*/\s*Vy\s*>", re.I)

    image_width = tif_tags.get("ImageWidth")
    image_length = tif_tags.get("ImageLength")
    xml_text = tif_tags.get("FibicsXML")
    #if xml_text is not None:
    #    xml_text = xml_text.decode("utf-8", "replace")

    if image_width is None or image_length is None: #fallback if the tags are not present
        image_width = array.shape[1]
        image_length = array.shape[0]

    px_um, py_um = 1.0, 1.0 #initialize with 1.0 in case the regex fail
    mUx = re_Ux.search(xml_text) if isinstance(xml_text, str) else None
    mUy = re_Uy.search(xml_text) if isinstance(xml_text, str) else None
    mVx = re_Vx.search(xml_text) if isinstance(xml_text, str) else None
    mVy = re_Vy.search(xml_text) if isinstance(xml_text, str) else None
    if mUx and mUy and mVx and mVy:
        Ux, Uy = float(mUx.group(1)), float(mUy.group(1))
        Vx, Vy = float(mVx.group(1)), float(mVy.group(1))
        px_um = math.hypot(Ux, Uy)
        py_um = math.hypot(Vx, Vy)

    #Save the data as ome-tiff
    subresolutions = choose_levels(float(image_width), float(image_length))
    metadata = {
            "axes": "YX",
            "PhysicalSizeX": px_um,
            "PhysicalSizeXUnit": "µm",
            "PhysicalSizeY": py_um,
            "PhysicalSizeYUnit": "µm",
    }
    extratags = [(51023, "s", 0, xml_text, False)]
    write_tiff_pyramid(out_file, array, ome_xml=None, metadata=metadata, pxl_size=(px_um, py_um),
                       subresolutions=subresolutions,extra_tags=extratags)
    
    # Convert µm/px -> pixels per centimeter
    # px_cm = px_um * 1e-4
    # py_cm = py_um * 1e-4
    # xres0 = 1.0 / px_cm
    # yres0 = 1.0 / py_cm
    # subresolutions = choose_levels(float(image_width), float(image_length))
    # with tifffile.TiffWriter(out_file, bigtiff=True) as tif:
    #     tif.write(
    #         array,
    #         subifds=subresolutions-1,
    #         metadata={
    #                 "axes": "YX",
    #                 "PhysicalSizeX": px_um,
    #                 "PhysicalSizeXUnit": "µm",
    #                 "PhysicalSizeY": py_um,
    #                 "PhysicalSizeYUnit": "µm",
    #         },
    #         resolution=(xres0, yres0),
    #         resolutionunit="CENTIMETER",
    #         extratags=[(51023, "s", 0, xml_text, False)],
    #         photometric="minisblack",
    #         tile=(512, 512),
    #         maxworkers=2,
    #     )
        
    #     for level in range(1, subresolutions):
    #         mag = 2 ** level
    #         tif.write(
    #             array[..., ::mag, ::mag],
    #             subfiletype=1,
    #             resolution=(xres0/mag, yres0/mag),
    #             resolutionunit="CENTIMETER",
    #             photometric="minisblack",
    #             compression="zlib",
    #             predictor=True,
    #             tile=(512, 512),
    #             maxworkers=2,
    #         )

    #generate a small key-value pair for Omero!
    mini_metadata = {'Microscope': mapping('Gemini'),
                     'Lens Magnification': "N/A",
                     'Lens NA': "N/A",
                     'Image type':'SEM',
                     'Physical pixel size X':px_um,
                     'Physical pixel size Y':py_um,
                     'Image Size X':image_width,
                     'Image Size Y':image_length,
                     'Comment':"N/A",
                     'Description':"N/A",
                     'Acquisition date': datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                     }

    return out_file, mini_metadata


def convert_magnification(mag_str):
    """Convert magnification string like '81.20 K X' to a real number."""
    
    # Extract numeric part and unit using regex
    match = re.match(r"(?:MAG\s*)?(\d+(?:\.\d+)?)\s*([KMG]?)\s*X", mag_str, re.IGNORECASE)
    
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
        if '\xb5' in value: 
            value = value.replace('\xb5', 'micron')
        elif '\xb0' in value: 
            value = value.replace('\xb0', 'degree')
        elif '\xb2' in value: 
            value = value.replace('\xb2', '^')
        # Try encoding to ASCII first, fallback to UTF-8 if needed
        try:
            # Check for non-ASCII and raise an error to trigger the fallback
            value.encode('ascii')
        except UnicodeEncodeError:
            # If encoding fails, try UTF-8 encoding
            value = value.encode('utf-8').decode('utf-8')
        
        return value
    
    return str(value)  # Ensure everything else (e.g., None) is converted to string


# def delete(file_path:str):
#     if os.path.exists(file_path):
#         os.remove(file_path)
#         logger.info(f"Successfully deleted temporary file: {file_path}")
#     else:
#         logger.warning(f"Temporary file not found for deletion: {file_path}")

def is_supported_format(fileName):
    if '.' not in fileName:
        logger.info(f"{fileName} is not a propper file name")
        return False
    
    ext = fileName.split('.')[-1]
    return ('.'+ext) in conf.ALLOWED_FOLDER_FILE_EXT or ('.'+ext) in conf.ALLOWED_SINGLE_FILE_EXT

def file_format_splitter(fileData : FileData) -> tuple[list[str], dict[str,str]]:
    ext = fileData.getMainFileExtension().lower()
    try:
        img_path = fileData.getMainFileTempPath()
    except AttributeError:
        logger.info(f"File {fileData.originalFileNames} is not supported")
        img_path = ""

    logger.info(f"Received file is of format {ext}")

    if ext == "czi": #Light microscope format - CarlZeissImage
        key_pair = get_info_metadata_from_czi(Path(img_path))
        mic = (key_pair.get("Microscope") or "").strip()

        mic_ok  = mic in conf.TO_CONVERT_SCOPE
        size_ok = fileData.getTotalFileSize() > conf.CZI_CONVERT_MIN_BYTES
        do_convert = mic_ok and (conf.FORCE_CZI_CONVERSION or size_ok)

        if do_convert:
            try:
                converted_path = convert_czi_to_ometiff(img_path)
            except Exception:  # catch-all is fine; not a bare except
                    logger.error(f"CZI→OME-TIFF conversion failed for {str(img_path)}; falling back to Bio-Formats.")
                    converted_path = [img_path]
        else: #no conversion needed
            converted_path = [img_path]
    
    elif ext == "tif" or ext == "tiff":
        converted_path, key_pair = convert_tif_to_ometiff(fileData)
    
    elif ext == "mrc":
        atlasPair = {}
        atlasPair[fileData.getDictFileExtension()] = fileData.getDictFileTempPath()
        atlasPair[fileData.getMainFileExtension()] = img_path
        converted_path, key_pair = convert_atlas_to_ometiff(atlasPair)

    #these formats need to be converted locally due to no bioformats support
    elif ext == "emi": #Electron microscope format
        converted_path, key_pair = convert_emi_to_ometiff(img_path)
    elif ext == "emd": #Electron microscope format
        converted_path, key_pair = convert_emd_to_ometiff(img_path)

    else:
        raise ImageNotSupported(f"Image format not supported: {ext}")
    
    #security
    if isinstance(converted_path, str):
        converted_path = [converted_path]
    converted_path = [p for p in (converted_path or []) if p]
    
    if not converted_path:
        # Fallback to staged originals (what TempFileHandler saved)
        staged = fileData.getUploadFilePaths() or fileData.getTempFilePaths()
        if staged:
            logger.warning(f"format_splitter returned no paths; falling back to staged uploads: {str(staged)}")
            converted_path = staged
        else:
            raise ValueError(f"No files to import after format split for {img_path}")

    return converted_path, key_pair