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

# create a user inside the container. if you specify your UID when building the
# image, you can mount directories into the container with read-write access:
# docker build -t "dtrx" -f Dockerfile --build-arg UID=$(id -u) .
ARG UID=1010
ARG UNAME=builder
RUN useradd --uid ${UID} --create-home --user-group ${UNAME} && \
    echo "${UNAME}:${UNAME}" | chpasswd && adduser ${UNAME} sudo

USER ${UNAME}

# Install Conda
# Copied from continuumio/miniconda3
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV PATH /home/${UNAME}/miniconda3/bin:$PATH
ARG MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-py37_4.8.2-Linux-x86_64.sh
RUN wget --quiet ${MINICONDA_URL} -O ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b

# Install these in the base conda env
RUN pip install \
    tox-conda==0.2.1 \
    tox==3.15.0
