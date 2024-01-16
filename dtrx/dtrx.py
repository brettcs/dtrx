#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# dtrx -- Intelligently extract various archive types.
# Copyright © 2006-2011 Brett Smith <brettcsmith@brettcsmith.org>
# Copyright © 2008 Peter Kelemen <Peter.Kelemen@gmail.com>
# Copyright © 2011 Ville Skyttä <ville.skytta@iki.fi>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.

# Python 2.3 string methods: 'rfind', 'rindex', 'rjust', 'rstrip'

from __future__ import absolute_import, print_function

import errno
import fcntl
import itertools
import logging
import mimetypes
import optparse
import os
import re
import shutil
import signal
import stat
import string
import struct
import sys
import tempfile
import termios
import textwrap
import traceback
from functools import cmp_to_key, total_ordering

# Python 3 compatibility hacks commence
try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse
try:
    import subprocess32 as subprocess
except ImportError:
    import subprocess

if sys.version_info[0] >= 3:
    get_input = input

    def cmp(a, b):
        return (a > b) - (a < b)

else:
    get_input = raw_input  # noqa: F821

try:
    set
except NameError:
    from sets import Set as set

VERSION = "8.5.3"
VERSION_BANNER = """dtrx version %s
Copyright © 2006-2011 Brett Smith <brettcsmith@brettcsmith.org>
Copyright © 2008 Peter Kelemen <Peter.Kelemen@gmail.com>
Copyright © 2011 Ville Skyttä <ville.skytta@iki.fi>

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation; either version 3 of the License, or (at your
option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
Public License for more details.""" % (VERSION,)

# Python3.6 optparse has a hard time parsing this, so ascii transform it
if sys.version_info[:2] == (3, 6):
    VERSION_BANNER = VERSION_BANNER.encode("ascii", errors="ignore").decode("ascii")


MATCHING_DIRECTORY = 1
ONE_ENTRY_KNOWN = 2
BOMB = 3
EMPTY = 4
ONE_ENTRY_FILE = "file"
ONE_ENTRY_DIRECTORY = "directory"

ONE_ENTRY_UNKNOWN = [ONE_ENTRY_FILE, ONE_ENTRY_DIRECTORY]

EXTRACT_HERE = 1
EXTRACT_WRAP = 2
EXTRACT_RENAME = 3

RECURSE_ALWAYS = 1
RECURSE_ONCE = 2
RECURSE_NOT_NOW = 3
RECURSE_NEVER = 4
RECURSE_LIST = 5

mimetypes.encodings_map.setdefault(".bz2", "bzip2")
mimetypes.encodings_map.setdefault(".lzma", "lzma")
mimetypes.encodings_map.setdefault(".xz", "xz")
mimetypes.encodings_map.setdefault(".lz", "lzip")
mimetypes.encodings_map.setdefault(".lrz", "lrzip")
mimetypes.encodings_map.setdefault(".zst", "zstd")
mimetypes.encodings_map.setdefault(".zstd", "zstd")
mimetypes.types_map.setdefault(".gem", "application/x-ruby-gem")

logger = logging.getLogger("dtrx-log")


class FilenameChecker(object):
    free_func = os.open
    free_args = (os.O_CREAT | os.O_EXCL,)
    free_close = os.close

    def __init__(self, original_name):
        self.original_name = original_name

    def is_free(self, filename):
        try:
            result = self.free_func(filename, *self.free_args)
        except OSError as error:
            if error.errno == errno.EEXIST:
                return False
            raise
        if self.free_close:
            self.free_close(result)
        return True

    def create(self):
        fd, filename = tempfile.mkstemp(prefix=self.original_name + ".", dir=".")
        os.close(fd)
        return filename

    def check(self):
        for suffix in [""] + [".%s" % (x,) for x in range(1, 10)]:
            filename = "%s%s" % (self.original_name, suffix)
            if self.is_free(filename):
                return filename
        return self.create()


class DirectoryChecker(FilenameChecker):
    free_func = os.mkdir
    free_args = ()
    free_close = None

    def create(self):
        return tempfile.mkdtemp(prefix=self.original_name + ".", dir=".")


class NonblockingRead(object):
    iostream = None

    def __init__(self, iostream):
        self.iostream = iostream

        fd = iostream.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def python_2_readlines(self):
        # XXX: There seems to be a bug in Python 2 where readline() returns
        # "IOError: [Errno 11] Resource temporarily unavailable" on a
        # non-blocking read from a pipe where the output lacks a newline.
        # It doesn't happen in Python 3, so this hack can be deleted once we
        # no longer care about Python 2.
        out = ""
        try:
            while True:
                # read a single byte at a time until we hit IOError
                out += self.iostream.read(1).decode("ascii", "ignore")
        except IOError:
            pass
        return out.splitlines(True)

    def readlines(self):
        if sys.version_info[0] >= 3:
            out = self.iostream.readlines()
            return [line.decode("ascii", "ignore") for line in out]
        else:
            return self.python_2_readlines()


class ExtractorError(Exception):
    pass


class ExtractorUnusable(Exception):
    pass


EXTRACTION_ERRORS = (ExtractorError, ExtractorUnusable, OSError, IOError)


