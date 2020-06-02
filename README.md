[![PyPI
version](https://img.shields.io/pypi/v/dtrx.svg?style=for-the-badge)](https://pypi.org/project/dtrx/)
[![PyPI
pyversions](https://img.shields.io/pypi/pyversions/dtrx.svg?style=for-the-badge)](https://pypi.python.org/pypi/dtrx/)

- [dtrx-noah](#dtrx-noah)
  - [What is this repo then](#what-is-this-repo-then)
  - [TODO](#todo)
    - [Repo relocating](#repo-relocating)
    - [Python 3.9](#python-39)

# dtrx-noah

"**Do The Right eXtraction**" - don't remember what set of `tar` flags or where to
pipe the output to extract it? no worries!

TL;DR

```bash
pip install dtrx

dtrx yolo.tar.gz
```

This is a copy-paste of the original dtrx repo, and all credit for this software
should be attributed to the original authoer, Brett Smith @brettcs:

https://github.com/brettcs/dtrx

See the original [`README`](README) for more details on what this does!

## What is this repo then

This repo is just enough patch to deploy a `dtrx-noah` to pypi so I can keep
using this tool on Ubuntu 20.04 (it's not longer available on the default apt
sources).

I attempted to get the tests all working via `tox` , for which I used a
Dockerfile to try to get some kind of environment consistency. You can run the
tests by running (requires Docker installed):

```bash
./test.sh
```

## TODO

### Repo relocating

Thanks to @ChrisJefferson , this package is now deployed to PyPi under the
`dtrx` name: https://pypi.org/project/dtrx/

This repo will be moved to a new location very soon, and package links updated
etc.

### Python 3.9

Now that python 3.9 has entered the RC stage, we should include a target
classifier and support 3.9 in the test suite!
