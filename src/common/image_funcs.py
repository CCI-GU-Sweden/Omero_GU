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
from zoneinfo import ZoneInfo
import tzlocal
import re
from ipaddress import ip_address
from dateutil import parser
from pathlib import Path
from rsciio import tia, emd, mrc
import numpy as np
import tifffile
import xml.etree.ElementTree as ET
from flask import request
from ome_types import model
from ome_types.model import Microscope_Type, Pixels_DimensionOrder

from ome_types.model import Map
from ome_types.model.simple_types import PixelType, UnitsLength
from common import conf
from common import czi_pyramidizer
from common import logger
from common.file_data import FileData
from omerofrontend.exceptions import MetaDataError
from typing import Any

def get_timezone_aware_iso_str(dt: datetime.datetime) -> str:
    
    local_zone_name = tzlocal.get_localzone_name()   # e.g. "Europe/Paris"
    local_zone = ZoneInfo(local_zone_name)

    aware_real = dt.replace(tzinfo=local_zone)
    return aware_real.isoformat()

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

def downsample2x_nearest(im):
    # Fast + dependency-free. Good enough for pyramids/thumbnails.
    return im[::2, ::2]

def write_simple_ometif_pyramid(
    output_fpath: str,
    img_yx: np.ndarray,
    ome_xml: str,
    tile=(256, 256),
    compression="zlib",
    target_min=512,
):
    if img_yx.ndim != 2:
        raise ValueError(f"Expected 2D grayscale (Y,X). Got shape {img_yx.shape}")

    y, x = img_yx.shape
    nlevels = choose_levels(y, x, target_min=target_min)

    # BigTIFF is safer for large images/pyramids
    with tifffile.TiffWriter(output_fpath, bigtiff=True) as tif:
        # Write base level with SubIFDs reserved
        tif.write(
            img_yx,
            description=ome_xml,
            metadata={"axes": "YX"},
            photometric="minisblack",
            planarconfig="contig",
            tile=tile,
            compression=compression,
            subifds=nlevels-1,   # reserve space for pyramid levels
        )

        # Write reduced levels into the SubIFDs
        level = img_yx
        for _ in range(1, nlevels):
            level = downsample2x_nearest(level)
            tif.write(
                level,
                subfiletype=1,          # reduced-resolution image
                photometric="minisblack",
                planarconfig="contig",
                tile=tile,
                compression=compression,
                metadata=None,         # no metadata for pyramid levels
            )

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


def is_valid_ip(value: Any) -> bool:
    if value is None:
        return False
    try:
        ip_address(str(value).strip())
        return True
    except ValueError:
        return False


def _normalize_ip(value: Any) -> str | None:
    if not is_valid_ip(value):
        return None
    return str(ip_address(str(value).strip()))


def get_client_ip() -> str | None:
    """Return the client IP, honoring X-Forwarded-For only for trusted proxies."""
    try:
        remote_addr = request.remote_addr
        forwarded_for = request.headers.get("X-Forwarded-For", "")
    except RuntimeError:
        # No active Flask request context.
        return None

    trusted_proxies = {
        normalized
        for proxy in conf.TRUSTED_PROXY_IPS
        if (normalized := _normalize_ip(proxy)) is not None
    }

    remote_ip = _normalize_ip(remote_addr)
    if remote_ip is None:
        return None

    # Explicitly disable forwarded header parsing when no trusted proxies are configured.
    if not trusted_proxies:
        return remote_ip

    if remote_ip in trusted_proxies and forwarded_for:
        for candidate in forwarded_for.split(","):
            normalized_candidate = _normalize_ip(candidate)
            if normalized_candidate is not None:
                return normalized_candidate

    return remote_ip

