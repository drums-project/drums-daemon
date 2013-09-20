#!/usr/bin/env python
# -*- coding: utf-8 -*-

# TODO

__version__ = "0.1.0"
version_info = tuple([int(num) for num in __version__.split('.')])

from _common import *
from _process import ProcessMonitor
from _host import HostMonitor
from _sock import SocketMonitor
from _latency import LatencyMonitor

from pprint import pprint
class Dimon():
    def __init__(self, process_interval = 1, host_interval = 1,
        socket_interval = 1, late_interval = 1, late_pings_per_interval = 4, late_wait_between_pings = 0.1, process_fields = [], host_fields = []):
        self.q = Queue()
        self.process_interval = process_interval
        self.host_interval = host_interval
        self.socket_interval = socket_interval
        self.process_fields = process_fields
        self.host_fields = host_fields
        self.socket_inet = "any"
        self.late_interval =late_interval
        self.late_pings_per_interval = late_pings_per_interval
        self.late_wait_between_pings = late_wait_between_pings

        self.running = False

        # Monitors
        self.proc = None
        self.host = None
        self.sock = None
        self.late = dict()

        self.callback_map = dict()

    def flush_result_queue(self):
        #TODO: Check errors?
        while not self.q.empty():
            self.q.get()

    def _shutdown_monitor(self, mon):
        logging.info("Trying to kill `%s`" % (mon, ))
        mon.set_terminate_event()
        logging.info("Waiting for process `%s` to finish." % (mon, ))
        mon.join()
        #while mon.is_alive():
        #    logging.info("> killing `%s`" % (mon, ))
        #    mon.set_terminate_event()
        #    time.sleep(0.1)
        #logging.info("Killed `%s`" % (mon, ))
        #mon.join()

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
    def _create_socket_monitor(self):
        if self.sock == None:
            logging.debug("Creating a SocketMonitor object")
            self.sock = SocketMonitor(self.q, self.socket_interval,
             self.socket_inet, "dimon_socketmonitor")
            self.sock.start()

    def _create_new_latency_monitor(self, target):
        # TODO: Customize name
        if target not in self.late:
            logging.debug("Creating a new LatencyMonitor object for %s" % (target,))
            mon = LatencyMonitor(self.q, self.late_interval, self.late_pings_per_interval, self.late_wait_between_pings, 'dimon_latency_monitor')
            self.late[target] = mon
            return True
        else:
            logging.warning("Unable to create a new monitor. A Latency monitor already exists for %s" % (target,))
            return False

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

    def set_late_interval(self, interval):
        self.late_interval = interval
        for target, late in self.late.items():
            self.late.set_interval(self.late_interval)

    def set_host_fields(self, fields):
        self.host_fields = fields
        if not self.host == None:
            self.host.set_fields(self.host_fields)

    def set_sock_interval(self, interval):
        self.socket_interval = interval
        if not self.sock == None:
            self.sock.set_interval(self.sock_interval)

    def set_latency_options(self, pings_per_interval, wait_between_pings):
        self.pings_per_interval = pings_per_interval
        self.wait_between_pings = wait_between_pings
        for target, late in self.late.items():
            late.set_options(pings_per_interval, wait_between_pings)

    def monitor_pid(self, pid, callback):
        self._create_proc_monitor()
        res = self.proc.register_task(pid)
        if res == DimonError.SUCCESS:
            self.callback_map[pid] = callback
        return res

    def monitor_host(self, callback):
        self._create_host_monitor()
        # TODO: Change 'host' to variable key
        res = self.host.register_task('host')
        if res == DimonError.SUCCESS:
            self.callback_map['host'] = callback
        return res

    def create_monitor_socket(self, callback, inet = "any"):
        self.socket_inet = inet
        self._create_socket_monitor()
        self.callback_map['sock'] = callback
        return DimonError.SUCCESS

    def add_socket_to_monitor(self, sock):
        """
        sock: tuple("tcp/udp", "src/dst/''", port number)
        """
        if self.sock == None:
            raise RuntimeError("You need to register a callback first using `create_monitor_socket`.")
            return DimonError.RUNTIME

        return self.sock.register_task(sock)

    def monitor_target_latency(self, target, callback):
        if self._create_new_latency_monitor(target):
            self.late[target].start()
            res = self.late[target].register_task(target)
            if (res == DimonError.SUCCESS):
                self.callback_map[target] = callback
            return res

    def remove_host(self):
        res = self.host.remove_task('host')
        if res == DimonError.SUCCESS:
            try:
                del self.callback_map['host']
            except:
                logging.error("host not in internal monitoring map. This should never happen")
                return DimonError.UNEXPECTED
            finally:
                self._shutdown_monitor(self.host)
                self.host = None
        return res

    def remove_pid(self, pid):
        res = self.proc.remove_task(pid)
        if res == success:
            try:
                del self.callback_map[pid]
            except KeyError:
                logging.error("pid not in internal monitoring map. This should never happen")
                return DimonError.UNEXPECTED
            finally:
                pass
                # TODO: Find a way to shutdown processmonitor when pid
                # list is empty
                #if len(self.callback_map.keys()) == 0:
                    # There is no ProcessMonitor, lets shut it down
                #    self._shutdown_monitor(self.proc)
                #    self.proc = None
        return res

    def remove_socket(self, sock):
        # TODO
        return self.proc.remove_task(sock)

    def remove_target_latency(self, target):
        if target in self.late:
            self.late[target].remove_task(target)
            self.late[target].stop()
            try:
                del self.callback_map[target]
                del self.late[target]
            except KeyError:
                logging.error("KeyError while deleting latency task. This should never happen")
                return DimonError.UNEXPECTED
        else:
            logging.error("Latency Monitor task (%s) not found." % (target,))
            return DimonError.NOTFOUND

    def shutdown(self):
        logging.info("Shutting down all active monitors")
        if not self.proc == None:
            self._shutdown_monitor(self.proc)
            self.proc = None
        if not self.host == None:
            self._shutdown_monitor(self.host)
            self.host = None
        if not self.sock == None:
            self._shutdown_monitor(self.sock)
            self.sock = None
        for target, late in self.late.items():
            self._shutdown_monitor(self.late[target])
            del self.late[target]

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