class BaseExtractor(object):
    decoders = {
        "bzip2": ["bzcat"],
        "gzip": ["zcat"],
        "compress": ["zcat"],
        "lzma": ["lzcat"],
        "xz": ["xzcat"],
        "lzip": ["lzip", "-cd"],
        "zstd": ["zstd", "-d"],
        "br": ["br", "--decompress"],
    }
    name_checker = DirectoryChecker

    def __init__(self, filename, encoding):
        # bit of a hack, if we're doing lzip, need to set the correct quiet
        # option based on what's supported, since this behavior changed
        if encoding in ("lrzip", "lrz"):
            # need to check if this version of lrzip supports the -Q option
            output = subprocess.check_output(
                "lrzip --help", stderr=subprocess.STDOUT, shell=True
            )
            if b"-Q" in output:
                decoder = ["lrzcat", "-Q"]
            else:
                decoder = ["lrzcat", "-q"]
            self.decoders["lrz"] = decoder
            self.decoders["lrzip"] = decoder

        if encoding and (encoding not in self.decoders):
            raise ValueError("unrecognized encoding %s" % (encoding,))
        self.filename = os.path.realpath(filename)
        self.encoding = encoding
        self.ignore_pw = False
        self.password = None
        self.file_count = 0
        self.included_archives = []
        self.target = None
        self.content_type = None
        self.content_name = None
        self.pipes = []
        self.user_stdin = False
        self.stderr = ""
        self.pw_prompted = False
        self.exit_codes = []
        try:
            self.archive = open(filename, "r")
        except (IOError, OSError) as error:
            raise ExtractorError("could not open %s: %s" % (filename, error.strerror))
        if encoding:
            self.pipe(self.decoders[encoding], "decoding")
        self.prepare()

    def pipe(self, command, description="extraction"):
        self.pipes.append((command, description))

    def add_process(self, processes, command, stdin, stdout):
        try:
            logger.debug("running command: {}".format(command))
            processes.append(
                subprocess.Popen(
                    command, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE
                )
            )
        except OSError as error:
            if error.errno == errno.ENOENT:
                raise ExtractorUnusable("could not run %s" % (command[0],))
            raise

    def timeout_check(self, pipe):
        pass

    def wait_for_exit(self, pipe):
        while True:
            try:
                return pipe.wait(timeout=1)
            except subprocess.TimeoutExpired:
                logging.debug("timeout hit...")
                self.timeout_check(pipe)
                # Verify that we're not waiting for a password in non-interactive mode
                if self.pw_prompted and self.ignore_pw:
                    pipe.kill()
                    # Whatever extractor we're using probably left the
                    # terminal hiding output..
                    os.system("stty echo")
                    # Clean up the error output
                    self.stderr = ""
                    raise ExtractorError(
                        "cannot extract encrypted archive '%s' in non-interactive mode"
                        " without a password" % (self.filename)
                    )

    def send_stdout_to_dev_null(self):
        return True

    def run_pipes(self, final_stdout=None):
        has_output_target = (
            True if final_stdout or self.send_stdout_to_dev_null() else False
        )
        if not self.pipes:
            return
        elif final_stdout is None:
            final_stdout = open("/dev/null", "w")
        num_pipes = len(self.pipes)
        last_pipe = num_pipes - 1
        processes = []
        for index, command in enumerate([pipe[0] for pipe in self.pipes]):
            if index == 0:
                stdin = None if self.user_stdin else self.archive
            else:
                stdin = processes[-1].stdout
            if index == last_pipe and has_output_target:
                stdout = final_stdout
            else:
                stdout = subprocess.PIPE
            self.add_process(processes, command, stdin, stdout)
        self.exit_codes = [self.wait_for_exit(pipe) for pipe in processes]
        for pipe in processes:
            # Grab any remaining error messages
            errs = pipe.stderr.readlines()
            self.stderr += b"".join(errs).decode("ascii", "ignore")
        self.archive.close()
        for index in range(last_pipe):
            processes[index].stdout.close()
        self.archive = final_stdout

    def prepare(self):
        pass

    def check_included_archives(self):
        if (self.content_name is None) or (not self.content_name.endswith("/")):
            self.included_root = "./"
        else:
            self.included_root = self.content_name
        start_index = len(self.included_root)
        for path, _dirname, filenames in os.walk(self.included_root):
            self.file_count += len(filenames)
            path = path[start_index:]
            for filename in filenames:
                if ExtractorBuilder.try_by_mimetype(
                    filename
                ) or ExtractorBuilder.try_by_extension(filename):
                    self.included_archives.append(os.path.join(path, filename))

    def check_contents(self):
        if not self.contents:
            self.content_type = EMPTY
        elif len(self.contents) == 1:
            if self.basename() == self.contents[0]:
                self.content_type = MATCHING_DIRECTORY
            elif os.path.isdir(self.contents[0]):
                self.content_type = ONE_ENTRY_DIRECTORY
            else:
                self.content_type = ONE_ENTRY_FILE
            self.content_name = self.contents[0]
            if os.path.isdir(self.contents[0]):
                self.content_name += "/"
        else:
            self.content_type = BOMB
        self.check_included_archives()

    def basename(self):
        pieces = os.path.basename(self.filename).split(".")
        orig_len = len(pieces)
        extension = "." + pieces[-1]
        # This is maybe a little more clever than it ought to be.
        # We're trying to be conservative about what remove, but also DTRT
        # in cases like .tar.gz, and also do something reasonable if we
        # encounter some completely off-the-wall extension.  So that means:
        # 1. First remove any compression extension.
        # 2. Then remove any commonly known extension that remains.
        # 3. If neither of those did anything, remove anything that looks
        #    like it's almost certainly an extension (less than 5 chars).
        if extension in mimetypes.encodings_map:
            pieces.pop()
            extension = "." + pieces[-1]
        if (
            extension in mimetypes.types_map
            or extension in mimetypes.common_types
            or extension in mimetypes.suffix_map
        ):
            pieces.pop()
        if (orig_len == len(pieces)) and (orig_len > 1) and (len(pieces[-1]) < 5):
            pieces.pop()
        return ".".join(pieces)

    def is_fatal_error(self, status):
        return False

    def first_bad_exit_code(self):
        for index, code in enumerate(self.exit_codes):
            if code > 0:
                return index, code
        return None, None

    def check_success(self, got_files):
        error_index, error_code = self.first_bad_exit_code()
        logger.debug(
            "success results: %s %s %s" % (got_files, error_index, self.exit_codes)
        )
        if self.is_fatal_error(error_code) or (
            (not got_files) and (error_code is not None)
        ):
            command = " ".join(self.pipes[error_index][0])
            self.pw_prompt = False  # Don't silently fail with wrong password
            raise ExtractorError(
                "%s error: '%s' returned status code %s"
                % (self.pipes[error_index][1], command, error_code)
            )

    def extract_archive(self):
        self.pipe(self.extract_pipe)
        self.run_pipes()

    def extract(self, ignore_passwd=False, password=None):
        self.ignore_pw = ignore_passwd
        self.password = password
        try:
            self.target = tempfile.mkdtemp(prefix=".dtrx-", dir=".")
        except (OSError, IOError) as error:
            raise ExtractorError("cannot extract here: %s" % (error.strerror,))
        old_path = os.path.realpath(os.curdir)
        os.chdir(self.target)
        try:
            self.archive.seek(0, 0)
            self.extract_archive()
            self.contents = os.listdir(".")
            self.check_contents()
            self.check_success(self.content_type != EMPTY)
        except EXTRACTION_ERRORS:
            self.archive.close()
            os.chdir(old_path)
            shutil.rmtree(self.target, ignore_errors=True)
            raise
        self.archive.close()
        os.chdir(old_path)

    def get_filenames(self, internal=False):
        if not internal:
            self.pipe(self.list_pipe, "listing")
        processes = []
        stdin = self.archive
        for command in [pipe[0] for pipe in self.pipes]:
            self.add_process(processes, command, stdin, subprocess.PIPE)
            stdin = processes[-1].stdout
        get_output_line = processes[-1].stdout.readline
        while True:
            line = get_output_line().decode("ascii", errors="ignore")
            if not line:
                break
            yield line.rstrip("\n")
        self.exit_codes = [pipe.wait() for pipe in processes]
        self.archive.close()
        for process in processes:
            process.stdout.close()
        self.check_success(False)