def mapping(microscope, client_ip: str | None = None):
    """Map microscope metadata value to canonical name, with optional IP fallback."""
    micro_mapping = conf.MICROSCOPE_ID_TO_NAME
    mapped_name = micro_mapping.get(microscope, microscope)

    # Use IP fallback only when metadata did not provide a meaningful mapping.
    if mapped_name in [None, "", "Undefined", "Instrument:0"]:
        ip_mapping = {
            normalized_ip: name
            for raw_ip, name in conf.MICROSCOPE_IP_TO_NAME.items()
            if (normalized_ip := _normalize_ip(raw_ip)) is not None
        }

        resolved_ip = _normalize_ip(client_ip) if client_ip is not None else get_client_ip()
        if resolved_ip is not None and resolved_ip in ip_mapping:
            return ip_mapping[resolved_ip]

    return mapped_name

def get_ome_metadata(path: Path, include_ome_xml: bool=False, include_raw_metadata: bool=False) -> dict:
    """Extract a compact metadata dictionary from BioFormats OME-XML.

    Parameters
    ----------
    path:
        Image file path accepted by ``bioio``/BioFormats.
    include_ome_xml:
        Include the generated OME-XML string in the return dictionary. This is
        mainly useful while debugging parser behavior.
    include_raw_metadata:
        Include the raw BioFormats metadata XML in the return dictionary. This
        can be large, so it is disabled by default.

    Returns
    -------
    dict
        Normalized metadata fields used by the application prototype.
    """

    if not path.exists():
        raise FileNotFoundError(f"The file {path} does not exist.")

    # Invalid/placeholder files should fail fast without spinning up BioFormats.
    if path.stat().st_size == 0:
        raise ValueError(f"Error opening or reading metadata: {path.as_posix()}")

    try:
        from bioio import BioImage #lazy import
        import bioio_bioformats
        import xml.etree.ElementTree as ET

        # BioImage initializes the BioFormats reader and exposes common normalized
        # metadata such as physical pixel sizes and scene counts.
        img = BioImage(path, reader=bioio_bioformats.Reader)

        md = {} #final dictionary to hold the metadata we want to extract

        # Directly read the most important metadata from the BioImage object. These
        # values can later be overwritten by explicit OME-XML values when present.
        md["Physical pixel size X"] = img.physical_pixel_sizes.X
        md["Physical pixel size Y"] = img.physical_pixel_sizes.Y
        md["Physical pixel size Z"] = img.physical_pixel_sizes.Z

        # Convert the parsed OME model back to XML so we can access fields that are
        # not exposed as first-class BioImage attributes.
        ome_xml = img.ome_metadata.to_xml()

        root = ET.fromstring(ome_xml)
        ns = {"ome": root.tag.split("}")[0].strip("{")}

        # OME-XML usually has one Image/Pixels block for the active image and one
        # Instrument block describing objective and microscope metadata.
        image = root.find("ome:Image", ns)
        pixels = image.find("ome:Pixels", ns) if image is not None else None
        instrument = root.find("ome:Instrument", ns)
        objective = instrument.find("ome:Objective", ns) if instrument is not None else None

        # Image sizes and physical sizes are stored as attributes on Pixels. Only
        # copy axes that are present because not every format records every axis.
        if pixels is not None:
            for axis in ["X", "Y", "Z", "C", "T", "S", "M", "H"]:
                value = pixels.get(f"Size{axis}")
                if value is not None:
                    md[f"Image Size {axis}"] = int(value)

            for axis in ["X", "Y", "Z"]:
                value = pixels.get(f"PhysicalSize{axis}")
                if value is not None:
                    md[f"Physical pixel size {axis}"] = round(float(value), 4)

        if "Image Size S" not in md: #fall back to counting the number of scenes if SizeS is not available
            md["Image Size S"] = len(img.scenes)

        # Objective details are optional in OME-XML. Prefer the nominal
        # magnification, then calibrated magnification if nominal is missing.
        if objective is not None:
            lens_mag = (
                objective.get("NominalMagnification")
                or objective.get("CalibratedMagnification")
            )

            if lens_mag is not None:
                md["Lens Magnification"] = int(float(lens_mag))

            lens_na = objective.get("LensNA")
            if lens_na is not None:
                md["Lens NA"] = round(float(lens_na), 2)

            md["Lens Immersion"] = objective.get("Immersion")
            md["Objective Model"] = objective.get("Model")

        # Acquisition date and description are child elements rather than Pixels
        # attributes.
        if image is not None:
            acq_date = image.find("ome:AcquisitionDate", ns)
            desc = image.find("ome:Description", ns)

            md["Acquisition date"] = acq_date.text if acq_date is not None else None
            md["Description"] = desc.text if desc is not None else None

        # Channel metadata can indicate the image modality. Use the first available
        # channel descriptor as a coarse "Image type" value.
        channels = []
        if pixels is not None:
            for ch in pixels.findall("ome:Channel", ns):
                channels.append({
                    "AcquisitionMode": ch.get("AcquisitionMode"),
                    "IlluminationType": ch.get("IlluminationType"),
                    "ContrastMethod": ch.get("ContrastMethod"),
                })

        md["Image type"] = next(
            (
                c["AcquisitionMode"] or c["IlluminationType"] or c["ContrastMethod"]
                for c in channels
                if c["AcquisitionMode"] or c["IlluminationType"] or c["ContrastMethod"]
            ),
            None,
        )

    # OME Instrument metadata is not always populated. If it only contains the
    # generated placeholder ID, treat the microscope as unknown.
        if instrument is not None:
            microscope = instrument.get("Model") or instrument.get("Manufacturer") or instrument.get("ID")
            if microscope == "Instrument:0":
                microscope = None
            md["Microscope"] = mapping(microscope)
        else:
            md["Microscope"] = mapping(None)

        md["Comment"] = None

        md["Metadata source"] = "OME-XML via BioFormats"
        #for debugging purposes
        if include_ome_xml:
            md["ome_xml"] = ome_xml
        if include_raw_metadata:
            md["raw_metadata"] = img.metadata.to_xml()

        return md
    except Exception as e:
        logger.error(f"Error opening or reading metadata: {str(e)}")
        raise ValueError(f"Error opening or reading metadata: {path.as_posix()}")


