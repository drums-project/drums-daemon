# -*- coding: utf-8 -*-

"""
Process monitoring daemon
"""

from _common import *
from psutil import Process

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

class ProcessMonitor(TaskBase):
    def __init__(self, default_interval, name = "", fields = [], pids = []):
        TaskBase.__init__(self, default_interval, name)
        if len(fields) > 0:
            self.fields = fields
        else:
            self.fields = ['name', 'status','get_cpu_percent', 'get_cpu_times',
            'get_memory_info','get_io_counters', 'get_threads']

        for p in list(set(pids)):
            self.register_task(p)

    def register_task_core(self, task):
        """
        Adds a pid to the task_map
        """
        try:
            self.task_map[task] = Process(task)
        except:
            logging.error("[in %s] Error adding PID `%s`"
                % (self, task))

    def remove_task_core(self, task):
        try:
            del self.task_map[task]
        except:
            logging.warning("[in %s] Error removing PID `%s`"
                % (self, task))


    def do(self):
        data = dict()
        for pid, proc in self.task_map.items():
            data[pid] = dict()
            for f in self.fields:
                attr = getattr(proc, f, None)
                if callable(attr):
                    dummy = attr()
                elif attr != None:
                    dummy = str(attr)
                else:
                    logging.warning("[in %s] Attribute `%s` not found."
                        % (self, f))
                    continue

                # This is all about the s**t about pickle is not able
                # to encode/decode a nested class (used by psutils)
                # this code converts namedtuples to dict
                data[pid][f] = psutil_convert(dummy)


        if len(data) > 0:
            try:
                self.result_queue.put(data)
            except Queue.Full:
                logging.error("[in %s] Output queue is full in"
                    % (self, ))

