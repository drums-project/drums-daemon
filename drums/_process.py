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

"""
Process monitoring daemon
"""

from _common import *
import psutil
# TODO: Filter out input pids for positive integers only


class ProcessMonitor(TaskBase):
    def __init__(
            self, result_queue, default_interval,
            name="drums_processmonitor", fields={}, pids=[]):
        TaskBase.__init__(self, result_queue, default_interval, name)
        self.set_fields(fields)
        for p in list(set(pids)):
            self.register_task(p)

    # TODO: This is not thread safe
    def set_fields(self, fields):
        if isinstance(fields, dict) and fields:
            self.fields = fields
        else:
            self.fields = {
                'name': [],
                'exe': [],
                'status': [],
                'cmdline': [],
                'cpu_percent': [],
                'cpu_times': [],
                'memory_info': [],
                'memory_percent': [],
                'io_counters': [],
                'threads': [],
#                'connections': []
            }

    def register_task_core(self, task, meta=''):
        """
        Adds a pid to the task_map
        """
        assert isinstance(meta, basestring)
        try:
            self.logger.debug("Registering pid: %s" % (task,))
            self.task_map[task] = (psutil.Process(task), meta)
            return DrumsError.SUCCESS
        except psutil.NoSuchProcess:
            self.logger.error(
                "[in %s] Error adding PID (NoSuchProcess) `%s`" % (self, task))
            return DrumsError.NOTFOUND
        except psutil.AccessDenied:
            self.logger.error(
                "[in %s] Error adding PID (AccessDenied) `%s`" % (self, task))
            return DrumsError.ACCESSDENIED

    def remove_task_core(self, task, meta=''):
        try:
            del self.task_map[task]
            return DrumsError.SUCCESS
        except KeyError:
            self.logger.error("[in %s] Error removing PID `%s`" % (self, task))
            return DrumsError.NOTFOUND

    def do(self):
        data = dict()
        # TODO: Check if the outer try is still needed
        try:
            for pid, (proc, meta) in self.task_map.items():
                data[pid] = dict()
                for f, params in self.fields.items():
                    attr = getattr(proc, f, None)
                    if callable(attr):
                        try:
                            dummy = attr()
                        except TypeError:
                            dummy = attr(params[0])
                    else:
                        self.logger.warning(
                            "[in %s] Attribute `%s` not found." % (self, f))
                        continue
                    data[pid][f] = psutil_convert(dummy)
                data[pid]['timestamp'] = time.time()
                data[pid]['meta'] = meta

            if data:
                try:
                    self.result_queue.put(data)
                except Queue.Full:
                    self.logger.error(
                        "[in %s] Output queue is full in" % (self, ))
                    #finally:
                    #    pass

        except AttributeError:
            self.logger.warning(
                "Exception: [in %s] Attribute '%s' not found." % (self, f))
        # TODO: Fix the following circular loop
        except psutil.NoSuchProcess:
            self.logger.warning("NoSuchProcess for %s, removing it", pid)
            del self.task_map[pid]
        except psutil.AccessDenied:
            self.logger.warning("AccessDenied for %s, removing it", pid)
            del self.task_map[pid]
