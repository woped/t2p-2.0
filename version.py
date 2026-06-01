"""
Version and metadata information for the T2P service.
"""

__version__ = "2.0.0"
__service_name__ = "T2P - Text to Process"
__description__ = "Service for converting text to BPMN process models"
__author__ = "WoPeD Team"
__license__ = "See LICENSE file"

# Build information (can be populated during CI/CD)
__build_date__ = None
__git_commit__ = None

# API version
__api_version__ = "v2"


def get_version_info():
    """
    Returns a dictionary with version and metadata information.
    """
    return {
        "version": __version__,
        "service_name": __service_name__,
        "description": __description__,
        "author": __author__,
        "license": __license__,
        "api_version": __api_version__,
        "build_date": __build_date__,
        "git_commit": __git_commit__,
    }
