# dtrx-noah

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

## What is this repo then

This repo is just enough patch to deploy a `dtrx-noah` to pypi so I can keep
using this tool on Ubuntu 20.04.

I attempted to get the tests all working via `tox` , for which I used a
Dockerfile to try to get some kind of environment consistency. You could run the
tests like:

```shell
# build the image
docker build -t "dtrx" -f Dockerfile --build-arg UID=$(id -u) .

# run tox in the container. note tox is being run serially (no -p auto), in case
# the working dir gets abused by the test script
docker run -v"$(pwd):/mnt/workspace" -t dtrx bash -c "cd /mnt/workspace && tox -s true"
```
