import os
import re
from functools import wraps
from collections import namedtuple
from typing import Dict, Mapping, Tuple
from pathlib import Path
from jedi import settings
from jedi.file_io import FileIO
from jedi.parser_utils import get_cached_code_lines
from jedi.inference.base_value import ValueSet, NO_VALUES
from jedi.inference.gradual.stub_value import TypingModuleWrapper, StubModuleValue
from jedi.inference.value import ModuleValue
_jedi_path = Path(__file__).parent.parent.parent
TYPESHED_PATH = _jedi_path.joinpath('third_party', 'typeshed')
DJANGO_INIT_PATH = _jedi_path.joinpath('third_party', 'django-stubs', 'django-stubs', '__init__.pyi')
_IMPORT_MAP = dict(_collections='collections', _socket='socket')
PathInfo = namedtuple('PathInfo', 'path is_third_party')

def _create_stub_map(directory_path_info):
    """
    Create a mapping of an importable name in Python to a stub file.
    """
    stub_map = {}
    for root, dir_names, file_names in os.walk(directory_path_info.path):
        for file_name in file_names:
            if file_name.endswith('.pyi'):
                file_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(file_path, directory_path_info.path)
                import_name = os.path.splitext(rel_path.replace(os.path.sep, '.'))[0]
                stub_map[import_name] = PathInfo(file_path, directory_path_info.is_third_party)
    return stub_map
_version_cache: Dict[Tuple[int, int], Mapping[str, PathInfo]] = {}

def _cache_stub_file_map(version_info):
    """
    Returns a map of an importable name in Python to a stub file.
    """
    if version_info[:2] not in _version_cache:
        v_string = '.'.join(str(i) for i in version_info[:2])
        stub_map = {}
        for directory in ['stdlib', f'stdlib/{v_string}', 'third_party']:
            path = os.path.join(TYPESHED_PATH, directory)
            if os.path.isdir(path):
                stub_map.update(_create_stub_map(PathInfo(path, directory == 'third_party')))
        
        # Add django stubs if available
        if os.path.isfile(DJANGO_INIT_PATH):
            stub_map['django'] = PathInfo(DJANGO_INIT_PATH, True)
        
        _version_cache[version_info[:2]] = stub_map
    return _version_cache[version_info[:2]]

def _try_to_load_stub(inference_state, import_names, python_value_set, parent_module_value, sys_path):
    """
    Trying to load a stub for a set of import_names.

    This is modelled to work like "PEP 561 -- Distributing and Packaging Type
    Information", see https://www.python.org/dev/peps/pep-0561.
    """
    stub_module_name = '.'.join(import_names)
    stub_file_path = None
    
    # First, try to find a stub file in the typeshed
    version_info = inference_state.environment.version_info
    stub_map = _cache_stub_file_map(version_info)
    if stub_module_name in stub_map:
        stub_file_path = stub_map[stub_module_name].path
    
    # If not found in typeshed, try to find a stub file in the package
    if stub_file_path is None:
        for python_value in python_value_set:
            if python_value.is_stub():
                return ValueSet([python_value])
            if python_value.is_compiled():
                continue
            
            package_path = python_value.py__file__()
            if package_path is None:
                continue
            
            stub_name = import_names[-1] + '.pyi'
            stub_path = os.path.join(os.path.dirname(package_path), stub_name)
            if os.path.isfile(stub_path):
                stub_file_path = stub_path
                break
    
    if stub_file_path is None:
        return NO_VALUES
    
    stub_module_node = inference_state.parse(
        path=stub_file_path,
        cache=True,
        use_latest_grammar=True
    )
    stub_module = create_stub_module(
        inference_state,
        stub_file_path,
        stub_module_node,
        python_value_set,
        parent_module_value
    )
    return ValueSet([stub_module])
