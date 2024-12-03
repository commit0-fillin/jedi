import os
from parso import file_io

class AbstractFolderIO:

    def __init__(self, path):
        self.path = path

    def __repr__(self):
        return f'<{self.__class__.__name__}: {self.path}>'

class FolderIO(AbstractFolderIO):
    pass

class FileIOFolderMixin:
    pass

class ZipFileIO(file_io.KnownContentFileIO, FileIOFolderMixin):
    """For .zip and .egg archives"""

    def __init__(self, path, code, zip_path):
        super().__init__(path, code)
        self._zip_path = zip_path

class FileIO(file_io.FileIO, FileIOFolderMixin):
    pass

class KnownContentFileIO(file_io.KnownContentFileIO, FileIOFolderMixin):
    pass
