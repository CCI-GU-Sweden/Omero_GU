import config
import logger
import os
import datetime
from pathlib import Path
import numpy as np
import re

from rsciio.tia import file_reader
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

    return list(search(dictionary, search_key))


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



def file_format_splitter(img_path:str, verbose:bool):
    # img_path = Path(img_path) #security, be sure that it is a Path object.   .absolute().as_posix()
    logger.info(f"Received file is of format {img_path.split('.')[-1].lower()}")
    #different strategies in case of different file format
    if img_path.split('.')[-1].lower() == "czi": #Light microscope format - CarlZeissImage
        key_pair = get_info_metadata_from_czi(img_path, verbose=verbose)
    elif img_path.split('.')[-1].lower() == "emi": #Electron microscope format
        img_path, key_pair = convert_emi_to_ometiff(img_path, verbose=verbose)
    
    return img_path, key_pair


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
        creation_date = metadata['Information']['Document'].get('CreationDate', None)
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
                     'Acquisition date':creation_date,
                     }
    
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
        data = file_reader(img_path) #Required to pair the emi and ser file!
        
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
    }

    date_object = datetime.datetime.strptime(dict_crawler(data, 'AcquireDate')[0], '%a %b %d %H:%M:%S %Y')
    key_pair['Acquisition date'] = date_object.strftime('%Y-%m-%d %H:%M:%S')
    
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
        acquisition_date=date_object.strftime('%Y-%m-%d %H:%M:%S'),
        
        pixels = model.Pixels(
            id="Pixels:0",
            dimension_order=dimension_order,
            type=str(img_array.dtype),
            size_x=dict_crawler(data, 'DetectorPixelHeight')[0],
            size_y=dict_crawler(data, 'DetectorPixelWidth')[0],
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

def delete(file_path:str):
    if os.path.exists(file_path):
        os.remove(file_path)
        logger.info(f"Successfully deleted temporary file: {file_path}")
    else:
        logger.warning(f"Temporary file not found for deletion: {file_path}")

def store_temp_file(img_obj):
    filename = img_obj.filename
    # Create subdirectories if needed
    file_path = os.path.join(config.UPLOAD_FOLDER, *os.path.split(filename))
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    img_obj.seek(0)            
    file_size = len(img_obj.read())
    img_obj.seek(0)
    
        # Save file to temporary directory
    if file_size <= config.MAX_SIZE_FULL_UPLOAD: #direct save
        logger.info(f"File {filename} is smaller than {config.MAX_SIZE_FULL_UPLOAD / (1024 * 1024)} MB. Full upload will be used.")
        img_obj.save(file_path) #one go save
    else: #chunk save
        logger.info(f"File {filename} is larger than {config.MAX_SIZE_FULL_UPLOAD / (1024 * 1024)} MB. Chunked upload will be used.")
        with open(file_path, 'wb') as f:
            while chunk := img_obj.stream.read(config.CHUNK_SIZE):
                f.write(chunk)
    
    return file_path, file_size
