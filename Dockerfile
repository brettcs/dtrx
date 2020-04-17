FROM ubuntu:focal-20200319

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    arj \
    cpio \
    gzip \
    lhasa \
    lrzip \
    lzip \
    p7zip-full \
    python-pip-whl \
    python2.7 \
    python3-pip \
    python3.8 \
    unrar \
    wget \
    zip

RUN pip3 install tox==3.14.6

# create a user inside the container. if you specify your UID when building the
# image, you can mount directories into the container with read-write access:
# docker build -t "dtrx" -f Dockerfile --build-arg UID=$(id -u) .
ARG UID=1010
ARG UNAME=builder
RUN useradd --uid ${UID} --create-home --user-group ${UNAME} && \
    echo "${UNAME}:${UNAME}" | chpasswd && adduser ${UNAME} sudo

USER ${UNAME}