class CompressionExtractor(BaseExtractor):
    file_type = "compressed file"
    name_checker = FilenameChecker

    def basename(self):
        pieces = os.path.basename(self.filename).split(".")
        extension = "." + pieces[-1]
        if extension in mimetypes.encodings_map:
            pieces.pop()
        return ".".join(pieces)

    def get_filenames(self):
        # This code used to just immediately yield the basename, under the
        # assumption that that would be the filename.  However, if that
        # happens, dtrx -l will report this as a valid result for files with
        # compression extensions, even if those files shouldn't actually be
        # handled this way.  So, we call out to the file command to do a quick
        # check and make sure this actually looks like a compressed file.
        if "compress" not in [
            match[0] for match in ExtractorBuilder.try_by_magic(self.filename)
        ]:
            raise ExtractorError("doesn't look like a compressed file")
        yield self.basename()

    def extract(self, ignore_passwd=False, password=None):
        self.ignore_pw = ignore_passwd
        self.password = password
        self.content_type = ONE_ENTRY_KNOWN
        self.content_name = self.basename()
        self.contents = None
        self.file_count = 1
        self.included_root = "./"
        try:
            output_fd, self.target = tempfile.mkstemp(prefix=".dtrx-", dir=".")
        except (OSError, IOError) as error:
            raise ExtractorError("cannot extract here: %s" % (error.strerror,))
        self.run_pipes(output_fd)
        os.close(output_fd)
        try:
            self.check_success(os.stat(self.target)[stat.ST_SIZE] > 0)
        except EXTRACTION_ERRORS:
            os.unlink(self.target)
            raise


class TarExtractor(BaseExtractor):
    file_type = "tar file"
    extract_pipe = ["tar", "-x"]
    list_pipe = ["tar", "-t"]


class CpioExtractor(BaseExtractor):
    file_type = "cpio file"
    extract_pipe = [
        "cpio",
        "-i",
        "--make-directories",
        "--quiet",
        "--no-absolute-filenames",
    ]
    list_pipe = ["cpio", "-t", "--quiet"]


class RPMExtractor(CpioExtractor):
    file_type = "RPM"

    def prepare(self):
        self.pipe(["rpm2cpio", "-"], "rpm2cpio")

    def basename(self):
        pieces = os.path.basename(self.filename).split(".")
        if len(pieces) == 1:
            return pieces[0]
        elif pieces[-1] != "rpm":
            return BaseExtractor.basename(self)
        pieces.pop()
        if len(pieces) == 1:
            return pieces[0]
        elif len(pieces[-1]) < 8:
            pieces.pop()
        return ".".join(pieces)

    def check_contents(self):
        self.check_included_archives()
        self.content_type = BOMB


class DebExtractor(TarExtractor):
    file_type = "Debian package"
    data_re = re.compile(r"^data\.tar\.[a-z0-9]+$")

    def prepare(self):
        self.pipe(["ar", "t", self.filename], "finding package data file")
        for filename in self.get_filenames(internal=True):
            if self.data_re.match(filename):
                data_filename = filename
                break
        else:
            raise ExtractorError(".deb contains no data.tar file")
        self.archive.seek(0, 0)
        self.pipes.pop()
        # self.pipes = start_pipes
        encoding = mimetypes.guess_type(data_filename)[1]
        if not encoding:
            raise ExtractorError("data.tar file has unrecognized encoding")
        self.pipe(
            ["ar", "p", self.filename, data_filename], "extracting data.tar from .deb"
        )
        self.pipe(self.decoders[encoding], "decoding data.tar")

    def basename(self):
        pieces = os.path.basename(self.filename).split("_")
        if len(pieces) == 1:
            return pieces[0]
        last_piece = pieces.pop()
        if (len(last_piece) > 10) or (not last_piece.endswith(".deb")):
            return BaseExtractor.basename(self)
        return "_".join(pieces)

    def check_contents(self):
        self.check_included_archives()
        self.content_type = BOMB


class DebMetadataExtractor(DebExtractor):
    def prepare(self):
        self.pipe(
            ["ar", "p", self.filename, "control.tar.gz"], "control.tar.gz extraction"
        )
        self.pipe(["zcat"], "control.tar.gz decompression")


class GemExtractor(TarExtractor):
    file_type = "Ruby gem"

    def prepare(self):
        self.pipe(["tar", "-xO", "data.tar.gz"], "data.tar.gz extraction")
        self.pipe(["zcat"], "data.tar.gz decompression")

    def check_contents(self):
        self.check_included_archives()
        self.content_type = BOMB


class GemMetadataExtractor(CompressionExtractor):
    file_type = "Ruby gem"

    def prepare(self):
        self.pipe(["tar", "-xO", "metadata.gz"], "metadata.gz extraction")
        self.pipe(["zcat"], "metadata.gz decompression")

    def basename(self):
        return os.path.basename(self.filename) + "-metadata.txt"


class NoPipeExtractor(BaseExtractor):
    # Some extraction tools won't accept the archive from stdin.  With
    # these, the piping infrastructure we normally set up generally doesn't
    # work, at least at first.  We can still use most of it; we just don't
    # want to seed self.archive with the archive file, since that sucks up
    # memory.  So instead we seed it with /dev/null, and specify the
    # filename on the command line as necessary.  We also open the actual
    # file with os.open, to make sure we can actually do it (permissions
    # are good, etc.).  This class doesn't do anything by itself; it's just
    # meant to be a base class for extractors that rely on these dumb
    # tools.
    def __init__(self, filename, encoding):
        os.close(os.open(filename, os.O_RDONLY))
        BaseExtractor.__init__(self, "/dev/null", None)
        self.filename = os.path.realpath(filename)
        self.user_stdin = True

    def extract_archive(self):
        # the commands provided by the child class have optional format codes
        # that will be replaced here
        extract_fmt_args = {
            "OUTPUT_FILE": os.path.splitext(os.path.basename(self.filename))[0],
        }
        formatted_extract_commands = [
            x.format(**extract_fmt_args) for x in self.extract_command
        ]

        self.extract_pipe = formatted_extract_commands + [self.filename]
        BaseExtractor.extract_archive(self)

    def get_filenames(self):
        self.list_pipe = self.list_command + [self.filename]
        return BaseExtractor.get_filenames(self)


class ZipExtractor(NoPipeExtractor):
    file_type = "Zip file"
    list_command = ["zipinfo", "-1"]

    @property
    def extract_command(self):
        """
        Returns the extraction command and adds a password if given.
        """
        cmd = ["unzip", "-q"]
        if self.password:
            cmd.append("-P %s" % (self.password,))
        return cmd

    def is_fatal_error(self, status):
        return (status or 0) > 1

    def timeout_check(self, pipe):
        nbs = NonblockingRead(pipe.stderr)
        errs = nbs.readlines()

        self.stderr += "".join(errs)

        # pass through the password prompt, if unzip sent one
        if errs and "password" in errs[-1]:
            sys.stdout.write("\n" + errs[-1])
            sys.stdout.flush()
            self.pw_prompted = True


