#!/usr/bin/env python
# -*- coding: utf-8 -*-

# TODO

__version__ = "0.1.0"
version_info = tuple([int(num) for num in __version__.split('.')])

from _common import *
from _process import ProcessMonitor
from _host import HostMonitor

from pprint import pprint
class Dimon():
    def __init__(self, process_interval = 1, host_interval = 1,
        socket_interval = 1, process_fields = [], host_fields = []):
        self.q = Queue()
        self.process_interval = process_interval
        self.host_interval = host_interval
        self.socket_interval = socket_interval
        self.process_fields = process_fields
        self.host_fields = host_fields

        self.running = False

        # Monitors
        self.proc = None
        self.host = None
        self.sock = None

        self.callback_map = dict()

    def flush_result_queue(self):
        #TODO: Check errors?
        while not self.q.empty():
            self.q.get()

    def _shutdown_monitor(self, mon):
        while mon.is_alive():
            mon.terminate()
            time.sleep(0.1)
        mon.join()

    def _create_proc_monitor(self):
        if self.proc == None:
            logging.debug("Creating a ProcessMonitor object")
            self.proc = ProcessMonitor(self.q, self.process_interval,
             "dimon_processmonitor", self.process_fields)
            self.proc.start()

    def _create_host_monitor(self):
        if self.host == None:
            logging.debug("Creating a HostMonitor object")
            self.host = HostMonitor(self.q, self.host_interval,
             "dimon_hostmonitor", self.host_fields)
            self.host.start()

    def set_process_interval(self, interval):
        self.process_interval = interval
        if not self.proc == None:
            self.proc.set_interval(self.process_interval)

    def set_process_fields(self, fields):
        self.process_fields = fields
        if not self.proc == None:
            self.proc.set_fields(self.process_fields)

    def set_host_interval(self, interval):
        self.host_interval = interval
        if not self.host == None:
            self.host.set_interval(self.host_interval)

    def set_host_fields(self, fields):
        self.host_fields = fields
        if not self.host == None:
            self.host.set_fields(self.host_fields)

    def monitor_pid(self, pid, callback):
        self._create_proc_monitor()
        self.proc.register_task(pid)
        self.callback_map[pid] = callback

    def monitor_host(self, callback):
        self._create_host_monitor()
        # TODO: Change 'host' to variable key
        self.host.register_task('host')
        self.callback_map['host'] = callback

    def remove_host(self):
        self.host.remove_task('host')
        try:
            del self.callback_map['host']
        except:
            logging.error("host not in internal monitoring map. This should never happen")
        finally:
            self._shutdown_monitor(self.host)
            self.host = None

    def remove_pid(self, pid):
        self.proc.remove_task(pid)
        try:
            del self.callback_map[pid]
        except:
            logging.error("pid not in internal monitoring map. This should never happen")
        finally:
            pass
            # TODO: Find a way to shutdown processmonitor when pid
            # list is empty
            #if len(self.callback_map.keys()) == 0:
                # There is no ProcessMonitor, lets shut it down
            #    self._shutdown_monitor(self.proc)
            #    self.proc = None

    def shutdown(self):
        logging.info("Shutting down all active monitors")
        if not self.proc == None:
            self._shutdown_monitor(self.proc)
            self.proc = None
        if not self.host == None:
            self._shutdown_monitor(self.host)
            self.host = None

    def spin_once(self):
        # results are dicts, keys are tasks
        data_pair_dict = self.q.get()
        for task, data in data_pair_dict.items():
            try:
                self.callback_map[task](task, data)
            except KeyError:
                logging.error("Error calling callback for task=%s"
                    % (task,))

    def spin(self):
        self.running = True
        while True:
            self.spin_once()





