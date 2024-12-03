import sys
import os
import inspect
import importlib
from pathlib import Path
from zipfile import ZipFile
from zipimport import zipimporter, ZipImportError
from importlib.machinery import all_suffixes
from jedi.inference.compiled import access
from jedi import debug
from jedi import parser_utils
from jedi.file_io import KnownContentFileIO, ZipFileIO

def get_module_info(inference_state, sys_path=None, full_name=None, **kwargs):
    """
    Returns Tuple[Union[NamespaceInfo, FileIO, None], Optional[bool]]
    """
    if sys_path is None:
        sys_path = sys.path

    module_name = full_name.split('.')[-1] if full_name else None
    
    try:
        file, path, is_pkg = _find_module(module_name, sys_path, full_name)
    except ImportError:
        return None, None

    if file is None:  # builtin module
        return ImplicitNSInfo(full_name, [path]), True
    
    try:
        return KnownContentFileIO(path, file.read()), is_pkg
    finally:
        file.close()

def _test_raise_error(inference_state, exception_type):
    """
    Raise an error to simulate certain problems for unit tests.
    """
    exception = getattr(builtins, exception_type)
    raise exception("Test exception")

def _test_print(inference_state, stderr=None, stdout=None):
    """
    Force some prints in the subprocesses. This exists for unit tests.
    """
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)

def _get_init_path(directory_path):
    """
    The __init__ file can be searched in a directory. If found return it, else
    None.
    """
    for suffix in all_suffixes():
        init_path = os.path.join(directory_path, '__init__' + suffix)
        if os.path.exists(init_path):
            return init_path
    return None

def _find_module(string, path=None, full_name=None, is_global_search=True):
    """
    Provides information about a module.

    This function isolates the differences in importing libraries introduced with
    python 3.3 on; it gets a module name and optionally a path. It will return a
    tuple containin an open file for the module (if not builtin), the filename
    or the name of the module if it is a builtin one and a boolean indicating
    if the module is contained in a package.
    """
    if full_name is None:
        full_name = string

    try:
        module_spec = importlib.util.find_spec(full_name, path)
    except (ImportError, AttributeError, ValueError, SystemError, SyntaxError):
        # This might happen if there's a sys.path that is not a directory or
        # a zip file (see #491) or if the directory is not readable.
        return None, None, False

    if module_spec is None:
        return None, None, False

    if module_spec.loader is None:  # namespace package
        return None, list(module_spec.submodule_search_locations)[0], True

    # We try to find the actual path of the module. This is especially
    # important if it's a namespace package where the spec.origin is None.
    if module_spec.origin in {None, 'namespace'}:
        path = list(module_spec.submodule_search_locations)[0]
    else:
        path = module_spec.origin

    is_package = module_spec.loader.is_package(full_name) if hasattr(module_spec.loader, 'is_package') else False

    if module_spec.loader.__class__.__name__ == 'BuiltinImporter':
        # The file is None for builtin modules.
        return None, path, is_package
    elif module_spec.loader.__class__.__name__ == 'ExtensionFileLoader':
        # The file is None for extension modules.
        return None, path, is_package
    else:
        file = None
        if os.path.exists(path):
            file = open(path, 'rb')
        elif zipimporter is not None:
            try:
                archive_path, internal_path = path.split('.zip' + os.path.sep)
                archive_path += '.zip'
                zip_importer = zipimporter(archive_path)
                file = ZipFile(archive_path).open(internal_path)
            except (ValueError, ZipImportError):
                pass

        return file, path, is_package

def _get_source(loader, fullname):
    """
    This method is here as a replacement for SourceLoader.get_source. That
    method returns unicode, but we prefer bytes.
    """
    try:
        source = loader.get_source(fullname)
    except ImportError:
        return None

    if source is None:
        return None

    if isinstance(source, str):
        return source.encode('utf-8')
    return source

class ImplicitNSInfo:
    """Stores information returned from an implicit namespace spec"""

    def __init__(self, name, paths):
        self.name = name
        self.paths = paths