def get_extra_czi_metadata(path: Path) -> dict:
    """Extract CZI metadata that may be missing from generated OME-XML.

    The Zeiss CZI metadata schema varies by acquisition software. This function
    inspects the application name/version and then reads the microscope name
    from the location used by that software generation.
    """
    from pylibCZIrw import czi as pyczi #lazy import

    try:
        with pyczi.open_czi(str(path)) as czidoc:
            metadata = czidoc.metadata['ImageDocument']['Metadata']
    except Exception as e:
        logger.error(f"Error opening or reading metadata: {str(e)}")
        raise ValueError(f"Error opening or reading metadata: {path}")
    
    # Microscope name in CZI metadata is not standardized, so parse it based on
    # the application that created the metadata.
    microscope = None
    app = metadata['Information'].get('Application', None)
    if app is not None: #security check
        app_name = app['Name']
        app_version = app['Version']
        logger.debug('Metadata made with %s version %s' %(app_name, app_version))

        # ZEN 3.x stores the user-facing microscope name when available, but
        # some files only have a generic name or camera name.
        if 'ZEN' in app_name and app_version.startswith("3."): #CD7, 980, Elyra
            microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('UserDefinedName', None)
            if microscope is None:
                microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('@Name', None)
            if microscope is None:
                microscope = metadata['Scaling']['AutoScaling'].get('CameraName', None)

        # ZEN 2.6 and AIM write the microscope name to different fields.
        elif 'ZEN' in app_name and app_version.startswith("2.6"): #Observer, Imager
            microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('@Name', None)
            
        elif 'AIM' in app_name: #700, 880, 710
            microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('System', None)

        # Normalize the raw microscope value and preserve document-level notes.
        microscope = mapping(microscope)
        comment = metadata['Information']['Document'].get('Comment', None)
        description = metadata['Information']['Document'].get('Description', None)
    else:
        return {}
    return {'Microscope':microscope, 'Comment':comment, 'Description':description}

# legacy code. Can remove if we are sure that the get_ome_metadata function is working well.
# The get_extra_czi_metadata function can be used as a fallback to extract the microscope name when it is missing from the OME-XML metadata.

# def get_info_metadata_from_czi(img_path : Path) -> dict:
#     """
#     Extract important metadata from a CZI image file.
    
