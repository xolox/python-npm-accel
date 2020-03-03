# Accelerator for npm, the Node.js package manager.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: March 3, 2020
# URL: https://github.com/xolox/python-npm-accel

"""Test suite for the `npm-accel` package."""

# Standard library modules.
import json
import logging
import os
import string

# External dependencies.
from executor import execute
from executor.contexts import create_context
from humanfriendly import Timer
from humanfriendly.text import random_string
from humanfriendly.testing import CustomSearchPath, MockedProgram, TemporaryDirectory, TestCase, run_cli

# Modules included in our package.
from npm_accel import NpmAccel
from npm_accel.cli import main
from npm_accel.exceptions import MissingPackageFileError, MissingNodeInterpreterError

# Initialize a logger for this module.
logger = logging.getLogger(__name__)


class NpmAccelTestCase(TestCase):

    """Container for the `npm-accel` test suite."""

    def test_missing_package_file_error(self):
        """Make sure an error is raised when the ``package.json`` file is missing."""
        with TemporaryDirectory() as project_directory:
            accelerator = NpmAccel(context=create_context())
            self.assertRaises(MissingPackageFileError, accelerator.install, project_directory)

    def test_node_binary_not_found_error(self):
        """Make sure an error is raised when the Node.js interpreter is missing."""
        with CustomSearchPath(isolated=True):
            accelerator = NpmAccel(context=create_context())
            self.assertRaises(MissingNodeInterpreterError, getattr, accelerator, "nodejs_interpreter")

    def test_multiple_arguments_error(self):
        """Make sure that multiple positional arguments raise an error."""
        returncode, output = run_cli(main, "a", "b")
        assert returncode != 0

    def test_cache_directory(self):
        """Make sure the default cache directory is writable."""
        accelerator = NpmAccel(context=create_context())
        directory = accelerator.cache_directory
        # The actual cache directory might not exist, but in that case one of
        # its parent directories is expected to exist and be writable for the
        # current user.
        for _ in range(100):
            try:
                assert os.access(directory, os.W_OK)
            except AssertionError:
                directory = os.path.dirname(directory)

    def test_implicit_local_directory(self):
        """Make sure local installation implicitly uses the working directory."""
        saved_cwd = os.getcwd()
        with TemporaryDirectory() as project_directory:
            write_package_metadata(project_directory)
            os.chdir(project_directory)
            try:
                returncode, output = run_cli(main)
                assert returncode == 0
            finally:
                os.chdir(saved_cwd)

    def test_explicit_remote_directory(self):
        """Make sure remote installation requires an explicit working directory."""
        returncode, output = run_cli(main, "--remote-host=localhost")
        assert returncode != 0

    def test_installer_selection(self):
        """Make sure the installer name is properly validated."""
        # Check that 'yarn' is the default installer when available.
        with MockedProgram(name="yarn"):
            accelerator = NpmAccel(context=create_context())
            assert accelerator.default_installer == "yarn"
        # Check that 'npm' is the default installer when 'yarn' isn't available.
        with CustomSearchPath(isolated=True):
            accelerator = NpmAccel(context=create_context())
            assert accelerator.default_installer == "npm"
        # Check that non-default installers are ignored when unavailable.
        with CustomSearchPath(isolated=True):
            accelerator = NpmAccel(context=create_context())
            accelerator.installer_name == "npm-cache"
            assert accelerator.installer_name == accelerator.default_installer
        # All of the following assertions can share the same program instance.
        accelerator = NpmAccel(context=create_context())
        # Make sure the default installer is 'npm' or 'yarn'.
        assert accelerator.installer_name in ("yarn", "npm")
        assert accelerator.installer_method in (accelerator.install_with_npm, accelerator.install_with_yarn)
        # Make sure 'npm' is supported.
        accelerator.installer_name = "npm"
        assert accelerator.installer_method == accelerator.install_with_npm
        # Make sure 'yarn' is supported.
        accelerator.installer_name = "yarn"
        assert accelerator.installer_method == accelerator.install_with_yarn
        # Make sure 'pnpm' is supported.
        accelerator.installer_name = "pnpm"
        assert accelerator.installer_method == accelerator.install_with_pnpm
        # Make sure 'npm-cache' is supported.
        accelerator.installer_name = "npm-cache"
        assert accelerator.installer_method == accelerator.install_with_npm_cache
        # Make sure invalid installer names raise an error.
        self.assertRaises(ValueError, setattr, accelerator, "installer_name", "bogus")

    def test_installers(self):
        """Make sure all of the supported installers actually work!"""
        for installer_name in "npm", "yarn", "pnpm", "npm-cache":
            with TemporaryDirectory() as cache_directory:
                with TemporaryDirectory() as project_directory:
                    write_package_metadata(project_directory, dict(npm="3.10.6"))
                    run_cli(
                        main,
                        "--installer=%s" % installer_name,
                        "--cache-directory=%s" % cache_directory,
                        project_directory,
                    )
                    self.check_program(project_directory, "npm", "help")

    def test_development_versus_production(self):
        """
        Make sure development and production installations both work.

        This test is intended to verify that development & production installs
        don't "poison" each other due to naively computed cache keys.
        """
        with TemporaryDirectory() as cache_directory:
            with TemporaryDirectory() as project_directory:
                write_package_metadata(project_directory, dict(path="0.12.7"), dict(npm="3.10.6"))
                # Install the production dependencies (a subset of the development dependencies).
                run_cli(main, "--cache-directory=%s" % cache_directory, "--production", project_directory)
                # We *do* expect the `path' production dependency to have been installed.
                assert os.path.exists(os.path.join(project_directory, "node_modules", "path"))
                # We *don't* expect the `npm' development dependency to have been installed.
                assert not os.path.exists(os.path.join(project_directory, "node_modules", "npm"))
                # Install the development dependencies (a superset of the production dependencies).
                run_cli(main, "--cache-directory=%s" % cache_directory, project_directory)
                # We *do* expect the `path' production dependency to have been installed.
                assert os.path.exists(os.path.join(project_directory, "node_modules", "path"))
                # We *also* expect the `npm' development dependency to have been installed.
                assert os.path.exists(os.path.join(project_directory, "node_modules", "npm"))

    def test_caching(self):
        """Verify that caching of ``node_modules`` brings a speed improvement."""
        with TemporaryDirectory() as cache_directory:
            with TemporaryDirectory() as project_directory:
                original_dependencies = dict(npm="3.10.6")
                write_package_metadata(project_directory, original_dependencies)
                accelerator = NpmAccel(context=create_context(), cache_directory=cache_directory)
                # Sanity check that we're about to prime the cache.
                parsed_dependencies = accelerator.extract_dependencies(os.path.join(project_directory, "package.json"))
                assert parsed_dependencies == original_dependencies
                # XXX In Python 2.x the following two expressions can both be
                #     True (due to implicit Unicode string coercion):
                #
                #     1. parsed_dependencies == original_dependencies
                #     2. get_cache_file(parsed_dependencies) != get_cache_file(original_dependencies)
                #
                # That is to say: While you can successfully compare two
                # dictionaries for equality, the repr() of the two dictionaries
                # will differ, due to string keys versus Unicode keys and the
                # u'' syntax in the repr() output.
                file_in_cache = accelerator.get_cache_file(parsed_dependencies)
                logger.debug(
                    "Name of file to be added to cache: %s (based on original dependencies: %s)",
                    file_in_cache,
                    original_dependencies,
                )
                assert not os.path.isfile(file_in_cache)
                # The first run is expected to prime the cache.
                first_run = Timer(resumable=True)
                with first_run:
                    parsed_dependencies = accelerator.install(project_directory)
                    assert parsed_dependencies == original_dependencies
                self.check_program(project_directory, "npm", "help")
                # Sanity check that the cache was primed.
                assert os.path.isfile(file_in_cache)
                # The second run is expected to reuse the cache.
                second_run = Timer(resumable=True)
                with second_run:
                    parsed_dependencies = accelerator.install(project_directory)
                    assert parsed_dependencies == original_dependencies
                self.check_program(project_directory, "npm", "help")
                # Make sure the 2nd run was significantly faster than the 1st run.
                assert second_run.elapsed_time < (first_run.elapsed_time / 2)

    def test_cache_cleaning(self):
        """Make sure the automatic cache cleaning logic works as expected."""
        with TemporaryDirectory() as cache_directory:
            context = create_context()
            accelerator = NpmAccel(context=context, cache_directory=cache_directory)
            just_above_limit = accelerator.cache_limit + 1
            for i in range(just_above_limit):
                # Create a fake (empty) tar archive.
                fingerprint = random_string(length=40, characters=string.hexdigits)
                filename = os.path.join(cache_directory, "%s.tar" % fingerprint)
                context.write_file(filename, "")
                # Create the cache metadata.
                accelerator.write_metadata(filename)
            # Sanity check the cache entries.
            assert len(list(accelerator.find_archives())) == just_above_limit
            # Run the cleanup.
            accelerator.clean_cache()
            # Make sure the number of cache entries decreased.
            assert len(list(accelerator.find_archives())) == accelerator.cache_limit

    def test_benchmark(self):
        """Make sure the benchmark finishes successfully."""
        with TemporaryDirectory() as cache_directory:
            with TemporaryDirectory() as project_directory:
                write_package_metadata(project_directory, dict(npm="3.10.6"))
                run_cli(main, "--cache-directory=%s" % cache_directory, "--benchmark", project_directory)

    def check_program(self, directory, program_name, *arguments):
        """Verify that a Node.js program was correctly installed."""
        # Verify that the program's executable was installed.
        program_path = os.path.join(directory, "node_modules", ".bin", program_name)
        assert os.path.isfile(program_path)
        assert os.access(program_path, os.X_OK)
        # Verify that the program's executable actually runs.
        execute(program_path, *arguments)


def write_package_metadata(directory, dependencies={}, devDependencies={}):
    """Generate a ``package.json`` file for testing."""
    metadata = dict(name=random_string(10), version="0.0.1", dependencies=dependencies, devDependencies=devDependencies)
    with open(os.path.join(directory, "package.json"), "w") as handle:
        json.dump(metadata, handle)
