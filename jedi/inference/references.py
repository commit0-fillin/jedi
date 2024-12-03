import os
import re
from parso import python_bytes_to_unicode
from jedi.debug import dbg
from jedi.file_io import KnownContentFileIO, FolderIO, FileIO
from jedi.inference.names import SubModuleName
from jedi.inference.imports import load_module_from_path
from jedi.inference.filters import ParserTreeFilter
from jedi.inference.gradual.conversion import convert_names

_IGNORE_FOLDERS = ('.tox', '.venv', '.mypy_cache', 'venv', '__pycache__')
_IGNORE_FOLDERS = ('.tox', '.venv', '.mypy_cache', 'venv', '__pycache__')
_OPENED_FILE_LIMIT = 2000
"\nStats from a 2016 Lenovo Notebook running Linux:\nWith os.walk, it takes about 10s to scan 11'000 files (without filesystem\ncaching). Once cached it only takes 5s. So it is expected that reading all\nthose files might take a few seconds, but not a lot more.\n"
_PARSED_FILE_LIMIT = 30
'\nFor now we keep the amount of parsed files really low, since parsing might take\neasily 100ms for bigger files.\n'

def get_module_contexts_containing_name(inference_state, module_contexts, name, limit_reduction=1):
    """
    Search a name in the directories of modules.

    :param limit_reduction: Divides the limits on opening/parsing files by this
        factor.
    """
    def check_directory(folder_io):
        try:
            file_names = folder_io.list()
        except OSError:
            return
        
        for name in file_names:
            if name in _IGNORE_FOLDERS:
                continue
            
            path = os.path.join(folder_io.path, name)
            if os.path.isdir(path):
                yield from check_directory(FolderIO(path))
            elif name.endswith(('.py', '.pyi')):
                yield path

    def check_fs(file_io):
        try:
            accessed = False
            if file_io.path.endswith(('.py', '.pyi')):
                code = file_io.read()
                accessed = True
                if name in code:
                    module = load_module_from_path(inference_state, file_io)
                    yield module
            if not accessed and file_io.is_folder():
                yield from check_directory(file_io.as_folder_io())
        except OSError:
            return

    yielded_paths = set()
    for module_context in module_contexts:
        if module_context.file_io is None:
            continue
        file_io = module_context.file_io
        for file_io_or_path in check_fs(file_io):
            if isinstance(file_io_or_path, str):
                if file_io_or_path in yielded_paths:
                    continue
                yielded_paths.add(file_io_or_path)
                yield load_module_from_path(inference_state, FileIO(file_io_or_path))
            else:
                yield file_io_or_path