#     This function opens a CZI image file, reads its metadata, and extracts
#     specific information such as microscope details, lens properties,
#     image type, pixel size, image dimensions, and other relevant metadata.
    
#     Args:
#         img_path : The file path to the CZI image.
    
#     Returns:
#         ImageMetadata: A dictionnary containing the extracted metadata.
    
#     Raises:
#         FileNotFoundError: If the specified image file does not exist.
#         ValueError: If the file is not a valid CZI image or if metadata extraction fails.
#     """
    
#     if not img_path.exists():
#         raise FileNotFoundError(f"The file {img_path} does not exist.")
    
#     try:
#         with pyczi.open_czi(str(img_path)) as czidoc:
#             metadata = czidoc.metadata['ImageDocument']['Metadata']
#     except Exception as e:
#         logger.error(f"Error opening or reading metadata: {str(e)}")
#         raise ValueError(f"Error opening or reading metadata: {img_path}")

           
#     #Initialization
#     app_name = None
#     app_version = None
#     microscope = None
#     acq_type = None
#     lensNA = None
#     lensMag = None
#     lensImmersion = None
#     pre_processed = None
#     comment = None
#     description = None
#     creation_date = None
                                
#     #grab the correct version of the metadata
#     app = metadata['Information'].get('Application', None)
#     if app is not None: #security check
#         app_name = app['Name']
#         app_version = app['Version']
#         logger.debug('Metadata made with %s version %s' %(app_name, app_version))
#         #Another way will be to grab the IP address of the room and map it
#         #microscope name, based on the version of the metadata
#         if 'ZEN' in app['Name'] and app['Version'].startswith("3."): #CD7, 980, Elyra
#             microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('UserDefinedName', None)
#             if microscope is None:
#                 microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('@Name', None)
#             if microscope is None:
#                 microscope = metadata['Scaling']['AutoScaling'].get('CameraName', None)

#         elif 'ZEN' in app['Name'] and app['Version'].startswith("2.6"): #Observer, Imager
#             microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('@Name', None)
            
#         elif 'AIM' in app['Name']: #700, 880, 710
#             microscope = metadata['Information']['Instrument']['Microscopes']['Microscope'].get('System', None)

#         microscope = mapping(microscope)
            
#         logger.debug('Image made on %s' %(microscope))
#         #pixel size (everything in the scaling)
#         physical_pixel_sizes = {}
#         for dim in metadata['Scaling']['Items']['Distance']:
#             physical_pixel_sizes[dim['@Id']] = round(float(dim['Value'])*1e+6, 4)
            
#         #image dimension
#         dims = metadata['Information']['Image']
#         size = {}
#         for d in dims.keys():
#             if 'Size' in d: #just the different Size (X,Y,Z,C,M,H...)
#                 size[d] = int(dims[d])
#         logger.debug('Image with dimension %s and pixel size of %s' %(size, physical_pixel_sizes))
            
#         # Acquisition type (not fully correct with elyra)
#         acq_type = metadata['Information']['Image']['Dimensions']['Channels']['Channel']
#         if isinstance(acq_type, list):
#             acq_type = acq_type[0].get('ChannelType', acq_type[0].get('AcquisitionMode', None))
#             if acq_type == 'Unspecified':
#                 acq_type = metadata['Information']['Image']['Dimensions']['Channels']['Channel'][0].get('AcquisitionMode', None)
#         elif isinstance(acq_type, dict):
#             acq_type = acq_type.get('AcquisitionMode', None)
#         logger.debug('Image acquired with a %s mode' %(acq_type))
            
#         #lens info
#         obj_settings = dict_crawler(metadata, "ObjectiveSettings")[0]
#         if isinstance(obj_settings, dict):
#             lensImmersion = obj_settings.get("Medium", "Other")
#             lensImmersion = lensImmersion if lensImmersion in model.Objective_Immersion._value2member_map_ else "Other"

