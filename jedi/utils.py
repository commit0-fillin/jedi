"""
Utilities for end-users.
"""
import __main__
from collections import namedtuple
import logging
import traceback
import re
import os
import sys
from jedi import Interpreter
READLINE_DEBUG = False

def setup_readline(namespace_module=__main__, fuzzy=False):
    """
    This function sets up :mod:`readline` to use Jedi in a Python interactive
    shell.

    If you want to use a custom ``PYTHONSTARTUP`` file (typically
    ``$HOME/.pythonrc.py``), you can add this piece of code::

        try:
            from jedi.utils import setup_readline
        except ImportError:
            # Fallback to the stdlib readline completer if it is installed.
            # Taken from http://docs.python.org/2/library/rlcompleter.html
            print("Jedi is not installed, falling back to readline")
            try:
                import readline
                import rlcompleter
                readline.parse_and_bind("tab: complete")
            except ImportError:
                print("Readline is not installed either. No tab completion is enabled.")
        else:
            setup_readline()

    This will fallback to the readline completer if Jedi is not installed.
    The readline completer will only complete names in the global namespace,
    so for example::

        ran<TAB>

    will complete to ``range``.

    With Jedi the following code::

        range(10).cou<TAB>

    will complete to ``range(10).count``, this does not work with the default
    cPython :mod:`readline` completer.

    You will also need to add ``export PYTHONSTARTUP=$HOME/.pythonrc.py`` to
    your shell profile (usually ``.bash_profile`` or ``.profile`` if you use
    bash).
    """
    try:
        import readline
    except ImportError:
        print("Readline is not installed. No tab completion is enabled.")
        return

    try:
        import jedi
    except ImportError:
        print("Jedi is not installed, falling back to readline")
        import rlcompleter
        readline.parse_and_bind("tab: complete")
        return

    class JediCompleter:
        def __init__(self, namespace_module, fuzzy):
            self.namespace_module = namespace_module
            self.fuzzy = fuzzy
            self.interpreter = jedi.Interpreter("", [namespace_module.__dict__])

        def complete(self, text, state):
            if state == 0:
                line = readline.get_line_buffer()
                cursor_pos = readline.get_endidx()

                completions = self.interpreter.complete(line, cursor_pos, fuzzy=self.fuzzy)
                self.matches = [c.name_with_symbols for c in completions]

            try:
                return self.matches[state]
            except IndexError:
                return None

    completer = JediCompleter(namespace_module, fuzzy)
    readline.set_completer(completer.complete)
    readline.parse_and_bind("tab: complete")

    if READLINE_DEBUG:
        def print_completer_debug(substitution, matches, longest_match_length):
            print(f"Completer debug: substitution={substitution}, matches={matches}, "
                  f"longest_match_length={longest_match_length}")
        readline.set_completion_display_matches_hook(print_completer_debug)

    print("Jedi completion is enabled.")

def version_info():
    """
    Returns a namedtuple of Jedi's version, similar to Python's
    ``sys.version_info``.
    """
    from jedi import __version__
    VersionInfo = namedtuple('VersionInfo', ['major', 'minor', 'micro', 'releaselevel', 'serial'])
    
    # Parse the version string
    version_parts = __version__.split('.')
    major = int(version_parts[0])
    minor = int(version_parts[1])
    
    # Handle the micro version and release level
    if len(version_parts) > 2:
        micro_parts = version_parts[2].split('-')
        micro = int(micro_parts[0])
        releaselevel = micro_parts[1] if len(micro_parts) > 1 else 'final'
    else:
        micro = 0
        releaselevel = 'final'
    
    # Set serial to 0 as it's not typically used in Jedi's version string
    serial = 0
    
    return VersionInfo(major, minor, micro, releaselevel, serial)
