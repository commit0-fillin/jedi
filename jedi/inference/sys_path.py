import os
import re
from pathlib import Path
from importlib.machinery import all_suffixes
from jedi.inference.cache import inference_state_method_cache
from jedi.inference.base_value import ContextualizedNode
from jedi.inference.helpers import is_string, get_str_or_none
from jedi.parser_utils import get_cached_code_lines
from jedi.file_io import FileIO
from jedi import settings
from jedi import debug
_BUILDOUT_PATH_INSERTION_LIMIT = 10

def _paths_from_assignment(module_context, expr_stmt):
    """
    Extracts the assigned strings from an assignment that looks as follows::

        sys.path[0:0] = ['module/path', 'another/module/path']

    This function is in general pretty tolerant (and therefore 'buggy').
    However, it's not a big issue usually to add more paths to Jedi's sys_path,
    because it will only affect Jedi in very random situations and by adding
    more paths than necessary, it usually benefits the general user.
    """
    try:
        expr = expr_stmt.children[0]
        if expr.type == 'power' and len(expr.children) > 1:
            if expr.children[0].value == 'sys' and expr.children[1].value == 'path':
                subscript = expr.children[2]
                if subscript.type == 'trailer' and subscript.children[0] == '[':
                    # Check if it's an insert operation (e.g., [0:0])
                    if ':' in subscript.children[1].get_code():
                        assigned = expr_stmt.children[2]
                        if assigned.type in ('testlist_star_expr', 'testlist'):
                            return [
                                elem.value.strip("'\"")
                                for elem in assigned.children
                                if elem.type == 'string'
                            ]
    except (AttributeError, IndexError):
        pass
    return []

def _paths_from_list_modifications(module_context, trailer1, trailer2):
    """ extract the path from either "sys.path.append" or "sys.path.insert" """
    try:
        if trailer1.children[0] == "." and trailer1.children[1].value in ('insert', 'append'):
            arg = trailer2.children[1]
            if arg.type == 'arglist':
                arg = arg.children[0]
            if arg.type == 'string':
                return [arg.value.strip("'\"")]
            elif arg.type == 'name':
                return [v.get_safe_value() for v in module_context.infer_node(arg)]
    except (AttributeError, IndexError):
        pass
    return []

@inference_state_method_cache(default=[])
def check_sys_path_modifications(module_context):
    """
    Detect sys.path modifications within module.
    """
    def get_sys_path_powers(module_node):
        try:
            for node in module_node.children:
                if node.type in ('power', 'atom_expr') and \
                        node.children[0].value == 'sys' and \
                        node.children[1].type == 'trailer' and \
                        node.children[1].children[1].value == 'path':
                    yield node
        except AttributeError:
            pass

    added = []
    for power in get_sys_path_powers(module_context.tree_node):
        if len(power.children) >= 4:
            added += _paths_from_list_modifications(
                module_context, power.children[-2], power.children[-1])
        elif power.parent.type == 'expr_stmt':
            added += _paths_from_assignment(module_context, power.parent)
    return added

def _get_buildout_script_paths(search_path: Path):
    """
    if there is a 'buildout.cfg' file in one of the parent directories of the
    given module it will return a list of all files in the buildout bin
    directory that look like python files.

    :param search_path: absolute path to the module.
    """
    parent = search_path.parent
    for _ in range(_BUILDOUT_PATH_INSERTION_LIMIT):
        if (parent / 'buildout.cfg').is_file():
            bin_path = parent / 'bin'
            if bin_path.is_dir():
                return [
                    str(p) for p in bin_path.iterdir()
                    if p.is_file() and p.suffix in ('.py', '') and p.stem != 'buildout'
                ]
        if parent == parent.parent:
            break
        parent = parent.parent
    return []

def transform_path_to_dotted(sys_path, module_path):
    """
    Returns the dotted path inside a sys.path as a list of names. e.g.

    >>> transform_path_to_dotted([str(Path("/foo").absolute())], Path('/foo/bar/baz.py').absolute())
    (('bar', 'baz'), False)

    Returns (None, False) if the path doesn't really resolve to anything.
    The second return part is if it is a package.
    """
    module_path = os.path.abspath(str(module_path))
    for p in sys_path:
        p = os.path.abspath(p)
        if module_path.startswith(p):
            rest = module_path[len(p):]
            split = [name for name in rest.split(os.path.sep) if name]
            if split and split[-1] == '__init__.py':
                split.pop()
                is_package = True
            elif split and split[-1].endswith('.py'):
                split[-1] = split[-1][:-3]
                is_package = False
            else:
                is_package = True
            return tuple(split), is_package
    return None, False