class LZHExtractor(ZipExtractor):
    file_type = "LZH file"
    extract_command = ["lha", "xq"]
    list_command = ["lha", "l"]

    def border_line_file_index(self, line):
        last_space_index = None
        for index, char in enumerate(line):
            if char == " ":
                last_space_index = index
            elif char != "-":
                return None
        if last_space_index is None:
            return None
        return last_space_index + 1

    def get_filenames(self):
        filenames = NoPipeExtractor.get_filenames(self)
        for line in filenames:
            fn_index = self.border_line_file_index(line)
            if fn_index is not None:
                break
        for line in filenames:
            if self.border_line_file_index(line):
                break
            else:
                yield line[fn_index:]
        self.archive.close()


class SevenExtractor(NoPipeExtractor):
    file_type = "7z file"
    list_command = ["7z", "l", "-ba"]
    border_re = re.compile("^[- ]+$")
    extract_command = ["7z", "x"]
    space_re = re.compile(" ")

    @property
    def extract_command(self):
        """
        Returns the extraction command and adds a password if given.
        """
        cmd = ["7z", "x"]
        if self.password:
            cmd.append("-p%s" % (self.password,))
        return cmd

    def get_filenames(self):
        for line in NoPipeExtractor.get_filenames(self):
            if " " in line:
                pos = line.rindex(" ") + 1
                yield line[pos:]
        self.archive.close()

    def send_stdout_to_dev_null(self):
        return False

    def timeout_check(self, pipe):
        nbs = NonblockingRead(pipe.stdout)
        errs = nbs.readlines()

        self.stderr += "".join(errs)

        # pass through the password prompt, if 7z sent one
        if errs and "password" in errs[-1]:
            sys.stdout.write("\n" + errs[-1])
            sys.stdout.flush()
            self.pw_prompted = True


class ZstandardExtractor(NoPipeExtractor):
    file_type = "zstd file"
    extract_command = ["zstd", "-d"]
    list_command = ["zstd", "-l"]
    border_re = re.compile("^[- ]+$")

    def get_filenames(self):
        fn_index = None
        for line in NoPipeExtractor.get_filenames(self):
            if self.border_re.match(line):
                if fn_index is not None:
                    break
                else:
                    fn_index = string.rindex(line, " ") + 1
            elif fn_index is not None:
                yield line[fn_index:]
        self.archive.close()


class BrotliExtractor(NoPipeExtractor):
    file_type = "brotli file"
    extract_command = ["brotli", "--decompress", "--output={OUTPUT_FILE}"]
    # brotli command line doesn't support this mode
    list_command = ["false"]

    def get_filenames(self):
        # just raise an error, this is not supported
        raise ExtractorError


class CABExtractor(NoPipeExtractor):
    file_type = "CAB archive"
    extract_command = ["cabextract", "-q"]
    list_command = ["cabextract", "-l"]
    border_re = re.compile(r"^[-\+]+$")

    def get_filenames(self):
        filenames = NoPipeExtractor.get_filenames(self)
        for line in filenames:
            if self.border_re.match(line):
                break
        for line in filenames:
            try:
                yield line.split(" | ", 2)[2]
            except IndexError:
                break
        self.archive.close()


class ShieldExtractor(NoPipeExtractor):
    file_type = "InstallShield archive"
    extract_command = ["unshield", "x"]
    list_command = ["unshield", "l"]
    prefix_re = re.compile(r"^\s+\d+\s+")
    end_re = re.compile(r"^\s+-+\s+-+\s*$")

    def get_filenames(self):
        for line in NoPipeExtractor.get_filenames(self):
            if self.end_re.match(line):
                break
            else:
                match = self.prefix_re.match(line)
                if match:
                    yield line[match.end() :]
        self.archive.close()

    def basename(self):
        result = NoPipeExtractor.basename(self)
        if result.endswith(".hdr"):
            result = result[:-4]
        return result


class RarExtractor(NoPipeExtractor):
    file_type = "RAR archive"
    list_command = ["unrar", "v"]
    border_re = re.compile("^-+$")

    @property
    def extract_command(self):
        """
        Returns the extraction command and adds a password if given.
        """
        cmd = ["unrar", "x"]
        if self.password:
            cmd.append("-p%s" % (self.password,))
        return cmd

    def get_filenames(self):
        inside = False
        isfile = True
        for line in NoPipeExtractor.get_filenames(self):
            if self.border_re.match(line):
                if inside:
                    break
                else:
                    inside = True
            elif inside:
                if isfile:
                    yield line.strip()
                isfile = not isfile
        self.archive.close()

    def timeout_check(self, pipe):
        nbs = NonblockingRead(pipe.stderr)
        errs = nbs.readlines()

        self.stderr += "".join(errs)

        # pass through the password prompt, if unrar sent one
        if errs and "password" in errs[-1]:
            sys.stdout.write("\n" + "".join(errs))
            sys.stdout.flush()
            self.pw_prompted = True


class UnarchiverExtractor(NoPipeExtractor):
    file_type = "RAR archive"
    list_command = ["lsar"]

    @property
    def extract_command(self):
        """
        Returns the extraction command and adds a password if given.
        """
        cmd = ["unar", "-D"]
        if self.password:
            cmd.append("-p %s" % (self.password,))
        return cmd

    def get_filenames(self):
        output = NoPipeExtractor.get_filenames(self)
        next(output)
        for line in output:
            end_index = line.rfind("(")
            yield line[:end_index].strip()


class ArjExtractor(NoPipeExtractor):
    file_type = "ARJ archive"
    list_command = ["arj", "v"]
    prefix_re = re.compile(r"^\d+\)\s+")

    @property
    def extract_command(self):
        """
        Returns the extraction command and adds a password if given.
        """
        cmd = ["arj", "x", "-y"]
        if self.password:
            cmd.append("-g%s" % (self.password,))
        return cmd

    def get_filenames(self):
        for line in NoPipeExtractor.get_filenames(self):
            match = self.prefix_re.match(line)
            if match:
                yield line[match.end() :]
        self.archive.close()


class BaseHandler(object):
    def __init__(self, extractor, options):
        self.extractor = extractor
        self.options = options
        self.target = None

    def handle(self):
        command = "find"
        status = subprocess.call(
            [
                "find",
                self.extractor.target,
                "-type",
                "d",
                "-exec",
                "chmod",
                "u+rwx",
                "{}",
                ";",
            ]
        )
        if status == 0:
            command = "chmod"
            status = subprocess.call(["chmod", "-R", "u+rwX", self.extractor.target])
        if status != 0:
            return "%s returned with exit status %s" % (command, status)
        return self.organize()

    def set_target(self, target, checker):
        self.target = checker(target).check()
        if self.target != target:
            logger.warning(
                "extracting %s to %s" % (self.extractor.filename, self.target)
            )


# The "where to extract" table, with options and archive types.
# This dictates the contents of each can_handle method.
#
#         Flat           Overwrite            None
# File    basename       basename             FilenameChecked
# Match   .              .                    tempdir + checked
# Bomb    .              basename             DirectoryChecked


