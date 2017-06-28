npm-accel: Accelerator for npm, the Node.js package manager
===========================================================

.. image:: https://travis-ci.org/xolox/python-npm-accel.svg?branch=master
   :target: https://travis-ci.org/xolox/python-npm-accel

.. image:: https://coveralls.io/repos/xolox/python-npm-accel/badge.svg?branch=master
   :target: https://coveralls.io/r/xolox/python-npm-accel?branch=master

The npm-accel program is a wrapper for npm_ (the Node.js_ package manager) that
was created to optimize **one specific use case**: Creating a node_modules_
directory from a package.json_ file as quickly as possible.

It works on the assumption that you build node_modules directories more
frequently then you change the contents of package.json files, because it
computes a fingerprint of the dependencies and uses that fingerprint as a cache
key, to cache the complete node_modules directory in a tar archive.

The program is intended to be used in environments that always or frequently
start with an empty node_modules directory and need to populate the complete
directory from scratch (e.g. continuous integration builds and deployments).
I'm specifically not claiming that you will see any speed improvements if
you're updating existing node_modules directories.

The npm-accel program is currently tested on Python 2.7, 3.4, 3.5, 3.6 and PyPy
(yes, it's written in Python, deal with it :-P). It's intended to work on UNIX
systems like Linux and Mac OS X and specifically won't work on Windows (see
`supported operating systems`_ for details).

.. contents::
   :local:

Installation
------------

The `npm-accel` package is available on PyPI_ which means installation
should be as simple as:

.. code-block:: sh

   $ pip install npm-accel

There's actually a multitude of ways to install Python packages (e.g. the `per
user site-packages directory`_, `virtual environments`_ or just installing
system wide) and I have no intention of getting into that discussion here, so
if this intimidates you then read up on your options before returning to these
instructions ;-).

Alternatively if you are running Arch Linux, npm-accel is `available in AUR`_.

Usage
-----

There are two ways to use the `npm-accel` package: As the command line program
``npm-accel`` and as a Python API. For details about the Python API please
refer to the API documentation available on `Read the Docs`_. The command line
interface is described below.

.. contents::
   :local:

.. A DRY solution to avoid duplication of the `npm-accel --help' text:
..
.. [[[cog
.. from humanfriendly.usage import inject_usage
.. inject_usage('npm_accel.cli')
.. ]]]

**Usage:** `npm-accel [OPTIONS] [DIRECTORY]`

The npm-accel program is a wrapper for npm (the Node.js package manager) that
optimizes one specific use case: Building a "node_modules" directory from a
"package.json" file as quickly as possible.

It works on the assumption that you build "node_modules" directories more
frequently then you change the contents of "package.json" files, because it
computes a fingerprint of the dependencies and uses that fingerprint as a
cache key, to cache the complete "node_modules" directory in a tar archive.

**Supported options:**

.. csv-table::
   :header: Option, Description
   :widths: 30, 70


   "``-p``, ``--production``","Don't install modules listed in ""devDependencies""."
   "``-i``, ``--installer=NAME``","Set the installer to use. Supported values for ``NAME`` are ""npm"", ""yarn"",
   ""npm-cache"" and ""npm-fast-install"". When yarn is available it will be
   selected as the default installer, otherwise the default is npm."
   "``-u``, ``--update``","Don't read from the cache but do write to the cache. If you suspect a cache
   entry to be corrupt you can use ``--update`` to 'refresh' the cache entry."
   "``-n``, ``--no-cache``","Disallow writing to the cache managed by npm-accel (reading is still
   allowed though). This option does not disable internal caching
   performed by npm, yarn, npm-cache and npm-fast-install."
   "``-c``, ``--cache-directory=DIR``",Set the pathname of the directory where the npm-accel cache is stored.
   "``-l``, ``--cache-limit=COUNT``","Set the maximum number of tar archives to preserve. When the cache
   directory contains more than ``COUNT`` archives the least recently used
   archives are removed. Defaults to 20."
   "``-b``, ``--benchmark``","Benchmark and compare the following installation methods:
   
   1. npm install
   2. yarn
   3. npm-accel
   4. npm-cache
   5. npm-fast-install
   
   The first method performs no caching (except for the HTTP caching that's
   native to npm) while the other four methods each manage their own cache
   (that is to say, the caching logic of npm-accel will only be used in the
   second method).
   
   Warning: Benchmarking wipes the caches managed by npm, yarn, npm-accel,
   npm-cache and npm-fast-install in order to provide a fair comparison
   (you can override this in the Python API but not on the command line)."
   "``-r``, ``--remote-host=SSH_ALIAS``","Operate on a remote system instead of the local system. The
   ``SSH_ALIAS`` argument gives the SSH alias of the remote host."
   "``-v``, ``--verbose``",Increase logging verbosity (can be repeated).
   "``-q``, ``--quiet``",Decrease logging verbosity (can be repeated).
   ``--version``,Report the version of npm-accel.
   "``-h``, ``--help``",Show this message and exit.

.. [[[end]]]

Status
------

