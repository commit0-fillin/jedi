"""
Environments are a way to activate different Python versions or Virtualenvs for
static analysis. The Python binary in that environment is going to be executed.
"""
import os
import sys
import hashlib
import filecmp
from collections import namedtuple
from shutil import which
from jedi.cache import memoize_method, time_cache
from jedi.inference.compiled.subprocess import CompiledSubprocess, InferenceStateSameProcess, InferenceStateSubprocess
import parso
_VersionInfo = namedtuple('VersionInfo', 'major minor micro')
_SUPPORTED_PYTHONS = ['3.12', '3.11', '3.10', '3.9', '3.8', '3.7', '3.6']
_SAFE_PATHS = ['/usr/bin', '/usr/local/bin']
_CONDA_VAR = 'CONDA_PREFIX'
_CURRENT_VERSION = '%s.%s' % (sys.version_info.major, sys.version_info.minor)

class InvalidPythonEnvironment(Exception):
    """
    If you see this exception, the Python executable or Virtualenv you have
    been trying to use is probably not a correct Python version.
    """

class _BaseEnvironment:
    pass

class Environment(_BaseEnvironment):
    """
    This class is supposed to be created by internal Jedi architecture. You
    should not create it directly. Please use create_environment or the other
    functions instead. It is then returned by that function.
    """
    _subprocess = None

    def __init__(self, executable, env_vars=None):
        self._start_executable = executable
        self._env_vars = env_vars
        self._get_subprocess()

    def __repr__(self):
        version = '.'.join((str(i) for i in self.version_info))
        return '<%s: %s in %s>' % (self.__class__.__name__, version, self.path)

    @memoize_method
    def get_sys_path(self):
        """
        The sys path for this environment. Does not include potential
        modifications from e.g. appending to :data:`sys.path`.

        :returns: list of str
        """
        return self._get_subprocess().get_sys_path()

class _SameEnvironmentMixin:

    def __init__(self):
        self._start_executable = self.executable = sys.executable
        self.path = sys.prefix
        self.version_info = _VersionInfo(*sys.version_info[:3])
        self._env_vars = None

class SameEnvironment(_SameEnvironmentMixin, Environment):
    pass

class InterpreterEnvironment(_SameEnvironmentMixin, _BaseEnvironment):
    def __init__(self):
        super().__init__()
        self._get_subprocess = lambda: InferenceStateSameProcess(self)

def _get_virtual_env_from_var(env_var='VIRTUAL_ENV'):
    """Get virtualenv environment from VIRTUAL_ENV environment variable.

    It uses `safe=False` with ``create_environment``, because the environment
    variable is considered to be safe / controlled by the user solely.
    """
    virtual_env = os.environ.get(env_var)
    if virtual_env is not None:
        return create_environment(virtual_env, safe=False)
    return None

def get_default_environment():
    """
    Tries to return an active Virtualenv or conda environment.
    If there is no VIRTUAL_ENV variable or no CONDA_PREFIX variable set
    set it will return the latest Python version installed on the system. This
    makes it possible to use as many new Python features as possible when using
    autocompletion and other functionality.

    :returns: :class:`.Environment`
    """
    virtual_env = _get_virtual_env_from_var()
    if virtual_env is not None:
        return virtual_env

    conda_env = _get_virtual_env_from_var(_CONDA_VAR)
    if conda_env is not None:
        return conda_env

    return get_system_environment(_CURRENT_VERSION)

def find_virtualenvs(paths=None, *, safe=True, use_environment_vars=True):
    """
    :param paths: A list of paths in your file system to be scanned for
        Virtualenvs. It will search in these paths and potentially execute the
        Python binaries.
    :param safe: Default True. In case this is False, it will allow this
        function to execute potential `python` environments. An attacker might
        be able to drop an executable in a path this function is searching by
        default. If the executable has not been installed by root, it will not
        be executed.
    :param use_environment_vars: Default True. If True, the VIRTUAL_ENV
        variable will be checked if it contains a valid VirtualEnv.
        CONDA_PREFIX will be checked to see if it contains a valid conda
        environment.

    :yields: :class:`.Environment`
    """
    if use_environment_vars:
        for env_var in ['VIRTUAL_ENV', _CONDA_VAR]:
            env = _get_virtual_env_from_var(env_var)
            if env is not None:
                yield env

    if paths is None:
        paths = []

    for path in paths:
        try:
            executable_path = _get_executable_path(path, safe=safe)
            if executable_path is not None:
                yield create_environment(executable_path, safe=safe)
        except InvalidPythonEnvironment:
            pass

def find_system_environments(*, env_vars=None):
    """
    Ignores virtualenvs and returns the Python versions that were installed on
    your system. This might return nothing, if you're running Python e.g. from
    a portable version.

    The environments are sorted from latest to oldest Python version.

    :yields: :class:`.Environment`
    """
    for version in _SUPPORTED_PYTHONS:
        try:
            yield get_system_environment(version, env_vars=env_vars)
        except InvalidPythonEnvironment:
            pass

def get_system_environment(version, *, env_vars=None):
    """
    Return the first Python environment found for a string of the form 'X.Y'
    where X and Y are the major and minor versions of Python.

    :raises: :exc:`.InvalidPythonEnvironment`
    :returns: :class:`.Environment`
    """
    exe = which(f'python{version}') or which('python')
    if exe is None:
        raise InvalidPythonEnvironment(f"Could not find Python {version}")
    return create_environment(exe, env_vars=env_vars)

def create_environment(path, *, safe=True, env_vars=None):
    """
    Make it possible to manually create an Environment object by specifying a
    Virtualenv path or an executable path and optional environment variables.

    :raises: :exc:`.InvalidPythonEnvironment`
    :returns: :class:`.Environment`
    """
    executable = _get_executable_path(path, safe=safe)
    if executable is None:
        raise InvalidPythonEnvironment(f"Could not find a Python executable in {path}")
    return Environment(executable, env_vars=env_vars)

def _get_executable_path(path, safe=True):
    """
    Returns None if it's not actually a virtual env.
    """
    if os.path.isfile(path):
        if os.name == 'nt' and path.endswith('.exe'):
            return path
        elif os.access(path, os.X_OK):
            return path
    elif os.path.isdir(path):
        for name in ['python', 'python3']:
            exe = os.path.join(path, 'bin', name)
            if os.path.isfile(exe) and os.access(exe, os.X_OK):
                return exe

    if not safe:
        return which('python')
    return None