class FlatHandler(BaseHandler):
    @staticmethod
    def can_handle(contents, options):
        return (options.flat and (contents != ONE_ENTRY_KNOWN)) or (
            options.overwrite and (contents == MATCHING_DIRECTORY)
        )

    def organize(self):
        self.target = "."
        for curdir, _dirs, filenames in os.walk(self.extractor.target, topdown=False):
            path_parts = curdir.split(os.sep)
            if path_parts[0] == ".":
                del path_parts[1]
            else:
                del path_parts[0]
            newdir = os.path.join(*path_parts)
            if not os.path.isdir(newdir):
                os.makedirs(newdir)
            for filename in filenames:
                os.rename(
                    os.path.join(curdir, filename), os.path.join(newdir, filename)
                )
            os.rmdir(curdir)


class OverwriteHandler(BaseHandler):
    @staticmethod
    def can_handle(contents, options):
        return (options.flat and (contents == ONE_ENTRY_KNOWN)) or (
            options.overwrite and (contents != MATCHING_DIRECTORY)
        )

    def organize(self):
        self.target = self.extractor.basename()
        if os.path.isdir(self.target):
            shutil.rmtree(self.target)
        os.rename(self.extractor.target, self.target)


class MatchHandler(BaseHandler):
    @staticmethod
    def can_handle(contents, options):
        return (contents == MATCHING_DIRECTORY) or (
            (contents in ONE_ENTRY_UNKNOWN) and options.one_entry_policy.ok_for_match()
        )

    def organize(self):
        source = os.path.join(
            self.extractor.target, os.listdir(self.extractor.target)[0]
        )
        if os.path.isdir(source):
            checker = DirectoryChecker
        else:
            checker = FilenameChecker
        if self.options.one_entry_policy == EXTRACT_HERE:
            destination = self.extractor.content_name.rstrip("/")
        else:
            destination = self.extractor.basename()
        self.set_target(destination, checker)
        if os.path.isdir(self.extractor.target):
            os.rename(source, self.target)
            os.rmdir(self.extractor.target)
        else:
            os.rename(self.extractor.target, self.target)
        self.extractor.included_root = "./"


class EmptyHandler(object):
    target = ""

    @staticmethod
    def can_handle(contents, options):
        return contents == EMPTY

    def __init__(self, extractor, options):
        os.rmdir(extractor.target)

    def handle(self):
        pass


class BombHandler(BaseHandler):
    @staticmethod
    def can_handle(contents, options):
        return True

    def organize(self):
        basename = self.extractor.basename()
        self.set_target(basename, self.extractor.name_checker)
        os.rename(self.extractor.target, self.target)


@total_ordering
class BasePolicy(object):
    try:
        size = fcntl.ioctl(
            sys.stdout.fileno(), termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0)
        )
        width = struct.unpack("HHHH", size)[1]
    except IOError:
        width = 80
    width = width - 1
    choice_wrapper = textwrap.TextWrapper(
        width=width,
        initial_indent=" * ",
        subsequent_indent="   ",
        break_long_words=False,
    )

    def __init__(self, options):
        self.current_policy = None
        if options.batch:
            self.permanent_policy = self.answers[""]
        else:
            self.permanent_policy = None

    def ask_question(self, question):
        question = question + ["You can:"]
        for choice in self.choices:
            question.extend(self.choice_wrapper.wrap(choice))
        while True:
            print("\n".join(question))
            try:
                answer = get_input(self.prompt)
            except EOFError:
                return self.answers[""]
            try:
                return self.answers[answer.lower()]
            except KeyError:
                print()

    def wrap(self, question, *args):
        words = question.split()
        for arg in args:
            words[words.index("%s")] = arg
        result = [words.pop(0)]
        for word in words:
            extend = "%s %s" % (result[-1], word)
            if len(extend) > self.width:
                result.append(word)
            else:
                result[-1] = extend
        return result

    def __eq__(self, other):
        return self.current_policy == other

    def __lt__(self, other):
        return self.current_policy < other


class OneEntryPolicy(BasePolicy):
    answers = {
        "h": EXTRACT_HERE,
        "i": EXTRACT_WRAP,
        "r": EXTRACT_RENAME,
        "": EXTRACT_WRAP,
    }
    choice_template = [
        "extract the %s _I_nside a new directory named %s",
        "extract the %s and _R_ename it %s",
        "extract the %s _H_ere",
    ]
    prompt = "What do you want to do?  (I/r/h) "

    def __init__(self, options):
        BasePolicy.__init__(self, options)
        if options.flat:
            default = "h"
        elif options.one_entry_default is not None:
            default = options.one_entry_default.lower()
        else:
            return
        if "here".startswith(default):
            self.permanent_policy = EXTRACT_HERE
        elif "rename".startswith(default):
            self.permanent_policy = EXTRACT_RENAME
        elif "inside".startswith(default):
            self.permanent_policy = EXTRACT_WRAP
        elif default is not None:
            raise ValueError("bad value %s for default policy" % (default,))

    def prep(self, archive_filename, extractor):
        question = self.wrap(
            "%s contains one %s but its name doesn't match.",
            archive_filename,
            extractor.content_type,
        )
        question.append(" Expected: " + extractor.basename())
        question.append("   Actual: " + extractor.content_name)
        choice_vars = (extractor.content_type, extractor.basename())
        self.choices = [
            text % choice_vars[: text.count("%s")] for text in self.choice_template
        ]
        self.current_policy = self.permanent_policy or self.ask_question(question)

    def ok_for_match(self):
        return self.current_policy in (EXTRACT_RENAME, EXTRACT_HERE)


class RecursionPolicy(BasePolicy):
    answers = {
        "o": RECURSE_ONCE,
        "a": RECURSE_ALWAYS,
        "n": RECURSE_NOT_NOW,
        "v": RECURSE_NEVER,
        "l": RECURSE_LIST,
        "": RECURSE_NOT_NOW,
    }
    choices = [
        "_A_lways extract included archives during this session",
        "extract included archives this _O_nce",
        "choose _N_ot to extract included archives this once",
        "ne_V_er extract included archives during this session",
        "_L_ist included archives",
    ]
    prompt = "What do you want to do?  (a/o/N/v/l) "

    def __init__(self, options):
        BasePolicy.__init__(self, options)
        if options.show_list:
            self.permanent_policy = RECURSE_NEVER
        elif options.recursive:
            self.permanent_policy = RECURSE_ALWAYS

    def prep(self, current_filename, target, extractor):
        archive_count = len(extractor.included_archives)
        if (self.permanent_policy is not None) or (
            (archive_count * 10) <= extractor.file_count
        ):
            self.current_policy = self.permanent_policy or RECURSE_NOT_NOW
            return
        question = self.wrap(
            "%s contains %s other archive file(s), out of %s file(s) total.",
            current_filename,
            archive_count,
            extractor.file_count,
        )
        if target == ".":
            target = ""
        included_root = extractor.included_root
        if included_root == "./":
            included_root = ""
        while True:
            self.current_policy = self.ask_question(question)
            if self.current_policy != RECURSE_LIST:
                break
            print(
                "\n%s\n"
                % "\n".join(
                    [
                        os.path.join(target, included_root, filename)
                        for filename in extractor.included_archives
                    ]
                )
            )
        if self.current_policy in (RECURSE_ALWAYS, RECURSE_NEVER):
            self.permanent_policy = self.current_policy

    def ok_to_recurse(self):
        return self.current_policy in (RECURSE_ALWAYS, RECURSE_ONCE)