#         lensNA = metadata['Information']['Instrument']['Objectives']['Objective'].get('LensNA', None)
#         if lensNA is not None: 
#             lensNA = round(float(lensNA), 2)
#         lensMag = metadata['Information']['Instrument']['Objectives']['Objective'].get('NominalMagnification', None)
#         if lensMag is not None: 
#             lensMag = int(lensMag)
#         logger.debug('Objective lens used has a magnification of %s, a NA of %s and an immersion of %s' %(lensMag, lensNA, lensImmersion))
            
#         #processing (if any)
#         processing = metadata['Information'].get('Processing', None)
#         if processing is not None:
#             pre_processed = list(processing.keys())
#             logger.debug('Image preprocessed with %s' %(pre_processed))
            
#         #other
#         comment = metadata['Information']['Document'].get('Comment', None)
#         description = metadata['Information']['Document'].get('Description', None)
#         #creation_date = metadata['Information']['Document'].get('CreationDate', None)
#         date_object = parser.isoparse(metadata['Information']['Document'].get('CreationDate', None))
#         creation_date = date_object.strftime(conf.DATE_TIME_FMT)
#         logger.debug(
#                         f"Image\n    Comment: {comment if comment else 'No comment'},\n" 
#                         f"Description: {description if description else 'No description'},\n"
#                         f"Creation date: {creation_date if creation_date else 'No creation date'}"
#                     )    
#     else:
#         return {}
         
#     logger.debug("_"*25)

#     mini_metadata = {'Microscope':microscope,
#                      'Lens Magnification': lensMag,
#                      'Lens NA': lensNA,
#                      'Lens Immersion': lensImmersion,
#                      'Image type':acq_type,
#                      'Physical pixel size':physical_pixel_sizes,
#                      'Image Size':size,
#                      'Comment':comment,
#                      'Description':description,
#                      'Acquisition date': creation_date,
#                      }
#     # Unpack Physical pixel size
#     for axis, value in physical_pixel_sizes.items():
#         mini_metadata[f'Physical pixel size {axis}'] = value
    
#     # Unpack Image Size
#     for axis, value in size.items():
#         mini_metadata[f'Image Size {axis[-1]}'] = value
    
#     del mini_metadata['Physical pixel size']
#     del mini_metadata['Image Size']
    
