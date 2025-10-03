import os
import pytest
from pathlib import Path

from omerofrontend.image_funcs import (get_info_metadata_from_czi, convert_emi_to_ometiff, convert_emd_to_ometiff,
                                       convert_tif_to_ometiff, convert_atlas_to_ometiff, convert_czi_to_ometiff)

def test_get_info_metadata_from_czi_file_not_found():
    fileName = Path('tests/data/test_image_no_exist.czi')
    with pytest.raises(FileNotFoundError) as excinfo:  
        get_info_metadata_from_czi(fileName)
    assert str(excinfo.value) == f"The file {fileName} does not exist."  


def test_get_info_metadata_from_czi_value_error():
    fileName = 'tests/data/fakefile.czi'
    with pytest.raises(ValueError) as excinfo:  
        get_info_metadata_from_czi(Path(fileName))
    assert str(excinfo.value) == f"Error opening or reading metadata: {fileName}"  
    assert True
    
def test_get_info_metadata_from_czi_metadata():
    fileName = 'tests/data/test_image.czi'
    meta_data = get_info_metadata_from_czi(Path(fileName))
    check_image_base_lm_metadata(meta_data)
    #also check czi specific meta data? 

def test_get_info_metadata_from_tif_metadata():
    fileName = 'tests/data/sample6_001.tif'
    p, meta_data = convert_tif_to_ometiff(fileName)
    check_image_base_lm_metadata(meta_data)

def test_get_info_metadata_from_mrc_metadata():
    atlasPair = {}
    atlasPair["xml"] = 'tests/data/Atlas_1.xml'
    atlasPair['mrc'] = 'tests/data/Atlas_1.mrc'
    converted_path, key_pair = convert_atlas_to_ometiff(atlasPair)
    check_image_base_em_metadata(key_pair)
    
def test_convert_emi_to_ometiff_file_not_found():
    fileName = 'tests/data/test_image_no_exist.emi'
    with pytest.raises(FileNotFoundError) as excinfo:  
        _, _ = convert_emi_to_ometiff(fileName)#type: ignore
    assert str(excinfo.value) == f"The file {fileName} does not exist."  
    
def test_convert_emi_to_ometiff():
    fileName = 'tests/data/49944_A1_0001.emi'
    p, dict = convert_emi_to_ometiff(fileName)
    assert p == 'tests/data/49944_A1_0001.ome.tiff'
    check_image_base_em_metadata(dict)
    assert('Comment' in dict )
    #TODO: also check emi specific meta data?
    os.remove(p)  # Clean up the generated file after the test

def test_convert_emd_to_ometiff():
    fileName = 'tests/data/test_emd_file.emd'
    p, dict = convert_emd_to_ometiff(fileName)
    assert p == 'tests/data/test_emd_file.ome.tiff'
    check_image_base_em_metadata(dict)
    #TODO: also check emd specific meta data?
    os.remove(p)  # Clean up the generated file after the test

def test_convert_fibicstif_and_test_metadata():
    fileName = 'tests/data/fibics_test.tif'
    p, meta_data = convert_tif_to_ometiff(fileName)
    check_image_minimal_metadata(meta_data)
    assert p == 'tests/data/fibics_test.ome.tiff'
    os.remove(p) # Clean up the generated file after the test

def test_convert_czi700():
    fileName = 'tests/data/test_700-conversion.czi' 
    files = convert_czi_to_ometiff(fileName)
    assert isinstance(files, list)
    assert files[0] == 'tests/data/test_700-conversion.ome.tiff'
    os.remove(files[0])  # Clean up the generated file after the test

# def test_convert_mrc_to_ometiff():
#     fileNameMrc = 'tests/data/Atlas_1.mrc'
#     fileNameXml = 'tests/data/Atlas_1.xml'
#     atlasPair = {}
#     atlasPair['xml'] = fileNameXml
#     atlasPair['mrc'] = fileNameMrc
#     p, dict = convert_atlas_to_ometiff(atlasPair)
#     assert p == 'tests/data/Atlas_1.ome.tiff'
#     check_image_base_em_metadata(dict)
#     os.remove(p)  # Clean up the generated file after the test
    
def check_image_base_metadata(meta_dict):
    assert('Microscope' in meta_dict)
    assert('Lens Magnification' in meta_dict)
    assert('Image type' in meta_dict)
    assert('Image Size X' in meta_dict)
    assert('Image Size Y' in meta_dict)
    assert('Acquisition date' in meta_dict)
    
def check_image_base_lm_metadata(meta_dict):
    check_image_base_metadata(meta_dict)    
    #assert('Lens NA' in meta_dict) #this is only for czi
    assert('Image type' in meta_dict)
    assert('Physical pixel size X' in meta_dict)
    assert('Physical pixel size Y' in meta_dict)
    #assert('Description' in meta_dict)
    assert('Comment' in meta_dict )

def check_image_base_em_metadata(meta_dict):
    check_image_base_metadata(meta_dict)
    assert('Electron source' in meta_dict)
    assert('Beam tension' in meta_dict)
    assert('Camera' in meta_dict)
    assert('Defocus' in meta_dict)

def check_image_minimal_metadata(meta_dict):
    assert('Image Size X' in meta_dict)
    assert('Image Size Y' in meta_dict)
    assert('Acquisition date' in meta_dict)
    assert('Physical pixel size X' in meta_dict)
    assert('Physical pixel size Y' in meta_dict)
    assert('Microscope' in meta_dict)