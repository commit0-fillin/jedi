import pydoc
from contextlib import suppress
from typing import Dict, Optional
from jedi.inference.names import AbstractArbitraryName
try:
    from pydoc_data import topics
    pydoc_topics: Optional[Dict[str, str]] = topics.topics
except ImportError:
    pydoc_topics = None

class KeywordName(AbstractArbitraryName):
    api_type = 'keyword'

def imitate_pydoc(string):
    """
    It's not possible to get the pydoc's without starting the annoying pager
    stuff.
    """
    if pydoc_topics is None:
        return None

    # Remove leading/trailing whitespace and convert to lowercase
    string = string.strip().lower()

    # Check if the string is a valid keyword
    if string in pydoc_topics:
        # Return the documentation for the keyword
        return pydoc_topics[string]

    # If the keyword is not found, return None
    return None