class ExtractorBuilder(object):
    extractor_map = {
        "tar": {
            "extractors": (TarExtractor,),
            "mimetypes": ("x-tar",),
            "extensions": ("tar",),
            "magic": ("POSIX tar archive",),
        },
        "zip": {
            "extractors": (ZipExtractor, SevenExtractor),
            "mimetypes": ("zip",),
            "extensions": ("zip", "jar", "epub", "xpi", "crx"),
            "magic": ("(Zip|ZIP self-extracting) archive",),
        },
        "lzh": {
            "extractors": (LZHExtractor,),
            "mimetypes": ("x-lzh", "x-lzh-compressed"),
            "extensions": ("lzh", "lha"),
            "magic": (r"LHa [\d\.\?]+ archive",),
        },
        "rpm": {
            "extractors": (RPMExtractor,),
            "mimetypes": ("x-redhat-package-manager", "x-rpm"),
            "extensions": ("rpm",),
            "magic": ("RPM",),
        },
        "deb": {
            "extractors": (DebExtractor,),
            "metadata": (DebMetadataExtractor,),
            "mimetypes": ("x-debian-package",),
            "extensions": ("deb",),
            "magic": ("Debian binary package",),
        },
        "cpio": {
            "extractors": (CpioExtractor,),
            "mimetypes": ("x-cpio",),
            "extensions": ("cpio",),
            "magic": ("cpio archive",),
        },
        "gem": {
            "extractors": (GemExtractor,),
            "metadata": (GemMetadataExtractor,),
            "mimetypes": ("x-ruby-gem",),
            "extensions": ("gem",),
        },
        "7z": {
            "extractors": (SevenExtractor,),
            "mimetypes": ("x-7z-compressed",),
            "extensions": ("7z",),
            "magic": ("7-zip archive",),
        },
        "cab": {
            "extractors": (CABExtractor,),
            "mimetypes": ("x-cab",),
            "extensions": ("cab",),
            "magic": ("Microsoft Cabinet Archive",),
        },
        "rar": {
            "extractors": (RarExtractor, UnarchiverExtractor),
            "mimetypes": ("rar",),
            "extensions": ("rar",),
            "magic": ("RAR archive",),
        },
        "arj": {
            "extractors": (ArjExtractor,),
            "mimetypes": ("arj",),
            "extensions": ("arj",),
            "magic": ("ARJ archive",),
        },
        "shield": {
            "extractors": (ShieldExtractor,),
            "mimetypes": ("x-cab",),
            "extensions": ("cab", "hdr"),
            "magic": ("InstallShield CAB",),
        },
        "msi": {
            "extractors": (SevenExtractor,),
            "mimetypes": ("x-msi", "x-ole-storage"),
            "extensions": ("msi",),
            "magic": ("Application: Windows Installer",),
        },
        "dmg": {
            "extractors": (SevenExtractor,),
            "mimetypes": ("x-apple-diskimage",),
            "extensions": ("dmg",),
            "magic": (
                "ISO 9660 CD-ROM filesystem data",
                "zlib compressed data",
            ),
        },
        "zst": {
            "extractors": (ZstandardExtractor,),
            "mimetypes": ("application/zstd",),
            "extensions": (
                "zst",
                "zstd",
            ),
            "magic": ("Zstandard compressed data",),
        },
        "brotli": {
            "extractors": (BrotliExtractor,),
            "extensions": ("br",),
        },
        "compress": {"extractors": (CompressionExtractor,)},
    }

    mimetype_map = {}
    magic_mime_map = {}
    extension_map = {}
    for ext_name, ext_info in extractor_map.items():
        for mimetype in ext_info.get("mimetypes", ()):
            if "/" not in mimetype:
                mimetype = "application/" + mimetype
            mimetype_map[mimetype] = ext_name
        for magic_re in ext_info.get("magic", ()):
            magic_mime_map[re.compile(magic_re)] = ext_name
        for extension in ext_info.get("extensions", ()):
            extension_map.setdefault(extension, []).append((ext_name, None))

    for mapping in (
        ("tar", "bzip2", "tar.bz2", "tbz2", "tb2", "tbz"),
        ("tar", "gzip", "tar.gz", "tgz"),
        ("tar", "lzma", "tar.lzma", "tlz"),
        ("tar", "xz", "tar.xz", "txz"),
        ("tar", "lz", "tar.lz"),
        ("tar", "compress", "tar.Z", "taz"),
        ("tar", "lrz", "tar.lrz"),
        ("tar", "zstd", "tar.zst"),
        ("compress", "gzip", "Z", "gz"),
        ("compress", "bzip2", "bz2"),
        ("compress", "lzma", "lzma"),
        ("compress", "xz", "xz"),
        ("compress", "lrzip", "lrz"),
    ):
        for extension in mapping[2:]:
            extension_map.setdefault(extension, []).append(mapping[:2])

    magic_encoding_map = {}
    for mapping in (
        ("bzip2", "bzip2 compressed"),
        ("gzip", "gzip compressed"),
        ("lzma", "LZMA compressed"),
        ("lzip", "lzip compressed"),
        ("lrzip", "LRZIP compressed"),
        ("zstd", "Zstandard compressed"),
        ("xz", "xz compressed"),
    ):
        for pattern in mapping[1:]:
            magic_encoding_map[re.compile(pattern)] = mapping[0]

    def __init__(self, filename, options):
        self.filename = filename
        self.options = options

    def build_extractor(self, archive_type, encoding):
        type_info = self.extractor_map[archive_type]
        if self.options.metadata and "metadata" in type_info:
            extractors = type_info["metadata"]
        else:
            extractors = type_info["extractors"]
        for extractor in extractors:
            yield extractor(self.filename, encoding)

    def get_extractor(self):
        tried_types = set()
        # As smart as it is, the magic test can't go first, because at least
        # on my system it just recognizes gem files as tar files.  I guess
        # it's possible for the opposite problem to occur -- where the mimetype
        # or extension suggests something less than ideal -- but it seems less
        # likely so I'm sticking with this.
        for func_name in ("mimetype", "extension", "magic"):
            logger.debug("getting extractors by %s" % (func_name,))
            extractor_types = getattr(self, "try_by_" + func_name)(self.filename)
            logger.debug("done getting extractors")
            for ext_args in extractor_types:
                if ext_args in tried_types:
                    continue
                tried_types.add(ext_args)
                logger.debug("trying %s extractor from %s" % (ext_args, func_name))
                for extractor in self.build_extractor(*ext_args):
                    yield extractor

    def try_by_mimetype(self, filename):
        mimetype, encoding = mimetypes.guess_type(filename)
        try:
            return [(self.mimetype_map[mimetype], encoding)]
        except KeyError:
            if encoding:
                return [("compress", encoding)]
        return []

    try_by_mimetype = classmethod(try_by_mimetype)

    def magic_map_matches(self, output, magic_map):
        return [result for regexp, result in magic_map.items() if regexp.search(output)]

    magic_map_matches = classmethod(magic_map_matches)

    def try_by_magic(self, filename):
        try:
            process = subprocess.Popen(
                ["file", "-zL", filename], stdout=subprocess.PIPE
            )
            status = process.wait()
            if status != 0:
                return []
        except FileNotFoundError:
            logger.error("'file' command not found, skipping magic test")
            return []
        output = process.stdout.readline().decode("ascii")
        process.stdout.close()
        if output.startswith("%s: " % filename):
            output = output[len(filename) + 2 :]
        mimes = self.magic_map_matches(output, self.magic_mime_map)
        encodings = self.magic_map_matches(output, self.magic_encoding_map)
        if mimes and not encodings:
            encodings = [None]
        elif encodings and not mimes:
            mimes = ["compress"]
        return [(m, e) for m in mimes for e in encodings]

    try_by_magic = classmethod(try_by_magic)

    def try_by_extension(self, filename):
        parts = filename.split(".")[-2:]
        results = []
        if len(parts) == 1:
            return results
        while parts:
            results.extend(self.extension_map.get(".".join(parts), []))
            del parts[0]
        return results

    try_by_extension = classmethod(try_by_extension)


