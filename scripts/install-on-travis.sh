#!/bin/bash -e

# On Mac OS X workers we are responsible for creating the Python virtual
# environment, because we set `language: generic' in the Travis CI build
# configuration file (to bypass the lack of Python runtime support).
if [ "$TRAVIS_OS_NAME" = osx ]; then
  VIRTUAL_ENV="$HOME/virtualenv/python2.7"
  if [ ! -x "$VIRTUAL_ENV/bin/python" ]; then
    pip install virtualenv
    virtualenv "$VIRTUAL_ENV"
  fi
  source "$VIRTUAL_ENV/bin/activate"
fi

# Install the required Python packages.
pip install --requirement=requirements-travis.txt

# On Linux workers we replace the default Node.js and npm install.
if [ "$TRAVIS_OS_NAME" = linux ]; then
  pip install debuntu-tools
  rm -r /home/travis/.nvm
  debuntu-nodejs-installer --install --version=node_10.x
fi

# Upgrade and/or install the tools that we'll be using and benchmarking.
sudo npm install -g npm
sudo npm install -g yarn
sudo npm install -g npm-cache
sudo npm install -g npm-fast-install

# Try to work around the following rather obscure fatal error in
# yarn due to Travis CI modifications that I'm not familiar with:
#
#  An unexpected error occurred:
#  EACCES: permission denied, mkdir '/home/travis/.config/yarn/global'
#
# Breakage encountered here:
#  - https://travis-ci.org/xolox/python-npm-accel/builds/247761572 (Linux)
#  - https://travis-ci.org/xolox/python-npm-accel/jobs/248055260 (Mac OS X)
sudo rm -fr ~/.config

# Try to work around the following Travis CI build failure:
# https://travis-ci.org/xolox/python-npm-accel/jobs/549229079
sudo rm -fr ~/.npm

# Install the project itself, making sure that potential character encoding
# and/or decoding errors in the setup script are caught as soon as possible.
LC_ALL=C pip install .
