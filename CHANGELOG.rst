Changelog
=========

The purpose of this document is to list all of the notable changes to this
project. The format was inspired by `Keep a Changelog`_. This project adheres
to `semantic versioning`_.

.. contents::
   :local:

.. _Keep a Changelog: http://keepachangelog.com/
.. _semantic versioning: http://semver.org/

`Release 2.0`_ (2020-03-03)
---------------------------

**Significant changes:**

- Update Python compatibility: Added 3.7 and 3.8, removed 3.4.

- Add support for the ``$NPM_ACCEL_CACHE_LIMIT`` environment variable.

- Add support for pnpm_ (it has piqued my interest) and remove support for
  npm-fast-install_ (it was never worth my time).

- Change cache key computation to include version of installer that's actually used
  instead of npm version (bug fix).

- Change development status in ``setup.py`` script from beta to stable.

**Miscellaneous changes:**

- Include documentation in source distributions.
- Switch from node_4.x to node_10.x on Travis CI.
- Add this changelog, restructure the documentation.
- Include ``license=MIT`` key in ``setup.py`` script.
- Change ``Makefile`` to use Python 3 for local development.
- Upgrade to :pypi:`humanfriendly` 8.0 (fix deprecated imports).
- Integrate :pypi:`pytest-rerunfailures` because MacOS workers on Travis CI are slow 😝.

.. _Release 2.0: https://github.com/xolox/python-npm-accel/compare/1.0...2.0
.. _npm-fast-install: https://www.npmjs.com/package/npm-fast-install
.. _pnpm: https://www.npmjs.com/package/pnpm

`Release 1.0`_ (2017-06-29)
---------------------------

Integrate ``yarn``, stop using ``npm prune`` (**backwards incompatible!**).

I've decided to bump the major version number because numerous minor
backwards incompatibilities were introduced in the Python API during my
refactoring spree of the past few days. I've also changed the previous
'alpha' label into a 'beta' label, which sounds weird together with the
1.0, but there you go, semantic versioning 😉.

Detailed overview of changes:

- Integrated support for ``yarn``:

  - When available ``yarn`` is used in preference to ``npm``.
  - The benchmark now allows npm-accel to use ``yarn``.

- Update project status (alpha ➡️ beta) and performance (further improved) in
  readme.
- Include full pathname of Node.js interpreter in log output.
- Exclude ``npm-cache`` & ``npm-fast-install`` from npm-accel cache usage.
- Make ``benchmark()`` handle command failure gracefully.
- Bug fix for matching of short options ``-p`` and ``-i``.
- Update supported Python versions (added 3.6).
- Remove support for local installers and pruning because it's broken anyway.
  When I originally created npm-accel I was under the impression that it should
  be possible to start with an empty ``node_modules`` directory, install a
  non-default installer in that directory and use that installer to install the
  packages that you're actually interested in. In reality I've seen both
  ``yarn`` and ``npm-fast-install`` choke completely when used in this setting.
  After installing them globally those problems immediately disappeared.
- Add ``npm-accel --update`` option to refresh existing cache entries.
- Add ``npm-accel --version`` option.

.. _Release 1.0: https://github.com/xolox/python-npm-accel/compare/0.4...1.0

`Release 0.4`_ (2016-10-12)
---------------------------

- Automatic garbage collection of cache entries.
- Configured Travis CI to run tests on Mac OS X.

.. _Release 0.4: https://github.com/xolox/python-npm-accel/compare/0.3.1...0.4

`Release 0.3.1`_ (2016-09-17)
-----------------------------

- Clarify supported operating systems in documentation and ``setup.py``.
- Mention the Arch Linux (AUR) package in the readme. Refer to pull request
  `#1`_ for details.

.. _Release 0.3.1: https://github.com/xolox/python-npm-accel/compare/0.3...0.3.1

`Release 0.3`_ (2016-09-17)
---------------------------

Merged pull request `#1`_: Fix calling ``node``/``nodejs`` binary in ``nodejs_version``.

- The primary nodejs executable being called ``nodejs`` is a Debian-ism, and is
  not compatible with upstream nodejs and non-Debian distros, because upstream
  just calls the binary ``node``.

- This makes the ``node_version`` method fail on non-Debian systems, where
  ``nodejs`` is actually called ``node`` instead.

- Instead of just executing the ``nodejs`` command, we now first search for it
  in the ``$PATH``.

- When no node executable is found, a ``NodeBinaryNotFoundError`` is now raised.

- If one of the node executables is found, we return the result of ``node
  --version`` or ``nodejs --version`` as before.

.. _Release 0.3: https://github.com/xolox/python-npm-accel/compare/0.2...0.3
.. _#1: https://github.com/xolox/python-npm-accel/pull/1

`Release 0.2`_ (2016-09-16)
---------------------------

- Bug fix: Avoid race conditions.
- Added Travis CI configuration.
- Improved the documentation.

.. _Release 0.2: https://github.com/xolox/python-npm-accel/compare/0.1...0.2

`Release 0.1`_ (2016-09-15)
---------------------------

This was the initial release.

.. _Release 0.1: https://github.com/xolox/python-npm-accel/tree/0.1
