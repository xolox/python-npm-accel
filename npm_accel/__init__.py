# Accelerator for npm, the Node.js package manager.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: March 3, 2020
# URL: https://github.com/xolox/python-npm-accel

"""Accelerator for npm, the Node.js package manager."""

# Standard library modules.
import codecs
import contextlib
import hashlib
import json
import os
import re
import time

# External dependencies.
from chardet import detect
from executor import ExternalCommandFailed, quote
from humanfriendly import Timer, format_path, parse_path
from humanfriendly.tables import format_pretty_table
from humanfriendly.terminal import ansi_wrap, terminal_supports_colors
from humanfriendly.text import concatenate, pluralize
from property_manager import (
    PropertyManager,
    cached_property,
    clear_property,
    mutable_property,
    required_property,
    set_property,
)
from verboselogs import VerboseLogger

# Modules included in our package.
from npm_accel.exceptions import MissingPackageFileError, MissingNodeInterpreterError

KNOWN_INSTALLERS = ("npm", "yarn", "pnpm", "npm-cache")
"""A tuple of strings with the names of supported Node.js installers."""

# Semi-standard module versioning.
__version__ = "2.0"

# Initialize a logger for this program.
logger = VerboseLogger(__name__)


class NpmAccel(PropertyManager):

    """
    Python API for npm-accel.

    When you create an :class:`NpmAccel` object you're required to provide a
    :attr:`context` by passing a keyword argument to the constructor. The
    following writable properties can be set in this same way:
    :attr:`cache_directory`, :attr:`cache_limit`, :attr:`context`,
    :attr:`installer_name`, :attr:`production`, :attr:`read_from_cache`,
    :attr:`write_to_cache`. Once you've initialized npm-accel the most useful
    method to call is :func:`install()`.
    """

    @mutable_property(cached=True)
    def cache_directory(self):
        """The absolute pathname of the directory where ``node_modules`` directories are cached (a string)."""
        return (
            "/var/cache/npm-accel"
            if os.getuid() == 0 and os.access("/var/cache", os.W_OK)
            else parse_path("~/.cache/npm-accel")
        )

    @mutable_property
    def cache_limit(self):
        """
        The maximum number of tar archives to preserve in the cache (an integer, defaults to 20).

        The environment variable ``$NPM_ACCEL_CACHE_LIMIT`` can be used to override the
        default value of this option.
        """
        return int(os.environ.get("NPM_ACCEL_CACHE_LIMIT", "20"))

    @required_property
    def context(self):
        """A command execution context created using :mod:`executor.contexts`."""

    @cached_property
    def default_installer(self):
        """
        The name of the default installer to use (either 'npm' or 'yarn').

        When the yarn program is available in the ``$PATH`` the value of
        :attr:`default_installer` will be 'yarn', otherwise it falls back to
        'npm'.
        """
        if self.context.find_program("yarn"):
            logger.verbose("Selecting 'yarn' as default installer.")
            return "yarn"
        else:
            logger.verbose("Selecting 'npm' as default installer ('yarn' isn't installed).")
            return "npm"

    @property
    def installer_method(self):
        """
        The method corresponding to :attr:`installer_name` (a callable).

        :raises: :exc:`~exceptions.ValueError` if the value of
                 :attr:`installer_name` is not supported.
        """
        if self.installer_name == "npm":
            return self.install_with_npm
        elif self.installer_name == "yarn":
            return self.install_with_yarn
        elif self.installer_name == "pnpm":
            return self.install_with_pnpm
        elif self.installer_name == "npm-cache":
            return self.install_with_npm_cache
        else:
            raise ValueError("The requested installer is not supported! (%r)" % self.installer_name)

    @mutable_property(cached=True)
    def installer_name(self):
        """
        The name of the installer to use (one of the strings in :data:`KNOWN_INSTALLERS`).

        The default value of :attr:`installer_name` is :attr:`default_installer`.
        When you try to set :attr:`installer_name` to a name that is not included
        in :data:`KNOWN_INSTALLERS` a :exc:`~exceptions.ValueError` exception will
        be raised. When you try to set :attr:`installer_name` to the name of an
        installer that is not available a warning message will be logged and
        :attr:`default_installer` is used instead.
        """
        return self.default_installer

    @installer_name.setter
    def installer_name(self, value):
        """Validate the configured installer."""
        if value not in KNOWN_INSTALLERS:
            msg = "Invalid installer name %r! (the supported installers are %s)"
            raise ValueError(msg % (value, concatenate(KNOWN_INSTALLERS)))
        if self.context.find_program(value):
            logger.verbose("Selecting user defined installer %r (confirmed to be installed).", value)
        else:
            logger.warning(
                "User defined installer %r isn't available, falling back to %s.", value, self.default_installer
            )
            value = self.default_installer
        set_property(self, "installer_name", value)
        clear_property(self, "installer_version")

    @cached_property
    def installer_version(self):
        """The installer version according to the ``${installer_name} --version`` command (a string)."""
        return self.context.capture(self.installer_name, "--version")

    @cached_property
    def nodejs_interpreter(self):
        """
        The name of the Node.js interpreter (a string).

        The official name of the Node.js interpreter is simply ``node``,
        however on Debian based systems this name conflicts with another
        program provided by a system package (ax25-node_) which predates the
        existence of the Node.js interpreter. For this reason Debian calls the
        Node.js interpreter ``nodejs`` instead.

        This property first checks whether the ``nodejs`` program is available
        (because it is the less ambiguous name of the two) and if that fails it
        will check if the ``node`` program is available.

        :raises: :exc:`.MissingNodeInterpreterError` when neither of the
                 expected programs is available.

        .. _ax25-node: https://packages.debian.org/ax25-node
        """
        logger.debug("Discovering name of Node.js interpreter ..")
        for interpreter in "nodejs", "node":
            logger.debug("Checking availability of program: %s", interpreter)
            matches = self.context.find_program(interpreter)
            if matches:
                logger.debug("Found Node.js interpreter: %s", matches[0])
                return matches[0]
        raise MissingNodeInterpreterError("Missing Node.js interpreter! (expected to find 'nodejs' or 'node')")

    @cached_property
    def nodejs_version(self):
        """
        The output of the ``nodejs --version`` or ```node --version`` command (a string).

        :raises: :exc:`.MissingNodeInterpreterError` when neither of the
                 expected programs is available.
        """
        return self.context.capture(self.nodejs_interpreter, "--version")

    @mutable_property
    def production(self):
        """
        :data:`True` if devDependencies_ should be ignored, :data:`False` to have them installed.

        The value of :attr:`production` defaults to :data:`True` when the
        environment variable ``$NODE_ENV`` is set to ``production``, otherwise
        it defaults to :data:`False`.

        .. _devDependencies: https://docs.npmjs.com/files/package.json#devdependencies
        """
        return os.environ.get("NODE_ENV") == "production"

    @property
    def production_option(self):
        """
        One of the strings ``--production=true`` or ``--production=false`` (depending on :attr:`production`).

        This command line option is given to the ``npm install``, ``yarn``, ``pnpm`` and
        ``npm-cache`` commands to explicitly switch between production and development
        installations.
        """
        return "--production=%s" % ("true" if self.production else "false")

    @mutable_property
    def read_from_cache(self):
        """:data:`True` if npm-accel is allowed to read from its cache, :data:`False` otherwise."""
        return self.installer_name != "npm-cache"

    @mutable_property
    def write_to_cache(self):
        """:data:`True` if npm-accel is allowed to write to its cache, :data:`False` otherwise."""
        return self.installer_name != "npm-cache"

    def add_to_cache(self, modules_directory, file_in_cache):
        """
        Add a ``node_modules`` directory to the cache.

        :param modules_directory: The pathname of the ``node_modules`` directory (a string).
        :param file_in_cache: The pathname of the archive in the cache (a string).
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        This method generates the tar archive under a temporary name inside the
        cache directory and then renames it into place atomically, in order to
        avoid race conditions where multiple concurrent npm-accel commands try
        to use partially generated cache entries.

        The temporary names are generated by appending a randomly generated
        integer number to the original filename (with a dash to delimit the
        original filename from the number).
        """
        timer = Timer()
        logger.info("Adding to cache (%s) ..", format_path(file_in_cache))
        self.context.execute("mkdir", "-p", os.path.dirname(file_in_cache))
        with self.context.atomic_write(file_in_cache) as temporary_file:
            self.context.execute("tar", "-cf", temporary_file, "-C", modules_directory, ".")
        self.write_metadata(file_in_cache)
        logger.verbose("Took %s to add directory to cache.", timer)

    def benchmark(self, directory, iterations=2, reset_caches=True, silent=False):
        """
        Benchmark ``npm install``, ``yarn``, ``pnpm``, ``npm-accel`` and ``npm-cache``.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param iterations: The number of times to run each installation command.
        :param reset_caches: :data:`True` to reset all caches before the first
                             iteration of each installation method,
                             :data:`False` otherwise.
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.
        """
        results = []
        baseline = None
        for name, label in (
            ("npm", "npm install"),
            ("yarn", "yarn"),
            ("pnpm", "pnpm install"),
            ("npm-accel", "npm-accel"),
            ("npm-cache", "npm-cache install npm"),
        ):
            # Reset all caches before the first run of each installer?
            if reset_caches:
                self.clear_directory("~/.cache/yarn")
                self.clear_directory("~/.npm")
                self.clear_directory("~/.package_cache")  # npm-cache
                self.clear_directory("~/.pnpm-store")
                self.clear_directory(self.cache_directory)
                self.clear_directory(os.path.join(directory, "node_modules"))
            # Run the test twice, the first time to prime the cache
            # and the second time to actually use the cache.
            for i in range(1, iterations + 1):
                iteration_label = "%i of %i" % (i, iterations)
                logger.info("Testing '%s' (%s) ..", label, iteration_label)
                timer = Timer()
                if name == "npm-accel":
                    self.installer_name = self.default_installer
                    self.read_from_cache = True
                    self.write_to_cache = True
                else:
                    self.installer_name = name
                    self.read_from_cache = False
                    self.write_to_cache = False
                try:
                    self.install(directory, silent=silent)
                except ExternalCommandFailed:
                    label += " (failed)"
                    if terminal_supports_colors():
                        label = ansi_wrap(label, color="red")
                    results.append((label, iteration_label, str(timer), "-"))
                    # We skip the second iteration on failure.
                    break
                else:
                    if baseline is None:
                        baseline = timer.elapsed_time
                        percentage = "100%"
                    else:
                        percentage = "%.2f%%" % (timer.elapsed_time / (baseline / 100.0))
                    results.append((label, iteration_label, str(timer), percentage))
                logger.info("Took %s for '%s' (%s).", timer, label, iteration_label)
        print(format_pretty_table(results, column_names=["Approach", "Iteration", "Elapsed time", "Percentage"]))

    def clean_cache(self):
        """Remove old and unused archives from the cache directory."""
        timer = Timer()
        entries = []
        for file_in_cache in self.find_archives():
            cache_metadata = self.read_metadata(file_in_cache)
            last_accessed = cache_metadata.get("last-accessed", 0)
            entries.append((last_accessed, file_in_cache))
        to_remove = sorted(entries)[: -self.cache_limit]
        if to_remove:
            for last_used, file_in_cache in to_remove:
                logger.debug("Removing archive from cache: %s", format_path(file_in_cache))
                metadata_file = self.get_metadata_file(file_in_cache)
                self.context.execute("rm", "-f", file_in_cache, metadata_file)
            logger.verbose("Took %s to remove %s from cache.", timer, pluralize(len(to_remove), "archive"))
        else:
            logger.verbose("Wasted %s checking whether cache needs to be cleaned (it doesn't).", timer)

    def clear_directory(self, directory):
        """
        Make sure a directory exists and is empty.

        :param directory: The pathname of the directory (a string).
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        .. note:: If the directory already exists it will be removed and
                  recreated in order to remove any existing contents. This may
                  change the ownership and permissions of the directory. If
                  this ever becomes a problem for someone I can improve it to
                  preserve the metadata.
        """
        parsed_directory = parse_path(directory)
        formatted_directory = format_path(parsed_directory)
        if self.context.is_directory(parsed_directory):
            logger.verbose("Clearing directory contents (%s) ..", formatted_directory)
            self.context.execute("rm", "-fr", parsed_directory)
        else:
            logger.verbose("Creating directory (%s) ..", formatted_directory)
        self.context.execute("mkdir", "-p", parsed_directory)

    def extract_dependencies(self, package_file):
        """
        Extract the relevant dependencies from a ``package.json`` file.

        :param package_file: The pathname of the file (a string).
        :returns: A dictionary with the relevant dependencies.
        :raises: :exc:`.MissingPackageFileError` when the given directory
                 doesn't contain a ``package.json`` file.

        If no dependencies are extracted from the ``package.json`` file
        a warning message is logged but it's not considered an error.
        """
        formatted_path = format_path(package_file)
        logger.verbose("Extracting dependencies (%s) ..", formatted_path)
        if not self.context.is_file(package_file):
            msg = "Missing package.json file! (%s)" % package_file
            raise MissingPackageFileError(msg)
        contents = self.context.read_file(package_file)
        metadata = json.loads(auto_decode(contents))
        dependencies = metadata.get("dependencies", {})
        if not self.production:
            dependencies.update(metadata.get("devDependencies", {}))
        if dependencies:
            logger.verbose(
                "Extracted %s from package.json file.", pluralize(len(dependencies), "dependency", "dependencies")
            )
        else:
            logger.warning("No dependencies extracted from %s file?!", formatted_path)
        return dependencies

    def find_archives(self):
        """
        Find the absolute pathnames of the archives in the cache directory.

        :returns: A generator of filenames (strings).
        """
        pattern = re.compile(r"^[0-9A-F]{40}\.tar$", re.IGNORECASE)
        for entry in self.context.list_entries(self.cache_directory):
            if pattern.match(entry):
                yield os.path.join(self.cache_directory, entry)

    def get_cache_file(self, dependencies):
        """
        Compute the filename in the cache for the given dependencies.

        :param dependencies: A dictionary of dependencies like those returned
                             by :func:`extract_dependencies()`.
        :returns: The absolute pathname of the file in the cache (a string).
        """
        filename = "%s.tar" % self.get_cache_key(dependencies)
        return os.path.join(self.cache_directory, filename)

    def get_cache_key(self, dependencies):
        """
        Compute the cache key (fingerprint) for the given dependencies.

        :param dependencies: A dictionary of dependencies like those returned
                             by :func:`extract_dependencies()`.
        :returns: A 40-character hexadecimal SHA1 digest (a string).

        In addition to the dependencies the values of :attr:`nodejs_version` and
        :attr:`installer_version` are used to compute the cache key, this is to
        make sure that upgrades to Node.js and the installer don't cause problems.
        """
        logger.debug(
            "Computing cache key based on dependencies (%s), Node.js version (%s) and %s version (%s) ..",
            dependencies,
            self.nodejs_version,
            self.installer_name,
            self.installer_version,
        )
        state = hashlib.sha1()
        state.update(repr(sorted(dependencies.items())).encode("ascii"))
        state.update(self.nodejs_version.encode("ascii"))
        state.update(self.installer_version.encode("ascii"))
        cache_key = state.hexdigest()
        logger.debug("Computed cache key is %s.", cache_key)
        return cache_key

    def get_metadata_file(self, file_in_cache):
        """
        Get the name of the metadata file for a given file in the cache.

        :param file_in_cache: The pathname of the archive in the cache (a string).
        :returns: The absolute pathname of the metadata file (a string).
        """
        return re.sub(r"\.tar$", ".json", file_in_cache)

    def install(self, directory, silent=False):
        """
        Install Node.js package(s) listed in a ``package.json`` file.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :returns: The result of :func:`extract_dependencies()`.
        """
        timer = Timer()
        package_file = os.path.join(directory, "package.json")
        modules_directory = os.path.join(directory, "node_modules")
        dependencies = self.extract_dependencies(package_file)
        logger.info("Installing Node.js packages in %s ..", format_path(directory))
        if dependencies:
            file_in_cache = self.get_cache_file(dependencies)
            if self.read_from_cache:
                logger.verbose("Checking the cache (%s) ..", format_path(file_in_cache))
            if self.read_from_cache and self.context.is_file(file_in_cache):
                self.install_from_cache(file_in_cache, modules_directory)
                logger.info(
                    "Done! Took %s to install %s from cache.",
                    timer,
                    pluralize(len(dependencies), "dependency", "dependencies"),
                )
            else:
                self.clear_directory(modules_directory)
                with self.preserve_contents(package_file):
                    self.installer_method(directory, silent=silent)
                if self.write_to_cache:
                    self.add_to_cache(modules_directory, file_in_cache)
                logger.info(
                    "Done! Took %s to install %s using %s.",
                    timer,
                    pluralize(len(dependencies), "dependency", "dependencies"),
                    self.installer_name,
                )
            self.clean_cache()
        else:
            logger.info("Nothing to do! (no dependencies to install)")
        return dependencies

    def install_from_cache(self, file_in_cache, modules_directory):
        """
        Populate a ``node_modules`` directory by unpacking an archive from the cache.

        :param file_in_cache: The pathname of the archive in the cache (a string).
        :param modules_directory: The pathname of the ``node_modules`` directory (a string).
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        If the directory already exists it will be removed and recreated in
        order to remove any existing contents before the archive is unpacked.
        """
        timer = Timer()
        formatted_path = format_path(file_in_cache)
        logger.info("Installing from cache (%s)..", formatted_path)
        self.clear_directory(modules_directory)
        logger.verbose("Unpacking archive (%s) ..", formatted_path)
        self.context.execute("tar", "-xf", file_in_cache, "-C", modules_directory)
        self.write_metadata(file_in_cache)
        logger.verbose("Took %s to install from cache.", timer)

    def install_with_npm(self, directory, silent=False):
        """
        Use `npm install`_ to install dependencies.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        .. _npm install: https://docs.npmjs.com/cli/install
        """
        timer = Timer()
        install_command = ["npm", "install", self.production_option]
        logger.info("Running command: %s", quote(install_command))
        self.context.execute(*install_command, directory=directory, silent=silent)
        logger.verbose("Took %s to install with npm.", timer)

    def install_with_npm_cache(self, directory, silent=False):
        """
        Use npm-cache_ to install dependencies.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        .. warning:: When I tried out npm-cache_ for the second time I found
                     out that it unconditionally includes both production
                     dependencies_ and devDependencies_ in the cache keys that
                     it calculates, thereby opening the door for 'cache
                     poisoning'. For more details please refer to `npm-cache
                     issue 74`_. Currently npm-accel does not work around
                     this problem, so consider yourself warned ;-).

        .. _npm-cache: https://www.npmjs.com/package/npm-cache
        .. _dependencies: https://docs.npmjs.com/files/package.json#dependencies
        .. _devDependencies: https://docs.npmjs.com/files/package.json#devdependencies
        .. _npm-cache issue 74: https://github.com/swarajban/npm-cache/issues/74
        """
        timer = Timer()
        install_command = ["npm-cache", "install", "npm", self.production_option]
        logger.info("Running command: %s", quote(install_command))
        self.context.execute(*install_command, directory=directory, silent=silent)
        logger.verbose("Took %s to install with npm-cache.", timer)

    def install_with_pnpm(self, directory, silent=False):
        """
        Use pnpm_ to install dependencies.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        .. _pnpm: https://www.npmjs.com/package/pnpm
        """
        timer = Timer()
        install_command = ["pnpm", "install", self.production_option]
        logger.info("Running command: %s", quote(install_command))
        self.context.execute(*install_command, directory=directory, silent=silent)
        logger.verbose("Took %s to install with pnpm.", timer)

    def install_with_yarn(self, directory, silent=False):
        """
        Use yarn_ to install dependencies.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        .. _yarn: https://www.npmjs.com/package/yarn
        """
        timer = Timer()
        install_command = ["yarn", self.production_option]
        logger.info("Running command: %s", quote(install_command))
        self.context.execute(*install_command, directory=directory, silent=silent)
        logger.verbose("Took %s to install with yarn.", timer)

    @contextlib.contextmanager
    def preserve_contents(self, filename):
        """
        Restore the contents of a file after the context ends.

        :param filename: The pathname of the file (a string).
        :returns: A context manager.
        """
        contents = self.context.read_file(filename)
        yield
        self.context.write_file(filename, contents)

    def read_metadata(self, file_in_cache):
        """
        Read the metadata associated with an archive in the cache.

        :param file_in_cache: The pathname of the archive in the cache (a string).
        :returns: A dictionary with cache metadata. If the cache metadata file
                  cannot be read or its contents can't be parsed as JSON then
                  an empty dictionary is returned.
        """
        metadata_file = self.get_metadata_file(file_in_cache)
        if self.context.is_file(metadata_file):
            return json.loads(auto_decode(self.context.read_file(metadata_file)))
        else:
            return {}

    def write_metadata(self, file_in_cache, **overrides):
        """
        Create or update the metadata file associated with an archive in the cache.

        :param file_in_cache: The pathname of the archive in the cache (a string).
        :param overrides: Any key/value pairs to add to the metadata.
        """
        metadata_file = self.get_metadata_file(file_in_cache)
        cache_metadata = self.read_metadata(file_in_cache)
        logger.verbose(
            "%s metadata file (%s) ..", "Updating" if cache_metadata else "Creating", format_path(metadata_file)
        )
        cache_metadata.update(overrides)
        if "date-created" not in cache_metadata:
            cache_metadata["date-created"] = int(time.time())
        cache_metadata["last-accessed"] = int(time.time())
        cache_metadata["cache-hits"] = cache_metadata.get("cache-hits", 0) + 1
        with self.context.atomic_write(metadata_file) as temporary_file:
            self.context.write_file(temporary_file, json.dumps(cache_metadata).encode("UTF-8"))


def auto_decode(text):
    """
    Decode a byte string by guessing the text encoding.

    :param text: A byte string.
    :returns: A Unicode string.
    """
    if text.startswith(codecs.BOM_UTF8):
        encoding = "utf-8-sig"
    else:
        result = detect(text)
        encoding = result["encoding"]
    return codecs.decode(text, encoding)