class BaseAction(object):
    def __init__(self, options, filenames):
        self.options = options
        self.filenames = filenames
        self.target = None
        self.do_print = False

    def report(self, function, *args):
        try:
            error = function(*args)
        except EXTRACTION_ERRORS as exception:
            error = str(exception)
            logger.debug("".join(traceback.format_exception(*sys.exc_info())))
        return error

    def show_filename(self, filename):
        if len(self.filenames) < 2:
            return
        elif self.do_print:
            print()
        else:
            self.do_print = True
        print("%s:" % (filename,))


class ExtractionAction(BaseAction):
    handlers = [FlatHandler, OverwriteHandler, MatchHandler, EmptyHandler, BombHandler]

    def get_handler(self, extractor):
        if extractor.content_type in ONE_ENTRY_UNKNOWN:
            self.options.one_entry_policy.prep(self.current_filename, extractor)
        for handler in self.handlers:
            if handler.can_handle(extractor.content_type, self.options):
                logger.debug("using %s handler" % (handler.__name__,))
                self.current_handler = handler(extractor, self.options)
                break

    def show_extraction(self, extractor):
        if self.options.log_level > logging.INFO:
            return
        self.show_filename(self.current_filename)
        if extractor.contents is None:
            print(self.current_handler.target)
            return

        def reverser(x, y):
            return cmp(y, x)

        if self.current_handler.target == ".":
            filenames = extractor.contents
            filenames = sorted(filenames, key=cmp_to_key(reverser))
        else:
            filenames = [self.current_handler.target]
        pathjoin = os.path.join
        isdir = os.path.isdir
        while filenames:
            filename = filenames.pop()
            if isdir(filename):
                print("%s/" % (filename,))
                new_filenames = os.listdir(filename)
                new_filenames = sorted(new_filenames, key=cmp_to_key(reverser))
                filenames.extend(
                    [pathjoin(filename, new_filename) for new_filename in new_filenames]
                )
            else:
                print(filename)

    def run(self, filename, extractor):
        self.current_filename = filename
        error = (
            self.report(extractor.extract, self.options.batch, self.options.password)
            or self.report(self.get_handler, extractor)
            or self.report(self.current_handler.handle)
            or self.report(self.show_extraction, extractor)
        )
        if not error:
            self.target = self.current_handler.target
        return error


class ListAction(BaseAction):
    def list_filenames(self, extractor, filename):
        # We get a line first to make sure there's not going to be some
        # basic error before we show what filename we're listing.
        filename_lister = extractor.get_filenames()
        try:
            first_line = next(filename_lister)
        except StopIteration:
            self.show_filename(filename)
        else:
            self.did_list = True
            self.show_filename(filename)
            print(first_line)
        for line in filename_lister:
            print(line)

    def run(self, filename, extractor):
        self.did_list = False
        error = self.report(self.list_filenames, extractor, filename)
        if error and self.did_list:
            logger.error("lister failed: ignore above listing for %s" % (filename,))
        return error


