"""
:mod:`jedi.inference.imports` is here to resolve import statements and return
the modules/classes/functions/whatever, which they stand for. However there's
not any actual importing done. This module is about finding modules in the
filesystem. This can be quite tricky sometimes, because Python imports are not
always that simple.

This module also supports import autocompletion, which means to complete
statements like ``from datetim`` (cursor at the end would return ``datetime``).
"""
import os
from pathlib import Path
from parso.python import tree
from parso.tree import search_ancestor
from jedi import debug
from jedi import settings
from jedi.file_io import FolderIO
from jedi.parser_utils import get_cached_code_lines
from jedi.inference import sys_path
from jedi.inference import helpers
from jedi.inference import compiled
from jedi.inference import analysis
from jedi.inference.utils import unite
from jedi.inference.cache import inference_state_method_cache
from jedi.inference.names import ImportName, SubModuleName
from jedi.inference.base_value import ValueSet, NO_VALUES
from jedi.inference.gradual.typeshed import import_module_decorator, create_stub_module, parse_stub_module
from jedi.inference.compiled.subprocess.functions import ImplicitNSInfo
from jedi.plugins import plugin_manager

class ModuleCache:

    def __init__(self):
        self._name_cache = {}

def _level_to_base_import_path(project_path, directory, level):
    """
    In case the level is outside of the currently known package (something like
    import .....foo), we can still try our best to help the user for
    completions.
    """
    if level == 0:
        return None, None
    
    base_path = os.path.normpath(directory)
    parent_directories = []
    for _ in range(level - 1):
        parent = os.path.dirname(base_path)
        if parent == base_path:
            return None, None
        parent_directories.append(os.path.basename(base_path))
        base_path = parent

    if os.path.basename(project_path) == os.path.basename(base_path):
        return None, None

    parent_directories.reverse()
    return parent_directories, base_path

class Importer:

    def __init__(self, inference_state, import_path, module_context, level=0):
        """
        An implementation similar to ``__import__``. Use `follow`
        to actually follow the imports.

        *level* specifies whether to use absolute or relative imports. 0 (the
        default) means only perform absolute imports. Positive values for level
        indicate the number of parent directories to search relative to the
        directory of the module calling ``__import__()`` (see PEP 328 for the
        details).

        :param import_path: List of namespaces (strings or Names).
        """
        debug.speed('import %s %s' % (import_path, module_context))
        self._inference_state = inference_state
        self.level = level
        self._module_context = module_context
        self._fixed_sys_path = None
        self._infer_possible = True
        if level:
            base = module_context.get_value().py__package__()
            if level <= len(base):
                base = tuple(base)
                if level > 1:
                    base = base[:-level + 1]
                import_path = base + tuple(import_path)
            else:
                path = module_context.py__file__()
                project_path = self._inference_state.project.path
                import_path = list(import_path)
                if path is None:
                    directory = project_path
                else:
                    directory = os.path.dirname(path)
                base_import_path, base_directory = _level_to_base_import_path(project_path, directory, level)
                if base_directory is None:
                    self._infer_possible = False
                else:
                    self._fixed_sys_path = [base_directory]
                if base_import_path is None:
                    if import_path:
                        _add_error(module_context, import_path[0], message='Attempted relative import beyond top-level package.')
                else:
                    import_path = base_import_path + import_path
        self.import_path = import_path

    @property
    def _str_import_path(self):
        """Returns the import path as pure strings instead of `Name`."""
        return [str(name) if isinstance(name, tree.Name) else name
                for name in self.import_path]

    def _get_module_names(self, search_path=None, in_module=None):
        """
        Get the names of all modules in the search_path. This means file names
        and not names defined in the files.
        """
        if search_path is None:
            search_path = self._inference_state.get_sys_path()

        names = []
        for path in search_path:
            try:
                contents = os.listdir(path)
            except OSError:
                # Invalid or non-existent directory
                continue

            for filename in contents:
                name, ext = os.path.splitext(filename)
                if ext in ('.py', '.pyi') or (ext == '' and os.path.isdir(os.path.join(path, filename))):
                    names.append(name)

        return sorted(set(names))

    def completion_names(self, inference_state, only_modules=False):
        """
        :param only_modules: Indicates wheter it's possible to import a
            definition that is not defined in a module.
        """
        module_names = self._get_module_names()
        if only_modules:
            return [ImportName(inference_state, string_name=name) for name in module_names]
        
        # If not only modules, we need to include submodule names as well
        names = []
        for name in module_names:
            names.append(ImportName(inference_state, string_name=name))
            try:
                module = import_module(inference_state, [name], None, sys_path=self._fixed_sys_path)
                if module:
                    names.extend(module.sub_modules_dict().values())
            except ImportError:
                pass
        return names

@plugin_manager.decorate()
@import_module_decorator
def import_module(inference_state, import_names, parent_module_value, sys_path):
    """
    This method is very similar to importlib's `_gcd_import`.
    """
    if parent_module_value is None:
        module = inference_state.builtins_module
    else:
        module = parent_module_value

    for name in import_names:
        try:
            module = module.py__getattribute__(name)
        except AttributeError:
            # If the module doesn't exist, try to load it
            module = load_module_from_path(inference_state, name, sys_path)
            if module is None:
                raise ImportError(f"No module named '{name}'")
    
    return module

def load_module_from_path(inference_state, file_io, import_names=None, is_package=None):
    """
    This should pretty much only be used for get_modules_containing_name. It's
    here to ensure that a random path is still properly loaded into the Jedi
    module structure.
    """
    module_node = inference_state.parse(file_io=file_io)
    if is_package is None:
        is_package = is_package_directory(file_io)

    if import_names is None:
        e_sys_path = inference_state.get_sys_path()
        import_names = sys_path.transform_path_to_dotted(file_io.path, e_sys_path)
    
    module = ModuleValue(
        inference_state, module_node,
        file_io=file_io,
        string_names=import_names,
        code_lines=get_cached_code_lines(inference_state.grammar, file_io.path),
        is_package=is_package
    )
    return module

def iter_module_names(inference_state, module_context, search_path, module_cls=ImportName, add_builtin_modules=True):
    """
    Get the names of all modules in the search_path. This means file names
    and not names defined in the files.
    """
    yielded = set()

    # Add modules from search_path
    for name in _get_module_names(search_path):
        if name not in yielded:
            yielded.add(name)
            yield module_cls(inference_state, name)

    # Add builtin modules if requested
    if add_builtin_modules:
        for name in inference_state.compiled_subprocess.get_builtin_module_names():
            if name not in yielded:
                yielded.add(name)
                yield module_cls(inference_state, name)

    # Add custom modules from sys.path
    for path in inference_state.get_sys_path():
        for name in _get_module_names([path]):
            if name not in yielded:
                yielded.add(name)
                yield module_cls(inference_state, name)

def _get_module_names(search_path):
    names = []
    for path in search_path:
        try:
            contents = os.listdir(path)
        except OSError:
            continue

        for filename in contents:
            name, ext = os.path.splitext(filename)
            if ext in ('.py', '.pyi') or (ext == '' and os.path.isdir(os.path.join(path, filename))):
                names.append(name)

    return sorted(set(names))