#     return mini_metadata       

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
        if img_array.ndim != 2:
            raise ValueError(f"Expected 2D grayscale image data. Got shape {img_array.shape}")

    except FileNotFoundError:
        raise FileNotFoundError(f"The file {img_path} does not exist.")
    
    logger.debug(f"{img_path} successfully readen!")
        # Check if this is possible to reduce its bit size
    dimension_order = Pixels_DimensionOrder.XYCZT
    img_array, _ = optimize_bit_depth(img_array)

    size_y, size_x = img_array.shape
    dtype_to_ome = {
        np.dtype("uint8"): "uint8",
        np.dtype("uint16"): "uint16",
        np.dtype("uint32"): "uint32",
        np.dtype("float32"): "float32",
    }
    px_type = dtype_to_ome.get(img_array.dtype, None)
    if px_type is None:
        raise ValueError(f"Unsupported dtype for OME: {img_array.dtype}")

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
    date_str = dict_crawler(data, 'AcquireDate')[0]
    date_iso_str= get_timezone_aware_iso_str(parser.parse(date_str))
    date_object = parser.isoparse(date_iso_str)
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
        acquisition_date=date_object,#datetime.datetime.strptime(date_str,conf.DATE_TIME_FMT),
        
        pixels = model.Pixels(
            id="Pixels:0",
            dimension_order=dimension_order,
            type=model.PixelType(px_type),
            size_x=size_x,
            size_y=size_y,
            size_c=1,
            size_z=1,
            size_t=1,
            physical_size_x=key_pair['Pixel size'],
            physical_size_x_unit=key_pair['Pixel unit'],
            physical_size_y=key_pair['Pixel size'],
            physical_size_y_unit=key_pair['Pixel unit'],
        )
    )
    # Add a single channel with SamplesPerPixel=1 to match grayscale TIFF storage
    pixels = image.pixels
    pixels.channels.append(
        model.Channel(
            id="Channel:0",
            name="Channel:0",
            samples_per_pixel=1,
        )
    )
    # add explicit TiffData plane mapping - only 2d mono image here
    pixels.tiff_data_blocks.append(
        model.TiffData(
            first_z=0, first_c=0, first_t=0,
            plane_count=1,
            ifd=0
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
    
    output_fpath = os.path.join(os.path.dirname(img_path), os.path.basename(img_path).replace(".emi", ".ome.tif"))   
    
    # Write OME-TIF file
    write_simple_ometif_pyramid(output_fpath, img_array, ome_xml)
    logger.debug(f"Ome-tif written at {output_fpath}.")
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
    img_array, _ = optimize_bit_depth(img['data'])

    size_y, size_x = img_array.shape
    dtype_to_ome = {
        np.dtype("uint8"): "uint8",
        np.dtype("uint16"): "uint16",
        np.dtype("uint32"): "uint32",
        np.dtype("float32"): "float32",
    }
    px_type = dtype_to_ome.get(img_array.dtype, None)
    if px_type is None:
        raise ValueError(f"Unsupported dtype for OME: {img_array.dtype}")

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
    date_iso_str = get_timezone_aware_iso_str(date_object)
    date_object = parser.isoparse(date_iso_str)
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
        acquisition_date=date_object, #datetime.datetime.strptime(date_str,conf.DATE_TIME_FMT),
        pixels = model.Pixels(
            id="Pixels:0",
            dimension_order=model.Pixels_DimensionOrder.XYCZT,
            type=model.PixelType(px_type),
            size_x=size_x,
            size_y=size_y,
            size_c=1,
            size_z=1,
            size_t=1,
            physical_size_x=key_pair['Physical pixel size'],
            physical_size_x_unit=key_pair['Physical pixel unit'],
            physical_size_y=key_pair['Physical pixel size'],
            physical_size_y_unit=key_pair['Physical pixel unit'],
        )
    )

    # Add a single channel with SamplesPerPixel=1 to match grayscale TIFF storage
    pixels = image.pixels
    pixels.channels.append(
        model.Channel(
            id="Channel:0",
            name="Channel:0",
            samples_per_pixel=1,
        )
    )
    # add explicit TiffData plane mapping - only 2d mono image here
    pixels.tiff_data_blocks.append(
        model.TiffData(
            first_z=0, first_c=0, first_t=0,
            plane_count=1,
            ifd=0
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
    
    output_fpath = os.path.join(os.path.dirname(img_path), os.path.basename(img_path).replace(".emd", ".ome.tif"))
    
    # Write OME-TIF file
    write_simple_ometif_pyramid(output_fpath, img_array, ome_xml)
        
    logger.debug(f"Ome-tif written at {output_fpath}.")
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

    full_data = mrc.file_reader(img_path['mrc'])[0]
    img_array, bit = optimize_bit_depth(full_data['data'])
    
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

    output_fpath = img_path['mrc']
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
    
def convert_tif_to_ometiff(img_path: str):
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

    # Convert µm/px -> pixels per centimeter
    px_cm = px_um * 1e-4
    py_cm = py_um * 1e-4
    xres0 = 1.0 / px_cm
    yres0 = 1.0 / py_cm

    #Save the data as ome-tiff
    subresolutions = choose_levels(float(image_width), float(image_length))
    with tifffile.TiffWriter(out_file, bigtiff=True) as tif:
        tif.write(
            array,
            subifds=subresolutions-1,
            metadata={
                    "axes": "YX",
                    "PhysicalSizeX": px_um,
                    "PhysicalSizeXUnit": "µm",
                    "PhysicalSizeY": py_um,
                    "PhysicalSizeYUnit": "µm",
            },
            resolution=(xres0, yres0),
            resolutionunit="CENTIMETER",
            extratags=[(51023, "s", 0, xml_text, False)],
            photometric="minisblack",
            tile=(512, 512),
            maxworkers=2,
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
                tile=(512, 512),
                maxworkers=2,
            )

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


def is_supported_format(fileName):
    if '.' not in fileName:
        logger.info(f"{fileName} is not a proper file name")
        return False
    
    ext = fileName.split('.')[-1]
    return ('.'+ext) in conf.ALLOWED_FOLDER_FILE_EXT or ('.'+ext) in conf.ALLOWED_SINGLE_FILE_EXT

def _handle_czi_with_pyramidizer(fileData: FileData, img_path: str, key_pair: dict[str, str]) -> list[str]:
    """Handle CZI files with the pyramidizer, including error handling and fallback."""
    if not conf.CZI_PYRAMIDIZER_ENABLED:
        logger.info("CZI pyramidizer is disabled by configuration, skipping pyramidization")
        return [img_path]

    source_size = fileData.getTotalFileSize()
    destination_path = czi_pyramidizer.default_pyramidized_path(img_path)

    try:
        check_result = czi_pyramidizer.check_needs_pyramid(img_path)
        logger.info(
            "CZI pyramid check done "
            f"czi_pyramid_check_exit_code={check_result.run_result.exit_code} "
            f"czi_source_bytes={source_size}"
        )

        if not check_result.needs_pyramid:
            return [img_path]

        build_result = czi_pyramidizer.build_pyramid(img_path, destination_path)
        logger.info(
            "CZI pyramid build done "
            f"czi_pyramid_build_exit_code={build_result.run_result.exit_code} "
            f"czi_source_bytes={source_size}"
        )
        if build_result.created_output:
            logger.info(f"Pyramidized CZI written to {destination_path}")
            return [destination_path]

        logger.info(f"Pyramidizer took no action for {img_path}, using original")
        return [img_path]
    except czi_pyramidizer.CziPyramidizerError as exc:
        run_result = exc.run_result
        exit_code = run_result.exit_code if run_result is not None else "n/a"
        stderr_tail = run_result.stderr if run_result is not None else ""
        stdout_tail = run_result.stdout if run_result is not None else ""
        logger.error(
            "CZI pyramidizer failed "
            f"for {img_path}. exit_code={exit_code}. "
            f"error={str(exc)}\n"
            f"  stderr: {stderr_tail!r}\n"
            f"  stdout: {stdout_tail!r}"
        )

        return [img_path]

def file_format_splitter(fileData : FileData) -> tuple[list[str], dict[str,str]]:
    ext = fileData.getMainFileExtension().lower()
    img_path = fileData.getMainFileTempPath()
    logger.info(f"Received file is of format {ext}")
    key_pair = {} #initialize

    #start with the EM format, not supported by bioformats
    if ext == "tif": #Tif, but only SEM-TIF or Fibics-TIF are supported
        converted_path, key_pair = convert_tif_to_ometiff(img_path)
    elif ext == "mrc":
        atlasPair = {}
        atlasPair[fileData.getDictFileExtension()] = fileData.getDictFileTempPath()
        atlasPair[fileData.getMainFileExtension()] = img_path
        converted_path, key_pair = convert_atlas_to_ometiff(atlasPair)
    elif ext == "emi": #Electron microscope format
        converted_path, key_pair = convert_emi_to_ometiff(img_path)
    elif ext == "emd": #Electron microscope format
        converted_path, key_pair = convert_emd_to_ometiff(img_path)

    else: #Other formats are expected to be supported by bioformats
        key_pair = get_ome_metadata(Path(img_path))
        converted_path = [img_path]
        if ext == "czi": #Light microscope format - CarlZeissImage can have extra metadata
            key_pair.update(get_extra_czi_metadata(Path(img_path)))
            converted_path = _handle_czi_with_pyramidizer(fileData, img_path, key_pair)
    
    #security
    if isinstance(converted_path, str):
        converted_path = [converted_path]
    converted_path = [p for p in (converted_path or []) if p]
    
    if not converted_path:
        # Fallback to staged originals (what TempFileHandler saved)
        staged = fileData.getTempFilePaths()
        if staged:
            logger.warning(f"format_splitter returned no paths; falling back to staged uploads: {str(staged)}")
            converted_path = staged
        else:
            raise ValueError(f"No files to import after format split for {img_path}")

    return converted_path, key_pair