class ExtractorApplication(object):
    def __init__(self, arguments):
        for signal_num in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signal_num, self.abort)
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        self.parse_options(arguments)
        self.setup_logger()
        self.successes = []
        self.failures = []

    def clean_destination(self, dest_name):
        try:
            os.unlink(dest_name)
        except OSError as error:
            if error.errno == errno.EISDIR:
                shutil.rmtree(dest_name, ignore_errors=True)

    def abort(self, signal_num, frame):
        signal.signal(signal_num, signal.SIG_IGN)
        print()
        logger.debug("traceback:\n" + "".join(traceback.format_stack(frame)).rstrip())
        logger.debug("got signal %s" % (signal_num,))
        try:
            basename = self.current_extractor.target
        except AttributeError:
            basename = None
        if basename is not None:
            logger.debug("cleaning up %s" % (basename,))
            clean_targets = set([os.path.realpath(".")])
            if hasattr(self, "current_directory"):
                clean_targets.add(os.path.realpath(self.current_directory))
            for directory in clean_targets:
                self.clean_destination(os.path.join(directory, basename))
        sys.exit(1)

    @staticmethod
    def get_supported_extensions():
        """
        return supported extensions
        """
        # get the lists of built-in extensions and combine them
        ext_map_base = set(ExtractorBuilder.extension_map.keys())
        ext_map = set(
            itertools.chain(
                *[
                    x["extensions"]
                    for x in ExtractorBuilder.extractor_map.values()
                    if "extensions" in x
                ]
            )
        )
        ext_map = ext_map_base.union(ext_map)

        # get the list of extensions supplied by mimetypes
        mimetypes_encodings_map = set([x.lstrip(".") for x in mimetypes.encodings_map])
        # dtrx only supports a subset of the total types_map set, filter it
        mimetypes_exts = filter(
            lambda x: mimetypes.types_map[x] in ExtractorBuilder.mimetype_map,
            mimetypes.types_map,
        )
        mimetypes_exts = set([x.lstrip(".") for x in mimetypes_exts])
        mimetypes_exts = mimetypes_encodings_map.union(mimetypes_exts)

        # sort the output for consistent order
        return sorted(ext_map.union(mimetypes_exts))

    def parse_options(self, arguments):
        parser = optparse.OptionParser(
            usage="%prog [options] archive [archive2 ...]",
            description="Intelligent archive extractor",
            version=VERSION_BANNER,
        )
        parser.add_option(
            "-l",
            "-t",
            "--list",
            "--table",
            dest="show_list",
            action="store_true",
            default=False,
            help="list contents of archives on standard output",
        )
        parser.add_option(
            "-m",
            "--metadata",
            dest="metadata",
            action="store_true",
            default=False,
            help="extract metadata from a .deb/.gem",
        )
        parser.add_option(
            "-r",
            "--recursive",
            dest="recursive",
            action="store_true",
            default=False,
            help="extract archives contained in the ones listed",
        )
        parser.add_option(
            "--one",
            "--one-entry",
            dest="one_entry_default",
            default=None,
            help=(
                "specify extraction policy for one-entry "
                + "archives: inside/rename/here"
            ),
        )
        parser.add_option(
            "-n",
            "--noninteractive",
            dest="batch",
            action="store_true",
            default=False,
            help="don't ask how to handle special cases",
        )
        parser.add_option(
            "-p",
            "--password",
            dest="password",
            default=None,
            help="provide a password for password-protected archives",
        )
        parser.add_option(
            "-o",
            "--overwrite",
            dest="overwrite",
            action="store_true",
            default=False,
            help="overwrite any existing target output",
        )
        parser.add_option(
            "-f",
            "--flat",
            "--no-directory",
            dest="flat",
            action="store_true",
            default=False,
            help="extract everything to the current directory",
        )

        def list_extensions(option, opt, value, parser, *args, **kwargs):
            """callback for optparse to list supported extensions"""
            print("\n".join(ExtractorApplication.get_supported_extensions()))
            sys.exit()

        parser.add_option(
            "--list-extensions",
            action="callback",
            callback=list_extensions,
            help=(
                "list supported filetypes by extension. note that these are the"
                " filetypes recognized by dtrx, but extraction still relies on the"
                " appropriate tool to be installed. also note that this is not a"
                " comprehensive list; dtrx will fall back on the 'file' command if the"
                " extension is unknown"
            ),
        )
        parser.add_option(
            "-v",
            "--verbose",
            dest="verbose",
            action="count",
            default=0,
            help="be verbose/print debugging information",
        )
        parser.add_option(
            "-q",
            "--quiet",
            dest="quiet",
            action="count",
            default=3,
            help="suppress warning/error messages",
        )
        self.options, filenames = parser.parse_args(arguments)
        if not filenames:
            parser.error("you did not list any archives")
        # This makes WARNING is the default.
        self.options.log_level = 10 * (self.options.quiet - self.options.verbose)
        try:
            self.options.one_entry_policy = OneEntryPolicy(self.options)
        except ValueError:
            parser.error("invalid value for --one-entry option")
        self.options.recursion_policy = RecursionPolicy(self.options)
        self.archives = {os.path.realpath(os.curdir): filenames}

    def setup_logger(self):
        logging.getLogger().setLevel(self.options.log_level)
        handler = logging.StreamHandler()
        handler.setLevel(self.options.log_level)
        formatter = logging.Formatter("dtrx: %(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.debug("logger is set up")

    def recurse(self, filename, extractor, action):
        self.options.recursion_policy.prep(filename, action.target, extractor)
        if self.options.recursion_policy.ok_to_recurse():
            for filename in extractor.included_archives:
                logger.debug("recursing with %s archive" % (extractor.content_type,))
                tail_path, basename = os.path.split(filename)
                path_args = [self.current_directory, extractor.included_root, tail_path]
                logger.debug("included root: %s" % (extractor.included_root,))
                logger.debug("tail path: %s" % (tail_path,))
                if os.path.isdir(action.target):
                    logger.debug("action target: %s" % (action.target,))
                    path_args.insert(1, action.target)
                directory = os.path.join(*path_args)
                self.archives.setdefault(directory, []).append(basename)

    def check_file(self, filename):
        try:
            result = os.stat(filename)
        except OSError as error:
            return error.strerror
        if stat.S_ISDIR(result.st_mode):
            return "cannot work with a directory"

    def show_stderr(self, logger_func, stderr):
        if stderr:
            logger_func("Error output from this process:\n" + stderr.rstrip("\n"))

    def try_extractors(self, filename, builder):
        errors = []
        for extractor in builder:
            self.current_extractor = extractor  # For the abort() method.
            error = self.action.run(filename, extractor)
            if error:
                errors.append(
                    (extractor.file_type, extractor.encoding, error, extractor.stderr)
                )
                if extractor.target is not None:
                    self.clean_destination(extractor.target)
            else:
                logfunc = logger.warning
                if extractor.pw_prompted:
                    # Normally stderr contains actual errors. If the archive
                    # contained a password, stderr is full of prompts; only
                    # relevant when debugging.
                    logfunc = logger.debug
                self.show_stderr(logfunc, extractor.stderr)
                self.recurse(filename, extractor, self.action)
                return
        logger.error("could not handle %s" % (filename,))
        if not errors:
            logger.error("not a known archive type")
            return True
        for file_type, encoding, error, stderr in errors:
            message = ["treating as", file_type, "failed:", error]
            if encoding:
                message.insert(1, "%s-encoded" % (encoding,))
            logger.error(" ".join(message))
            self.show_stderr(logger.error, stderr)
        return True

    def download(self, filename):
        url = filename.lower()
        for protocol in "http", "https", "ftp":
            if url.startswith(protocol + "://"):
                break
        else:
            return filename, None
        # FIXME: This can fail if there's already a file in the directory
        # that matches the basename of the URL.
        status = subprocess.call(["wget", "-c", filename], stdin=subprocess.PIPE)
        if status != 0:
            return None, "wget returned status code %s" % (status,)
        return os.path.basename(urlparse.urlparse(filename)[2]), None

    def run(self):
        if self.options.show_list:
            action = ListAction
        else:
            action = ExtractionAction
        self.action = action(self.options, list(self.archives.keys())[0])
        while self.archives:
            self.current_directory, self.filenames = self.archives.popitem()
            os.chdir(self.current_directory)
            for filename in self.filenames:
                filename, error = self.download(filename)
                if not error:
                    builder = ExtractorBuilder(filename, self.options)
                    error = self.check_file(filename) or self.try_extractors(
                        filename, builder.get_extractor()
                    )
                if error:
                    if error is not True:
                        logger.error("%s: %s" % (filename, error))
                    self.failures.append(filename)
                else:
                    self.successes.append(filename)
            self.options.one_entry_policy.permanent_policy = EXTRACT_WRAP
        if self.failures:
            return 1
        return 0


def main():
    app = ExtractorApplication(sys.argv[1:])
    sys.exit(app.run())


if __name__ == "__main__":
    main()
