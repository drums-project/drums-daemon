#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright 2013 Mani Monajjemi (AutonomyLab, Simon Fraser University)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

__version__ = "0.9.6"
version_info = tuple([int(num) for num in __version__.split('.')])

from _common import *
from _process import ProcessMonitor
from _host import HostMonitor
from _sock import SocketMonitor
from _latency import LatencyMonitor

# To guarantee thread safety
from threading import Thread, Event, Lock


class Singleton(type):
    """
    A singleton metaclass.
    From: http://c2.com/cgi/wiki?PythonSingleton
    """
    def __init__(cls, name, bases, dictionary):
        super(Singleton, cls).__init__(name, bases, dictionary)
        cls._instance = None
        cls._lock = Lock()

    def __call__(cls, *args, **kws):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Singleton, cls).__call__(*args, **kws)
        return cls._instance


class Drums(Thread):
    __metaclass__ = Singleton

    def __init__(
            self, process_interval=1, host_interval=1,
            socket_interval=1, late_interval=5,
            late_pings_per_interval=5, late_wait_between_pings=0.2,
            process_fields={}, host_fields={}):
        Thread.__init__(self)
        self.q = Queue()
        self.process_interval = process_interval
        self.host_interval = host_interval
        self.socket_interval = socket_interval
        self.process_fields = process_fields
        self.host_fields = host_fields
        self.socket_inet = "any"
        self.late_interval = late_interval
        self.late_pings_per_interval = late_pings_per_interval
        self.late_wait_between_pings = late_wait_between_pings
        self.terminate_event = Event()
        self.is_running = Event()

        # Monitors
        self.proc = None
        self.host = None
        self.sock = None
        self.late = dict()

        self.callback_map = dict()
        # TODO: Breakdown locks
        self.lock = Lock()
        self.logger = logging.getLogger(type(self).__name__)

    def init(self):
        if not self.is_running.is_set():
            self.logger.info("Starting drums's processing thread ...")
            self.start()

    def flush_result_queue(self):
        #TODO: Check errors?
        while not self.q.empty():
            self.q.get()

    def _shutdown_monitor(self, mon):
        self.logger.info("Trying to kill `%s`" % (mon, ))
        mon.set_terminate_event()
        self.logger.info("Waiting for process `%s` to finish." % (mon, ))
        mon.join()
        #while mon.is_alive():
        #    self.logger.info("> killing `%s`" % (mon, ))
        #    mon.set_terminate_event()
        #    time.sleep(0.1)
        #self.logger.info("Killed `%s`" % (mon, ))
        #mon.join()

    def _create_proc_monitor(self):
        if self.proc is None:
            self.logger.debug("Creating a ProcessMonitor object")
            self.proc = ProcessMonitor(
                self.q, self.process_interval,
                "drums_processmonitor", self.process_fields)
            self.proc.start()

    def _create_host_monitor(self):
        self.logger.debug("Creating a HostMonitor object")
        self.host = HostMonitor(
            self.q, self.host_interval,
            "drums_hostmonitor", self.host_fields)
        self.host.start()

    def _create_socket_monitor(self, inet="any"):
        if self.sock is None:
            self.logger.debug("Creating a SocketMonitor object")
            self.sock = SocketMonitor(
                self.q, self.socket_interval,
                inet, "drums_socketmonitor")
            self.sock.start()

    def _create_new_latency_monitor(self, target):
        # TODO: Customize name
        if target not in self.late:
            self.logger.debug(
                "Creating a new LatencyMonitor object for %s" % (target,))
            mon = LatencyMonitor(
                self.q, self.late_interval, self.late_pings_per_interval,
                self.late_wait_between_pings, 'drums_latency_monitor')
            self.late[target] = mon
            return True
        else:
            self.logger.warning(
                "Unable to create a new monitor. \
                A Latency monitor already exists for %s" % (target,))
            return False

    def set_process_interval(self, interval):
        self.process_interval = interval
        if not self.proc is None:
            self.proc.set_interval(self.process_interval)

    def set_process_fields(self, fields):
        self.process_fields = fields
        if not self.proc is None:
            self.proc.set_fields(self.process_fields)

    def set_host_interval(self, interval):
        self.host_interval = interval
        if not self.host is None:
            self.host.set_interval(self.host_interval)

    def set_late_interval(self, interval):
        self.late_interval = interval
        for target, late in self.late.items():
            self.late.set_interval(self.late_interval)

    def set_host_fields(self, fields):
        self.host_fields = fields
        if not self.host is None:
            self.host.set_fields(self.host_fields)

    def set_sock_interval(self, interval):
        self.socket_interval = interval
        if not self.sock is None:
            self.sock.set_interval(self.sock_interval)

    def set_latency_options(self, pings_per_interval, wait_between_pings):
        self.pings_per_interval = pings_per_interval
        self.wait_between_pings = wait_between_pings
        for target, late in self.late.items():
            late.set_options(pings_per_interval, wait_between_pings)

    def monitor_pid(self, pid, callback, meta=''):
        self._create_proc_monitor()
        res = self.proc.register_task(pid, meta)
        if res == DrumsError.SUCCESS:
            with self.lock:
                self.callback_map[pid] = callback
        return res

    def monitor_host(self, callback, meta=''):
        self._create_host_monitor()
        # TODO: Change 'host' to variable key
        res = self.host.register_task('host', meta)
        if res == DrumsError.SUCCESS:
            with self.lock:
                self.callback_map['host'] = callback
        return res

    def monitor_socket(self, sock, callback, meta=''):
        """
        sock: tuple("tcp/udp", "src/dst/''", port number)
        """
        #self.socket_inet = inet
        self._create_socket_monitor()
        res = self.sock.register_task(sock, meta)
        if res == DrumsError.SUCCESS:
            with self.lock:
                proto, direction, port = sock
                self.callback_map["%s:%s" % (proto, port)] = callback
        return res

    def monitor_target_latency(self, target, callback, meta=''):
        if self._create_new_latency_monitor(target):
            self.late[target].start()
            res = self.late[target].register_task(target, meta)
            if (res == DrumsError.SUCCESS):
                with self.lock:
                    self.callback_map[target] = callback
            return res

    def remove_host(self):
        if not self.host:
            self.logger.error("Drums HostMonitor has not been started yet.")
            return DrumsError.NOTFOUND

        res = self.host.remove_task('host')
        if res == DrumsError.SUCCESS:
            try:
                with self.lock:
                    del self.callback_map['host']
            except:
                self.logger.error(
                    "host not in internal monitoring map. \
                    This should never happen")
                return DrumsError.UNEXPECTED
            finally:
                self._shutdown_monitor(self.host)
                self.host = None
        return res

    def remove_pid(self, pid):
        if not self.proc:
            self.logger.error(
                "Drums ProcessMonitor has not been started yet.")
            return DrumsError.NOTFOUND

        res = self.proc.remove_task(pid)
        if res == DrumsError.SUCCESS:
            try:
                with self.lock:
                    del self.callback_map[pid]
            except KeyError:
                self.logger.error(
                    "pid not in internal monitoring map. \
                    This should never happen")
                return DrumsError.UNEXPECTED
            finally:
                pass
                # TODO: Find a way to shutdown processmonitor when pid
                # list is empty
                #if len(self.callback_map.keys()) == 0:
                    # There is no ProcessMonitor, lets shut it down
                #    self._shutdown_monitor(self.proc)
                #    self.proc = None
        return res

    def remove_socket(self, sock, meta=''):
        if not self.sock:
            self.logger.error("Drums SockMonitor has not been started yet.")
            return DrumsError.NOTFOUND
        # TODO
        return self.sock.remove_task(sock, meta)

    def remove_target_latency(self, target):
        if target in self.late:
            res = self.late[target].remove_task(target)
            self._shutdown_monitor(self.late[target])
            try:
                with self.lock:
                    del self.callback_map[target]
                del self.late[target]
                return res
            except KeyError:
                self.logger.error(
                    "KeyError while deleting latency task. \
                    This should never happen")
                return DrumsError.UNEXPECTED
        else:
            self.logger.error(
                "Latency Monitor task (%s) not found." % (target,))
            return DrumsError.NOTFOUND

    def is_shutdown(self):
        return self.terminate_event.is_set()

    def shutdown(self):
        if not self.is_running.is_set():
            self.logger.warning("Drums is not running ...")
            return

        self.logger.info("Shutting down drums ...")
        self.q.put({'shutdown': {'shutdown', None}})
        self.terminate_event.set()

        # TODO: Should we choose join() instead?
        while self.is_running.is_set():
            pass

        self.logger.info("Cleaning up ...")

        with self.lock:
            if not self.proc is None:
                self._shutdown_monitor(self.proc)
                self.proc = None
            if not self.host is None:
                self._shutdown_monitor(self.host)
                self.host = None
            if not self.sock is None:
                self._shutdown_monitor(self.sock)
                self.sock = None
            for target, late in self.late.items():
                self._shutdown_monitor(self.late[target])
                del self.late[target]

        self.logger.info("Cleaned up.")

    # This runs its own context
    def run(self):
        # results are dicts, keys are tasks
        self.logger.info("Drums's processing thread started.")
        self.is_running.set()
        while not self.terminate_event.is_set():
            data_pair_dict = self.q.get()
            for task, data in data_pair_dict.items():
                if task == 'shutdown':
                    self.logger.info("Shutdown request received ...")
                    break
                try:
                    with self.lock:
                        self.callback_map[task](task, data)
                except KeyError:
                    self.logger.error(
                        "Error calling callback for task=%s"
                        % (task,))

        self.logger.info("Drums's processing thread exited cleanly.")
        self.is_running.clear()
        return
