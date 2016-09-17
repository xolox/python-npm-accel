# Accelerator for npm, the Node.js package manager.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: September 17, 2016
# URL: https://github.com/xolox/python-npm-accel

"""Custom exceptions that are raised explicitly by npm-accel."""


class NpmAccelError(Exception):

    """Base class for exceptions that are raised explicitly by npm-accel."""


class MissingPackageFileError(NpmAccelError):

    """Raised when the given directory doesn't contain a ``package.json`` file."""


class MissingNodeInterpreterError(NpmAccelError):

    """Raised when the Node.js interpreter is not available on the ``$PATH``."""
