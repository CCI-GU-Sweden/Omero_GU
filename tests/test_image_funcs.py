import pytest
from pathlib import Path

from omerofrontend.image_funcs import get_info_metadata_from_czi, convert_emi_to_ometiff

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
    check_image_base_metadata(meta_data)
    #also check czi specific meta data? 
    
def test_convert_emi_to_ometiff_file_not_found():
    fileName = 'tests/data/test_image_no_exist.emi'
    with pytest.raises(FileNotFoundError) as excinfo:  
        p, dict = convert_emi_to_ometiff(Path(fileName))#type: ignore
    assert str(excinfo.value) == f"The file {fileName} does not exist."  
    

# def test_file_format_splitter_czi_as_str():
#     fileName = 'tests/data/test_image.czi'
    
#     with open(fileName, "rb") as f:
#         file_storage = FileStorage(
#             stream=f,
#             filename="test_image.czi",      # You can set this to any filename you want
#             content_type="image/x-czi" # Optional: set the content type
#         ) 
#         fileData = FileData([file_storage])
#         #fileData.setFileSizes(fileSizes)
#         #fileData.setTempFilePaths(filePaths)
        
#         meta_data = file_format_splitter(fileData)
#         check_image_base_metadata(meta_data)

    
def check_image_base_metadata(meta_dict):
    
    assert(meta_dict['Microscope'])
    assert(meta_dict['Lens Magnification'])
    assert(meta_dict['Lens NA'])
    assert(meta_dict['Image type'])
    assert(meta_dict['Physical pixel size X'])
    assert(meta_dict['Physical pixel size Y'])
    assert(meta_dict['Image Size X'])
    assert(meta_dict['Image Size Y'])
    assert('Comment' in meta_dict )
    assert('Description' in meta_dict)
    assert(meta_dict['Acquisition date'])
    
    
    