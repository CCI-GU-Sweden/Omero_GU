import os
import pytest
from pathlib import Path
from flask import Flask

from common.image_funcs import (get_ome_metadata, convert_emi_to_ometiff, convert_emd_to_ometiff,
                                       convert_tif_to_ometiff, convert_atlas_to_ometiff,
                                       is_valid_ip, get_client_ip, mapping)
from common import conf

def test_get_ome_metadata_from_czi_file_not_found():
    fileName = Path('tests/data/test_image_no_exist.czi')
    with pytest.raises(FileNotFoundError) as excinfo:  
        get_ome_metadata(fileName)
    assert str(excinfo.value) == f"The file {fileName} does not exist."  


def test_get_ome_metadata_from_czi_value_error():
    fileName = 'tests/data/fakefile.czi'
    with pytest.raises(ValueError) as excinfo:  
        get_ome_metadata(Path(fileName))
    assert str(excinfo.value) == f"Error opening or reading metadata: {fileName}"  
    assert True
    
def test_get_ome_metadata_from_czi_metadata():
    fileName = 'tests/data/test_image.czi'
    meta_data = get_ome_metadata(Path(fileName))
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
    assert p == 'tests/data/49944_A1_0001.ome.tif'
    check_image_base_em_metadata(dict)
    assert('Comment' in dict )
    #TODO: also check emi specific meta data?
    os.remove(p)  # Clean up the generated file after the test

def test_convert_emd_to_ometiff():
    fileName = 'tests/data/test_emd_file.emd'
    p, dict = convert_emd_to_ometiff(fileName)
    assert p == 'tests/data/test_emd_file.ome.tif'
    check_image_base_em_metadata(dict)
    #TODO: also check emd specific meta data?
    os.remove(p)  # Clean up the generated file after the test

def test_convert_fibicstif_and_test_metadata():
    fileName = 'tests/data/fibics_test.tif'
    p, meta_data = convert_tif_to_ometiff(fileName)
    check_image_minimal_metadata(meta_data)
    assert p == 'tests/data/fibics_test.ome.tiff'
    os.remove(p) # Clean up the generated file after the test


def test_is_valid_ip():
    assert is_valid_ip("10.1.2.3") is True
    assert is_valid_ip("2001:db8::1") is True
    assert is_valid_ip("not_an_ip") is False


def test_get_client_ip_trusted_proxy_uses_x_forwarded_for(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(conf, "TRUSTED_PROXY_IPS", ["10.250.8.63"])

    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "10.250.8.63"},
        headers={"X-Forwarded-For": "192.168.88.11, 10.250.8.63"},
    ):
        assert get_client_ip() == "192.168.88.11"


def test_get_client_ip_untrusted_proxy_ignores_x_forwarded_for(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(conf, "TRUSTED_PROXY_IPS", ["10.250.8.63"])

    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "10.250.8.99"},
        headers={"X-Forwarded-For": "192.168.88.11"},
    ):
        assert get_client_ip() == "10.250.8.99"


def test_get_client_ip_empty_trusted_proxy_list_ignores_x_forwarded_for(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(conf, "TRUSTED_PROXY_IPS", [])

    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "10.250.8.63"},
        headers={"X-Forwarded-For": "192.168.88.11"},
    ):
        assert get_client_ip() == "10.250.8.63"


def test_mapping_uses_id_mapping_before_ip_fallback(monkeypatch):
    monkeypatch.setattr(conf, "MICROSCOPE_ID_TO_NAME", {"TALOS": "Talos L120C"})
    monkeypatch.setattr(conf, "MICROSCOPE_IP_TO_NAME", {"192.168.88.11": "LSM 700"})

    assert mapping("TALOS", client_ip="192.168.88.11") == "Talos L120C"


def test_mapping_uses_ip_fallback_when_metadata_missing(monkeypatch):
    monkeypatch.setattr(conf, "MICROSCOPE_ID_TO_NAME", {})
    monkeypatch.setattr(conf, "MICROSCOPE_IP_TO_NAME", {"192.168.88.11": "LSM 700"})

    assert mapping(None, client_ip="192.168.88.11") == "LSM 700"
    assert mapping("", client_ip="192.168.88.11") == "LSM 700"
    
def check_image_base_metadata(meta_dict):
    assert('Microscope' in meta_dict)
    assert('Lens Magnification' in meta_dict)
    assert('Image type' in meta_dict)
    assert('Image Size X' in meta_dict)
    assert('Image Size Y' in meta_dict)
    assert('Acquisition date' in meta_dict)
    
def check_image_base_lm_metadata(meta_dict):
    check_image_base_metadata(meta_dict)    
    assert('Image type' in meta_dict)
    assert('Physical pixel size X' in meta_dict)
    assert('Physical pixel size Y' in meta_dict)

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