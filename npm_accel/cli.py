# Accelerator for npm, the Node.js package manager.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: March 3, 2020
# URL: https://github.com/xolox/python-npm-accel

"""
Usage: npm-accel [OPTIONS] [DIRECTORY]

The npm-accel program is a wrapper for npm (the Node.js package manager) that
optimizes one specific use case: Building a `node_modules' directory from a
`package.json' file as quickly as possible.

It works on the assumption that you build `node_modules' directories more
frequently then you change the contents of `package.json' files, because it
computes a fingerprint of the dependencies and uses that fingerprint as a
cache key, to cache the complete `node_modules' directory in a tar archive.

Supported options:

  -p, --production

    Don't install modules listed in `devDependencies'.

  -i, --installer=NAME

    Set the installer to use. Supported values for NAME are `npm', `yarn',
    `pnpm' and `npm-cache'. When yarn is available it will be selected as the
    default installer, otherwise the default is npm.

  -u, --update

    Don't read from the cache but do write to the cache. If you suspect a cache
    entry to be corrupt you can use --update to 'refresh' the cache entry.

  -n, --no-cache

    Disallow writing to the cache managed by npm-accel (reading is still
    allowed though). This option does not disable internal caching
    performed by npm, yarn, pnpm and npm-cache.

  -c, --cache-directory=DIR

    Set the pathname of the directory where the npm-accel cache is stored.

  -l, --cache-limit=COUNT

    Set the maximum number of tar archives to preserve. When the cache
    directory contains more than COUNT archives the least recently used
    archives are removed. Defaults to 20.

    The environment variable $NPM_ACCEL_CACHE_LIMIT provides a convenient
    way to customize this option in CI and build environments.

  -b, --benchmark

    Benchmark and compare the following installation methods:

    1. npm install
    2. yarn
    3. pnpm
    4. npm-accel
    5. npm-cache

    The first method performs no caching (except for the HTTP caching that's
    native to npm) while the other four methods each manage their own cache
    (that is to say, the caching logic of npm-accel is only used in step 4).

    Warning: Benchmarking wipes the caches managed by npm, yarn, pnpm,
    npm-accel and npm-cache in order to provide a fair comparison (you
    can override this in the Python API but not on the command line).

  -r, --remote-host=SSH_ALIAS

    Operate on a remote system instead of the local system. The
    SSH_ALIAS argument gives the SSH alias of the remote host.

  -v, --verbose

    Increase logging verbosity (can be repeated).

  -q, --quiet

    Decrease logging verbosity (can be repeated).

  --version

    Report the version of npm-accel.

  -h, --help

    Show this message and exit.
"""

# Standard library modules.
import getopt
import logging
import os
import sys

# External dependencies.
import coloredlogs
from executor.contexts import create_context
from humanfriendly import parse_path
from humanfriendly.terminal import output, usage, warning

# Modules included in our package.
from npm_accel import __version__, NpmAccel
from npm_accel.exceptions import NpmAccelError

# Initialize a logger for this module.
logger = logging.getLogger(__name__)


def main():
    """Command line interface for the ``npm-accel`` program."""
    # Initialize logging to the terminal and system log.
    coloredlogs.install(syslog=True)
    # Command line option defaults.
    program_opts = {}
    context_opts = {}
    directory = None
    action = "install"
    # Parse the command line arguments.
    try:
        options, arguments = getopt.getopt(
            sys.argv[1:],
            "pi:unc:l:br:vqh",
            [
                "production",
                "installer=",
                "update",
                "no-cache",
                "cache-directory=",
                "cache-limit=",
                "benchmark",
                "remote-host=",
                "verbose",
                "quiet",
                "version",
                "help",
            ],
        )
        for option, value in options:
            if option in ("-p", "--production"):
                program_opts["production"] = True
            elif option in ("-i", "--installer"):
                program_opts["installer_name"] = value
            elif option in ("-u", "--update"):
                program_opts["read_from_cache"] = False
                program_opts["write_to_cache"] = True
            elif option in ("-n", "--no-cache"):
                program_opts["write_to_cache"] = False
            elif option in ("-c", "--cache-directory"):
                program_opts["cache_directory"] = parse_path(value)
            elif option in ("-l", "--cache-limit"):
                program_opts["cache_limit"] = int(value)
            elif option in ("-b", "--benchmark"):
                action = "benchmark"
            elif option in ("-r", "--remote-host"):
                context_opts["ssh_alias"] = value
            elif option in ("-v", "--verbose"):
                coloredlogs.increase_verbosity()
            elif option in ("-q", "--quiet"):
                coloredlogs.decrease_verbosity()
            elif option == "--version":
                output(__version__)
                return
            elif option in ("-h", "--help"):
                usage(__doc__)
                return
            else:
                assert False, "Unhandled option!"
        if arguments:
            directory = arguments.pop(0)
            if arguments:
                raise Exception("Got more positional arguments than expected!")
        if not directory:
            if context_opts.get("ssh_alias"):
                raise Exception("When operating on a remote system the directory needs to be specified explicitly!")
            directory = os.getcwd()
    except Exception as e:
        warning("Error: Failed to parse command line arguments! (%s)" % e)
        sys.exit(1)
    # Perform the requested action(s).
    try:
        context = create_context(**context_opts)
        program_opts["context"] = context
        accelerator = NpmAccel(**program_opts)
        method = getattr(accelerator, action)
        method(directory)
    except NpmAccelError as e:
        warning("Error: %s", e)
        sys.exit(1)
    except Exception:
        logger.exception("Encountered unexpected exception! Aborting ..")
        sys.exit(1)
