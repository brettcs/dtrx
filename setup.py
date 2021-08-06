#!/usr/bin/env python

import io
import os
import sys

from setuptools import setup

# Get long description from readme
ROOT_PATH = os.path.abspath(os.path.join(os.environ.get("TOX_INI_DIR", ".")))
README_PATH = os.path.join(ROOT_PATH, "README.md")
with io.open(README_PATH, "rt", encoding="utf8") as readmefile:
    README = readmefile.read()

if sys.version_info <= (3, 2):
    install_requires = ["subprocess32"]
else:
    install_requires = []

# get version number from dtrx
# suppress the deprecation warning for imp, it's for py 2.7/3.x compat
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
import imp

dtrx = imp.load_source("dtrx", os.path.join(ROOT_PATH, "scripts/dtrx"))

setup(
    name="dtrx",
    version=dtrx.VERSION,
    description="Script to intelligently extract multiple archive types",
    author="Brett Smith",
    author_email="brettcsmith@brettcsmith.org",
    url="http://www.brettcsmith.org/2007/dtrx/",
    project_urls={
        "Code": "https://github.com/dtrx-py/dtrx",
    },
    download_url="https://github.com/dtrx-py/dtrx",
    scripts=["scripts/dtrx"],
    license="GNU General Public License, version 3 or later",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Natural Language :: English",
        "Operating System :: POSIX",
        "Programming Language :: Python",
        "Topic :: Utilities",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    # long_description="""dtrx extracts archives in a number of different
    #   formats; it currently supports tar, zip (including self-extracting
    #   .exe files), cpio, rpm, deb, gem, 7z, cab, rar, lzh, arj, and
    #   InstallShield files.  It can also decompress files compressed with gzip,
    #   bzip2, lzma, xz, lrzip, lzip, or compress.
    #   In addition to providing one command to handle many different archive
    #   types, dtrx also aids the user by extracting contents consistently.
    #   By default, everything will be written to a dedicated directory
    #   that's named after the archive.  dtrx will also change the
    #   permissions to ensure that the owner can read and write all those
    #   files.""",
    long_description=README,
    long_description_content_type="text/markdown",
    # using markdown as pypi description:
    # https://dustingram.com/articles/2018/03/16/markdown-descriptions-on-pypi
    setup_requires=["setuptools>=38.6.0", "wheel>=0.31.0", "twine>=1.11.0"],
    install_requires=install_requires,
)
