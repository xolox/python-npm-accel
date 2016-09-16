# Accelerator for npm, the Node.js package manager.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: September 16, 2016
# URL: https://github.com/xolox/python-npm-accel

"""Accelerator for npm, the Node.js package manager."""

# Standard library modules.
import codecs
import copy
import hashlib
import json
import os
import random

# External dependencies.
from chardet import detect
from executor import quote
from humanfriendly import Timer, format_path, format_table, parse_path
from humanfriendly.text import pluralize
from property_manager import PropertyManager, cached_property, mutable_property, required_property
from verboselogs import VerboseLogger

# Semi-standard module versioning.
__version__ = '0.2'

# Initialize a logger for this program.
logger = VerboseLogger(__name__)


class NpmAccel(PropertyManager):

    """Python API for the ``npm-accel`` program."""

    @required_property
    def context(self):
        """A command execution context created using :mod:`executor.contexts`."""

    @mutable_property
    def production(self):
        """
        :data:`True` if devDependencies_ should be ignored, :data:`False` to have them installed.

        The value of :attr:`production` defaults to :data:`True` when the
        environment variable ``$NODE_ENV`` is set to ``production``, otherwise
        it defaults to :data:`False`.

        .. _devDependencies: https://docs.npmjs.com/files/package.json#devdependencies
        """
        return os.environ.get('NODE_ENV') == 'production'

    @property
    def production_option(self):
        """
        One of the strings ``--production=true`` or ``--production=false`` (depending on :attr:`production`).

        This command line option is given to the ``npm install``, ``npm prune``
        and ``npm-cache`` programs to explicitly switch between production and
        development installations (``npm-fast-install`` is a special case
        because the option has no effect and so instead npm-accel implements
        a workaround).
        """
        return '--production=%s' % ('true' if self.production else 'false')

    @mutable_property
    def installer_name(self):
        """The name of the installer to use (one of the strings 'npm', 'npm-cache' or 'npm-fast-install')."""
        return 'npm'

    @property
    def installer_method(self):
        """
        The method corresponding to :attr:`installer_name` (a callable).

        :raises: :exc:`~exceptions.ValueError` if the value of
                 :attr:`installer_name` is not supported.
        """
        if self.installer_name == 'npm':
            return self.install_with_npm
        elif self.installer_name == 'npm-cache':
            return self.install_with_npm_cache
        elif self.installer_name == 'npm-fast-install':
            return self.install_with_npm_fast_install
        else:
            raise ValueError("The requested installer is not supported! (%r)" % self.installer_name)

    @mutable_property(cached=True)
    def cache_directory(self):
        """The absolute pathname of the directory where ``node_modules`` directories are cached (a string)."""
        return ('/var/cache/npm-accel'
                if os.getuid() == 0 and os.access('/var/cache', os.W_OK)
                else parse_path('~/.cache/npm-accel'))

    @mutable_property
    def read_from_cache(self):
        """:data:`True` if npm-accel is allowed to read from its cache, :data:`False` otherwise."""
        return self.installer_name != 'npm-cache'

    @mutable_property
    def write_to_cache(self):
        """:data:`True` if npm-accel is allowed to write to its cache, :data:`False` otherwise."""
        return self.installer_name != 'npm-cache'

    @cached_property
    def nodejs_version(self):
        """The output of the ``nodejs --version`` command (a string)."""
        return self.context.capture('nodejs', '--version')

    @cached_property
    def npm_version(self):
        """The output of the ``npm --version`` command (a string)."""
        return self.context.capture('npm', '--version')

    def install(self, directory, silent=False):
        """
        Install Node.js package(s) listed in a ``package.json`` file.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :returns: The result of :func:`extract_dependencies()`.
        """
        timer = Timer()
        package_file = os.path.join(directory, 'package.json')
        modules_directory = os.path.join(directory, 'node_modules')
        dependencies = self.extract_dependencies(package_file)
        logger.info("Installing Node.js package(s) in %s ..", format_path(directory))
        if dependencies:
            file_in_cache = self.get_cache_file(dependencies)
            logger.verbose("Checking the cache (%s) ..", file_in_cache)
            if self.read_from_cache and self.context.is_file(file_in_cache):
                self.install_from_cache(file_in_cache, modules_directory)
                logger.info("Done! Took %s to install %s from cache.",
                            timer, pluralize(len(dependencies), "dependency", "dependencies"))
            else:
                self.installer_method(directory, silent=silent)
                self.prune_dependencies(directory)
                if self.write_to_cache:
                    self.add_to_cache(modules_directory, file_in_cache)
                logger.info("Done! Took %s to install %s using npm.",
                            timer, pluralize(len(dependencies), "dependency", "dependencies"))
        else:
            logger.info("Nothing to do! (no dependencies to install)")
        return dependencies

    def extract_dependencies(self, package_file):
        """
        Extract the relevant dependencies from a ``package.json`` file.

        :param package_file: The pathname of the file (a string).
        :returns: A dictionary with the relevant dependencies.
        :raises: :exc:`MissingPackageFileError` when the given directory
                 doesn't contain a ``package.json`` file.

        If no dependencies are extracted from the ``package.json`` file
        a warning message is logged but it's not considered an error.
        """
        logger.verbose("Extracting dependencies (%s) ..", package_file)
        if not self.context.is_file(package_file):
            msg = "Missing package.json file! (%s)" % package_file
            raise MissingPackageFileError(msg)
        contents = self.context.read_file(package_file)
        metadata = json.loads(auto_decode(contents))
        dependencies = metadata.get('dependencies', {})
        if not self.production:
            dependencies.update(metadata.get('devDependencies', {}))
        if dependencies:
            logger.verbose("Extracted %s from package.json file.",
                           pluralize(len(dependencies), "dependency", "dependencies"))
        else:
            logger.warning("No dependencies extracted from %s file?!", package_file)
        return dependencies

    def get_cache_file(self, dependencies):
        """
        Compute the filename in the cache for the given dependencies.

        :param dependencies: A dictionary of dependencies like those returned
                             by :func:`extract_dependencies()`.
        :returns: The absolute pathname of the file in the cache (a string).
        """
        filename = '%s.tar' % self.get_cache_key(dependencies)
        return os.path.join(self.cache_directory, filename)

    def get_cache_key(self, dependencies):
        """
        Compute the cache key (fingerprint) for the given dependencies.

        :param dependencies: A dictionary of dependencies like those returned
                             by :func:`extract_dependencies()`.
        :returns: A 40-character hexadecimal SHA1 digest (a string).

        In addition to the dependencies the values of :attr:`nodejs_version`
        and :attr:`npm_version` are used to compute the cache key, this is to
        make sure that upgrades to Node.js and/or npm don't cause problems.
        """
        logger.debug("Computing cache key based on dependencies (%s), Node.js version (%s) and npm version (%s) ..",
                     dependencies, self.nodejs_version, self.npm_version)
        state = hashlib.sha1()
        state.update(repr(sorted(dependencies.items())).encode('ascii'))
        state.update(self.nodejs_version.encode('ascii'))
        state.update(self.npm_version.encode('ascii'))
        cache_key = state.hexdigest()
        logger.debug("Computed cache key is %s.", cache_key)
        return cache_key

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
        self.context.execute('mkdir', '-p', os.path.dirname(file_in_cache))
        temporary_file = '%s-%i' % (file_in_cache, random.randint(1, 100000))
        self.context.execute('tar', '-cf', temporary_file, '-C', modules_directory, '.')
        self.context.execute('mv', temporary_file, file_in_cache)
        logger.verbose("Took %s to add directory to cache.", timer)

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
        logger.info("Installing from cache (%s)..", format_path(file_in_cache))
        self.clear_directory(modules_directory)
        logger.verbose("Unpacking archive (%s) ..", file_in_cache)
        self.context.execute('tar', '-xf', file_in_cache, '-C', modules_directory)
        logger.verbose("Took %s to install from cache.", timer)

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
        if self.context.is_directory(directory):
            logger.verbose("Cleaning up existing directory (%s)..", directory)
            self.context.execute('rm', '-R', directory)
        logger.verbose("Creating directory (%s)..", directory)
        self.context.execute('mkdir', '-p', directory)

    def prune_dependencies(self, directory, silent=False):
        """
        Remove extraneous packages using `npm prune`_.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        .. _npm prune: https://docs.npmjs.com/cli/prune
        """
        timer = Timer()
        prune_command = ['npm', 'prune', self.production_option]
        logger.info("Running command: %s", quote(prune_command))
        self.context.execute(*prune_command, directory=directory, silent=silent)
        logger.verbose("Took %s to run 'npm prune'.", timer)

    def install_with_npm(self, directory, silent=False):
        """
        Use `npm install`_ to install dependencies.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        .. _npm install: https://docs.npmjs.com/cli/install
        """
        timer = Timer()
        install_command = ['npm', 'install', self.production_option]
        logger.info("Running command: %s", quote(install_command))
        self.context.execute(*install_command, directory=directory, silent=silent)
        logger.verbose("Took %s to install with npm.", timer)

    def install_with_npm_cache(self, directory, silent=False):
        """
        Use npm-cache_ to install dependencies.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        If the ``npm-cache`` command isn't already installed (globally) it will
        be installed (locally).

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
        program_name = 'npm-cache'
        if not self.context.test('which', program_name):
            program_name = os.path.join(directory, 'node_modules', '.bin', 'npm-cache')
            if not self.context.exists(program_name):
                logger.verbose("Installing npm-cache locally (because it's not globally installed) ..")
                self.context.execute('npm', 'install', 'npm-cache', directory=directory, silent=silent)
        install_command = [program_name, 'install', 'npm', self.production_option]
        logger.info("Running command: %s", quote(install_command))
        self.context.execute(*install_command, directory=directory, silent=silent)
        logger.verbose("Took %s to install with npm-cache.", timer)

    def install_with_npm_fast_install(self, directory, silent=False):
        """
        Use npm-fast-install_ to install dependencies.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.

        If the ``npm-fast-install`` command isn't already installed (globally)
        it will be installed (locally).

        .. warning:: When I tried out npm-fast-install_ for the first time I
                     found out that ``npm-fast-install --all`` fails to
                     actually install the devDependencies_. For more details
                     please refer to `npm-fast-install pull request 3`_.
                     Because this bug prevented me from evaluating how fast
                     npm-fast-install_ was I implemented a workaround that
                     temporarily rewrites the ``package.json`` file by merging
                     devDependencies_ into dependencies_. This approach has the
                     potential to corrupt the contents of ``package.json`` if
                     the process of restoring the original contents is
                     interrupted (e.g. when you abort npm-accel by pressing
                     Control-C and keeping it pressed for a while).

        .. _npm-fast-install: https://www.npmjs.com/package/npm-fast-install
        .. _npm-fast-install pull request 3: https://github.com/appcelerator/npm-fast-install/pull/3
        """
        timer = Timer()
        program_name = 'npm-fast-install'
        if not self.context.test('which', 'npm-fast-install'):
            program_name = os.path.join(directory, 'node_modules', '.bin', 'npm-fast-install')
            if not self.context.exists(program_name):
                logger.verbose("Installing npm-fast-install locally (because it's not globally installed) ..")
                self.context.execute('npm', 'install', 'npm-fast-install', directory=directory, silent=silent)
        package_file = os.path.join(directory, 'package.json')
        original_contents = self.context.read_file(package_file)
        metadata = dict(dependencies={}, devDependencies={})
        metadata.update(json.loads(auto_decode(original_contents)))
        need_patch = metadata['devDependencies'] and not self.production
        try:
            # Temporarily change the contents of the package.json file?
            if need_patch:
                logger.debug("Temporarily patching %s ..", package_file)
                patched_data = copy.deepcopy(metadata)
                patched_data['dependencies'].update(patched_data['devDependencies'])
                patched_data.pop('devDependencies')
                self.context.write_file(package_file, json.dumps(patched_data).encode('UTF-8'))
            # Run the npm-fast-install command.
            logger.info("Running command: %s", quote(program_name))
            self.context.execute(program_name, directory=directory, silent=silent)
        finally:
            # Restore the original contents of the package.json file?
            if need_patch:
                logger.debug("Restoring original contents of %s ..", package_file)
                self.context.write_file(package_file, original_contents)
        logger.verbose("Took %s to install with npm-fast-install.", timer)

    def benchmark(self, directory, iterations=2, reset_caches=True, silent=False):
        """
        Benchmark ``npm install``, ``npm-accel``, ``npm-cache`` and ``npm-fast-install``.

        :param directory: The pathname of a directory with a ``package.json`` file (a string).
        :param iterations: The number of times to run each installation command.
        :param reset_caches: :data:`True` to reset all caches before the first
                             iteration of each installation method,
                             :data:`False` otherwise.
        :param silent: Used to set :attr:`~executor.ExternalCommand.silent`.
        :raises: Any exceptions raised by the :mod:`executor.contexts` module.
        """
        results = []
        for name, label in (('npm', 'npm install'),
                            ('npm-accel', 'npm-accel'),
                            ('npm-cache', 'npm-cache install npm'),
                            ('npm-fast-install', 'npm-fast-install')):
            # Reset all caches before the first run of each installer?
            if reset_caches:
                self.clear_directory('~/.npm')               # npm
                self.clear_directory('~/.npm-fast-install')  # npm-fast-install
                self.clear_directory('~/.package_cache')     # npm-cache
                self.clear_directory(self.cache_directory)   # npm-accel
            # Run the test twice, the first time to prime the cache
            # and the second time to actually use the cache.
            for i in range(1, iterations + 1):
                iteration_label = "iteration %i/%i" % (i, iterations)
                logger.info("Testing '%s' (%s) ..", label, iteration_label)
                self.clear_directory(os.path.join(directory, 'node_modules'))
                timer = Timer()
                if name == 'npm-accel':
                    self.installer_name = 'npm'
                    self.read_from_cache = True
                    self.write_to_cache = True
                else:
                    self.installer_name = name
                    self.read_from_cache = False
                    self.write_to_cache = False
                self.install(directory, silent=silent)
                results.append((label, iteration_label, str(timer)))
                logger.info("Took %s for '%s' (%s).", timer, label, iteration_label)
        print(format_table(results, column_names=["Approach", "Iteration", "Elapsed time"]))


def auto_decode(text):
    """
    Decode a byte string by guessing the text encoding.

    :param text: A byte string.
    :returns: A Unicode string.
    """
    if text.startswith(codecs.BOM_UTF8):
        encoding = 'utf-8-sig'
    else:
        result = detect(text)
        encoding = result['encoding']
    return codecs.decode(text, encoding)


class MissingPackageFileError(Exception):

    """Raised when the given directory doesn't contain a ``package.json`` file."""
