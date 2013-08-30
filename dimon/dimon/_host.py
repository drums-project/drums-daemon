# -*- coding: utf-8 -*-

"""
Host monitoring daemon
"""

from _common import *
import psutil
# TODO: Refactor to Python < 2.7
# TODO: Write test
def psutil_convert(data):
    if isinstance(data, tuple):
        return namedtuple_to_dict(data)
    elif type(data) is list:
        if isinstance(data[0], tuple):
            return [namedtuple_to_dict(d) for d in data]
        else:
            return dict(data)
    else:
        return data

class HostMonitor(TaskBase):
    def __init__(self, result_queue, default_interval, name = "", fields = [], pids = []):
        TaskBase.__init__(self, result_queue, default_interval, name)
        self.set_fields(fields)
        for p in list(set(pids)):
            self.register_task(p)

    def set_fields(self, fields):
        if len(fields) > 0:
            self.fields = list(set(fields))
        else:
            # TODO: why does get_boot_time() throw exception?
            self.fields = ['cpu_percent', 'cpu_times',
            'virtual_memory','swap_memory', 'disk_usage'
            'disk_io_counters', 'net_io_counters']

    def register_task_core(self, task):
        """
        Adds a pid to the task_map
        """
        logging.debug("Registering host")
        self.task_map['host'] = psutil


    def remove_task_core(self, task):
        try:
            del self.task_map['host']
        except KeyError:
            logging.warning("[in %s] Error removing host")

    def do(self):
        data = dict()
        if not 'host' in self.task_map:
            return

        data['host'] = dict()
        for f in self.fields:
            # Due to lots of variation in function calls, it is better
            # to rewrite the code from _process.py
            attr = getattr(proc, f, None)
            if callable(attr):
                if f == "cpu_percent":
                    dummy = attr(interval = 0, percpu = True)
                elif f == ["cpu_times"]:
                    dummy = attr(percpu = True)
                elif f in ["disk_io_counters", "disk_usage"]:
                    # TODO: Implement this
                    dummy = []
                elif f == "net_io_counters":
                    dummy = attr(pernic = True)
            elif attr != None:
                dummy = str(attr)
            else:
                logging.warning("[in %s] Attribute `%s` not found."
                    % (self, f))
                continue

            # This is all about the s**t about pickle is not able
            # to encode/decode a nested class (used by psutils)
            # this code converts namedtuples to dict
            data['host'][f] = psutil_convert(dummy)

        if len(data) > 0:
            try:
                self.result_queue.put(data)
            except Queue.Full:
                logging.error("[in %s] Output queue is full in"
                    % (self, ))
            finally:
                pass#pprint(data)

