#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPL v3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>

import os
import termios
import struct
import fcntl
import signal

from .constants import terminfo_dir


class Child:

    child_fd = pid = None
    forked = False

    def __init__(self, argv, cwd, opts):
        self.argv = argv
        self.cwd = cwd
        self.opts = opts

    def fork(self):
        if self.forked:
            return
        self.forked = True
        master, slave = os.openpty()
        fcntl.fcntl(slave, fcntl.F_SETFD, fcntl.fcntl(slave, fcntl.F_GETFD) & ~fcntl.FD_CLOEXEC)
        # Note that master and slave are in blocking mode
        pid = os.fork()
        if pid == 0:  # child
            try:
                os.chdir(self.cwd)
            except EnvironmentError:
                os.chdir('/')
            os.setsid()
            for i in range(3):
                os.dup2(slave, i)
            os.close(slave), os.close(master)
            os.closerange(3, 200)
            # Establish the controlling terminal (see man 7 credentials)
            os.close(os.open(os.ttyname(1), os.O_RDWR))
            os.environ['TERM'] = self.opts.term
            os.environ['COLORTERM'] = 'truecolor'
            if os.path.isdir(terminfo_dir):
                os.environ['TERMINFO'] = terminfo_dir
            try:
                os.execvp(self.argv[0], self.argv)
            except Exception as err:
                print('Could not launch:', self.argv[0])
                print('\t', err)
                input('\nPress Enter to exit:')
        else:  # master
            os.close(slave)
            self.pid = pid
            self.child_fd = master
            return pid

    def resize_pty(self, w, h):
        if self.child_fd is not None:
            fcntl.ioctl(self.child_fd, termios.TIOCSWINSZ, struct.pack('4H', h, w, 0, 0))

    def hangup(self):
        if self.pid is not None:
            pid, self.pid = self.pid, None
            try:
                pgrp = os.getpgid(pid)
            except ProcessLookupError:
                return
            os.killpg(pgrp, signal.SIGHUP)
            os.close(self.child_fd)
            self.child_fd = None

    def __del__(self):
        self.hangup()

    def get_child_status(self):
        if self.pid is not None:
            try:
                return os.waitid(os.P_PID, self.pid, os.WEXITED | os.WNOHANG)
            except ChildProcessError:
                self.pid = None