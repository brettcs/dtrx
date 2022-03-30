[![GitHub](https://img.shields.io/badge/GitHub-dtrx--py/dtrx-8da0cb?style=for-the-badge&logo=github)](https://github.com/dtrx-py/dtrx)
[![PyPI
version](https://img.shields.io/pypi/v/dtrx.svg?style=for-the-badge&logo=PyPi&logoColor=white)](https://pypi.org/project/dtrx/)
[![PyPI
pyversions](https://img.shields.io/pypi/pyversions/dtrx.svg?style=for-the-badge&logo=python&logoColor=white&color=ff69b4)](https://pypi.python.org/pypi/dtrx/)
[![GitHub Workflow Status](https://img.shields.io/github/workflow/status/dtrx-py/dtrx/main-ci/master?logo=github-actions&logoColor=white&style=for-the-badge)](https://github.com/dtrx-py/dtrx/actions)

<!-- toc -->

- [Changes in this repo](#changes-in-this-repo)
- [Development](#development)
  - [Contributions](#contributions)
  - [Issues](#issues)
  - [Releases](#releases)
  - [Tests](#tests)
  - [Linting](#linting)

<!-- tocstop -->

# dtrx

"**Do The Right eXtraction**" - don't remember what set of `tar` flags or where
to pipe the output to extract it? no worries!

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

## Development

### Contributions

Contributions are gladly welcomed! Feel free to open a Pull Request with any
changes.

### Issues

When posting an issue, it can be very handy to provide any example files (for
example, the archive that failed to extract) or reproduction steps so we can
address the problem quickly.

### Releases

Releases are tagged in this repo and published to pypi.org. The release process
for maintainers is the below steps:

1. update the version specifier:

   ```bash
   # update the VERSION value in dtrx/dtrx.py, then:
   ❯ git add dtrx/dtrx.py
   ❯ git commit  # fill in the commit message
   ```

2. create an annotated tag for the release. usually good to put a list of new
   commits since the previous tag, for example by listing them with:

   ```bash
   ❯ git log $(git describe --tags --abbrev=0)..HEAD --oneline
   # create the annotated tag
   ❯ git tag -a <version number>
   ```

   be sure to push the tag, `git push --tags`.

3. use the `make publish-release` command to build and publish to GitHub and
   PyPi

See the [`Makefile`](Makefile) for details on what that rule does.

### Tests

There is a suite of tests that can be run either on the local python
environment, or across all the supported python environments via docker:

```bash
# run the suite from the current python environment
pip install pyyaml  # test dependency
python tests/compare.py

# run the tests in docker across all supported python versions (takes a while)
./test.sh

# run the tests in docker on one python version
RUN_JOB=quick-test ./test.sh
```

### Linting

Linting is provided by [pre-commit](pre-commit.com). To use it, first install
the pre-commit hook:

```bash
pip install pre-commit
pre-commit install
```

pre-commit will run anytime `git commit` runs (disable with `--no-verify`). You
can manually run it with `pre-commit run`.

It's also run in CI.