The npm-accel project was developed and published in September '16 because I
got fed up waiting for ``npm install`` to finish, specifically in the context
of continuous integration builds and deployments (where you frequently start
with an empty ``node_modules`` directory). It was developed in about a week
without much prior knowledge about Node.js_ or npm_, which explains why it's
written in Python :-P.

The project was initially published with 95% test coverage and I was careful
not to repeat the bugs I encountered in npm-cache_ and npm-fast-install_ while
evaluating those tools :-).

At the time of writing (June '17) npm-accel has been in active use at my
employer for about nine months. During that time our builds have become bigger
and slower and so I wanted npm-accel to be even faster :-). To this end I've
removed the use of ``npm prune`` and integrated support for yarn_ (it will be
used automatically in preference over npm_ when it is installed).

To summarize: Give it a try, see if it actually speeds up your ``npm install``
use case and then decide whether you want to use it or not. The current release
of npm-accel is labeled as a `beta release`_ because of the recent refactoring
that removed ``npm prune``, integrated yarn and cleaned up the code base.

Performance
-----------

The following table lists the output of ``npm-accel --benchmark`` against a
private code base with 58 dependencies listed in the package.json file
(resulting in a 357 MB node_modules directory):

=========================  =========  ===========================  ==========
Approach                   Iteration  Elapsed time                 Percentage
=========================  =========  ===========================  ==========
npm install                   1 of 2                42.47 seconds     100.00%
npm install                   2 of 2                27.92 seconds      65.73%
yarn                          1 of 2                33.32 seconds      78.45%
yarn                          2 of 2                17.66 seconds      41.59%
npm-accel                     1 of 2                28.22 seconds      66.45%
npm-accel                     2 of 2                  1.79 second       4.22%
npm-cache install npm         1 of 2    1 minute and 2.88 seconds     148.06%
npm-cache install npm         2 of 2                15.87 seconds      37.35%
npm-fast-install              1 of 2  9 minutes and 35.35 seconds    1354.62%
npm-fast-install (failed)     2 of 2                           \-          \-
=========================  =========  ===========================  ==========

Some notes about this benchmark:

- Each of the five installation methods (npm, yarn, npm-accel, npm-cache and
  npm-fast-install) is run twice. The first run starts with empty cache
  directories and is intended to "prime the cache". The second run is intended
  to actually use the cache and should be able to do so quite effectively,
  given that the package.json file does not change between the two runs.

- During the benchmark, the caching performed by npm-accel is only used in the
  sixth row of the table above. This is because the original point of the
  benchmark (for me) was to find out whether it was even worth it to develop
  and publish npm-accel. That is to say, if it wouldn't have given a speed
  improvement it wasn't worth my time, nor yours :-P.

.. _supported operating systems:

Supported operating systems
---------------------------

The npm-accel program was developed to work on UNIX systems like Linux and Mac
OS X. It requires several external commands to be installed (e.g. ``mkdir``,
``mv``, ``rm``, ``tar`` and ``which``).

I've tried to keep all of the external command invocations compatible with the
Linux and BSD variants of commands like tar_, that is to say npm-accel uses
only short options and skips the more esoteric features even if they would be
useful. If you find that I failed in this respect, please feel free to report
this as a bug.

For posterity: It was a conscious decision (for several reasons) to use the
tar_ program instead of manipulating tar archives via Python's `tarfile
module`_.

Future improvements
-------------------

**Dealing with optionalDependencies**
 I've never seen ``optionalDependencies`` in the wild but encountered them
 while browsing through the package.json_ documentation. Maybe these should be
 part of the computed cache keys aswell?

Contact
-------

The latest version of `npm-accel` is available on PyPI_ and GitHub_. The
documentation is hosted on `Read the Docs`_. For bug reports please create an
issue on GitHub_. If you have questions, suggestions, etc. feel free to send me
an e-mail at `peter@peterodding.com`_.

License
-------

This software is licensed under the `MIT license`_.

© 2017 Peter Odding.


.. External references:
.. _available in AUR: https://aur.archlinux.org/packages/npm-accel/
.. _beta release: https://en.wikipedia.org/wiki/Software_release_life_cycle#Beta
.. _GitHub: https://github.com/xolox/python-npm-accel
.. _MIT license: http://en.wikipedia.org/wiki/MIT_License
.. _Node.js: https://nodejs.org/en/
.. _node_modules: https://docs.npmjs.com/getting-started/installing-npm-packages-locally#installing
.. _npm-cache: https://www.npmjs.com/package/npm-cache
.. _npm-fast-install: https://www.npmjs.com/package/npm-fast-install
.. _npm: https://www.npmjs.com/
.. _package.json: https://docs.npmjs.com/files/package.json
.. _per user site-packages directory: https://www.python.org/dev/peps/pep-0370/
.. _peter@peterodding.com: peter@peterodding.com
.. _PyPI: https://pypi.python.org/pypi/npm-accel
.. _Read the Docs: https://npm-accel.readthedocs.io/en/latest/
.. _tar: https://en.wikipedia.org/wiki/Tar_(computing)
.. _tarfile module: https://docs.python.org/2/library/tarfile.html
.. _virtual environments: http://docs.python-guide.org/en/latest/dev/virtualenvs/
.. _yarn: https://www.npmjs.com/package/yarn
