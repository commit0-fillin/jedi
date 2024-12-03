import os
import time
from contextlib import contextmanager
from typing import Callable, Optional
_inited = False

def _lazy_colorama_init():
    """
    Lazily init colorama if necessary, not to screw up stdout if debugging is
    not enabled.

    This version of the function does nothing.
    """
    pass
try:
    if os.name == 'nt':
        raise ImportError
    else:
        from colorama import Fore, init
        from colorama import initialise

        def _lazy_colorama_init():
            """
            Lazily init colorama if necessary, not to screw up stdout is
            debug not enabled.

            This version of the function does init colorama.
            """
            global _inited
            if not _inited:
                init()
                _inited = True
except ImportError:

    class Fore:
        RED = ''
        GREEN = ''
        YELLOW = ''
        MAGENTA = ''
        RESET = ''
        BLUE = ''
NOTICE = object()
WARNING = object()
SPEED = object()
enable_speed = False
enable_warning = False
enable_notice = False
debug_function: Optional[Callable[[str, str], None]] = None
_debug_indent = 0
_start_time = time.time()

def increase_indent(func):
    """Decorator for making indented debug messages."""
    def wrapper(*args, **kwargs):
        global _debug_indent
        _debug_indent += 1
        try:
            return func(*args, **kwargs)
        finally:
            _debug_indent -= 1
    return wrapper

def dbg(message, *args, color='GREEN'):
    """ Looks at the stack, to see if a debug message should be printed. """
    global debug_function, _debug_indent
    if debug_function is None:
        return

    if args:
        message = message % args

    debug_function(color, '    ' * _debug_indent + message)

def print_to_stdout(color, str_out):
    """
    The default debug function that prints to standard out.

    :param str color: A string that is an attribute of ``colorama.Fore``.
    """
    _lazy_colorama_init()
    col = getattr(Fore, color)
    print(col + str_out + Fore.RESET)
