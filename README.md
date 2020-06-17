[![GitHub](https://img.shields.io/badge/GitHub-dtrx--py/dtrx-8da0cb?style=for-the-badge&logo=github)](https://github.com/dtrx-py/dtrx)
[![PyPI
version](https://img.shields.io/pypi/v/dtrx.svg?style=for-the-badge&logo=python&logoColor=white)](https://pypi.org/project/dtrx/)
[![PyPI
pyversions](https://img.shields.io/pypi/pyversions/dtrx.svg?style=for-the-badge&color=ff69b4)](https://pypi.python.org/pypi/dtrx/)
![GitHub Workflow Status
(branch)](https://img.shields.io/github/workflow/status/dtrx-py/dtrx/main-ci/master?logo=github-actions&logoColor=white&style=for-the-badge)

- [dtrx](#dtrx)
  - [Changes in this repo](#changes-in-this-repo)
  - [TODO](#todo)
    - [Python 3.9](#python-39)

# dtrx

"**Do The Right eXtraction**" - don't remember what set of `tar` flags or where to
pipe the output to extract it? no worries!

TL;DR

```bash
pip install dtrx

dtrx yolo.tar.gz
```

This is a copy-paste of the original dtrx repo, and **all credit for this
software** should be attributed to the original author, Brett Smith @brettcs:

https://github.com/brettcs/dtrx

See the original [`README`](README) for more details on what this does!

## Changes in this repo

This repo contains some patches on top of the original source to enable using
`dtrx` with python3. The original motivation was to enable `dtrx` on Ubuntu
20.04+, where the `dtrx` apt package was removed from the default ppas (likely
due to being python2 only).

I attempted to get the tests all working via `tox` , for which I used a
Dockerfile to try to get some kind of environment consistency. You can run the
tests by running (requires Docker installed):

```bash
./test.sh
```

## TODO

### Python 3.9

Now that python 3.9 has entered the RC stage, we should include a target
classifier and support 3.9 in the test suite!
