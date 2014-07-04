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
Host monitoring daemon
"""

from _common import *
import psutil


class HostMonitor(TaskBase):
    def __init__(
            self, result_queue, default_interval,
            name="drums_hostmonitor", fields={}, pids=[]):
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
                'boot_time': [],
                'cpu_percent': [],
                'cpu_times': [],
                'virtual_memory': [],
                'swap_memory': [],
                'disk_usage': ['/'],
                'disk_io_counters': [],
                'net_io_counters': []}

    def register_task_core(self, task, meta=''):
        """
        add current host to task_map
        """
        assert isinstance(meta, basestring)
        self.logger.debug("Registering host")
        self.task_map['host'] = (psutil, meta)
        return DrumsError.SUCCESS

    def remove_task_core(self, task, meta=''):
        try:
            del self.task_map['host']
            return DrumsError.SUCCESS
        except KeyError:
            self.logger.error("Error removing host")
            return DrumsError.NOTFOUND

    def do(self):
        data = dict()
        if not 'host' in self.task_map:
            return

        data['host'] = dict()
        for f, params in self.fields.items():
            attr = getattr(psutil, f, None)
            if callable(attr):
                try:
                    dummy = attr()
                except TypeError:
                    dummy = attr(params[0])
            else:
                self.logger.debug(
                    "[in %s] Attribute `%s` is not found or not \
                    callable in psutil object."
                    % (self, f))
                continue

            data['host'][f] = psutil_convert(dummy)

        if data:
            try:
                data['host']['timestamp'] = time.time()
                data['host']['meta'] = self.task_map['host'][1]
                self.result_queue.put(data)
            except Queue.Full:
                self.logger.error(
                    "[in %s] Output queue is full in" % (self, ))
            finally:
                pass
