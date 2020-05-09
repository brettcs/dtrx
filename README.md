[![PyPI
version](https://img.shields.io/pypi/v/dtrx-noahp.svg?style=for-the-badge)](https://pypi.org/project/dtrx-noahp/)
[![PyPI
pyversions](https://img.shields.io/pypi/pyversions/dtrx-noahp.svg?style=for-the-badge)](https://pypi.python.org/pypi/dtrx-noahp/)

# dtrx-noah

"**Do The Right eXtraction**" - don't remember what set of `tar` flags or where to
pipe the output to extract it? no worries!

TL;DR

```bash
pip install dtrx-noahp

dtrx yolo.tar.gz
```

This is a copy-paste of the original dtrx repo:

https://github.com/moonpyk/dtrx

The dtrx utility is not right now (2020-04-06) available on the Ubuntu 20.04
PPA, and the package published to pypi.org is no longer installable from pip,
due to pypi.python.org now redirecting to pypi.org, and the pypi dtrx package
404's due to empty list of packages:

> https://pypi.org/simple/dtrx/

Main dtrx pypi page is here:

> https://pypi.org/project/dtrx/

📦🐍🌀

I've submitted these changes to https://github.com/brettcs/dtrx/pull/1 .

## What is this repo then

This repo is just enough patch to deploy a `dtrx-noah` to pypi so I can keep
using this tool on Ubuntu 20.04.

I attempted to get the tests all working via `tox` , for which I used a
Dockerfile to try to get some kind of environment consistency. You can run the
tests by running:

```bash
./test.sh
```
