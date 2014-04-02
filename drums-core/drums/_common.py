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
Common functions and classes for drums
"""

# idea from : http://stackoverflow.com/a/9252020/1215297
#concurrency_impl = 'gevent' # single process, single thread
#concurrency_impl = 'threading' # single process, multiple threads
concurrency_impl = 'multiprocessing'  # multiple processes

if concurrency_impl == 'gevent':
    import gevent.monkey
    gevent.monkey.patch_all()

if concurrency_impl in ['gevent', 'threading']:
    from threading import Thread, Event
    from Queue import Queue, Empty, Full
elif concurrency_impl == 'multiprocessing':
    from multiprocessing import Process as Thread
    from multiprocessing import Queue, Event
    from Queue import Empty, Full
    from setproctitle import setproctitle

import sys
import logging
import time


class __drums__error():
    def __init__(self):
        self.SUCCESS = 0
        self.NOTFOUND = 1
        self.ACCESSDENIED = 2
        self.TIMEOUT = 3
        self.RUNTIME = 4
        self.UNEXPECTED = 5

DrumsError = __drums__error()


# TODO: Write test
def namedtuple_to_dict(nt):
    return {name: getattr(nt, name) for name in nt._fields}


# TODO: Refactor to Python < 2.7
# TODO: Write test
def psutil_convert(data):
    if isinstance(data, tuple):
        return namedtuple_to_dict(data)
    elif type(data) is list and data:
        if isinstance(data[0], tuple):
            return [namedtuple_to_dict(d) for d in data]
        else:
            # TODO: Why not just return the list?
            return data
    else:
        return data


class TaskBase(Thread):
    def __init__(self, result_queue, default_interval, name="drums_basetask"):
        Thread.__init__(self, target=None, name=name)
        assert default_interval > 0
        self._default_interval = default_interval
        # TODO: Check the overhead of calling 2 time() per loop
        self._last_loop_time = time.time()
        self._terminate_event = Event()
        self.task_map = dict()
        self.result_queue = result_queue
        # TODO: Should all tasks be daemons?
        self.cmd_queue = Queue()
        self.feedback_queue = Queue()
        self.daemon = True
        self.name = name
        self.logger = logging.getLogger(type(self).__name__)

        try:
            setproctitle(self.name)
        except NameError:
            self.logger.warn("setproctitle is not available.")
            pass
        self.logger.info("Initiated a new Task Request: %s" % (self.name,))

    def __repr__(self):
        name = self.__class__.__name__
        return '<%s at %#x>' % (name, id(self))

    # TODO: Not Thread Safe
    def set_interval(self, interval):
        self._default_interval = interval

    # TODO: Not Thread Safe
    def get_interval(self):
        return self._default_interval

    # This is very dangerous, because one Task will remove all pending
    # Results of itself and all other tasks.
    def flush_result_queue(self):
        #TODO: Check errors?
        while not self.result_queue.empty():
            self.result_queue.get()

    def set_terminate_event(self):
        self._terminate_event.set()

    def register_task(self, task, meta=''):
        try:
            self.cmd_queue.put(('a', task, meta))
            # Wait 5 seconds for the feeback
            try:
                return self.feedback_queue.get(block=True, timeout=5)
            except Empty:
                return DrumsError.TIMEOUT
        except Full:
            self.logger.error("Queue is full %s", self)

    def remove_task(self, task, meta=''):
        try:
            self.cmd_queue.put(('r', task, meta))
            try:
                # Wait 5 seconds for the feeback
                return self.feedback_queue.get(block=True, timeout=5)
            except Empty:
                return DrumsError.TIMEOUT
        except Full:
            self.logger.error("Queue is full %s", self)

    def register_task_core(self, task, meta=''):
        raise NotImplementedError

    def remove_task_core(self, task):
        raise NotImplementedError

    def run(self):
        """
        The main loop
        """
        try:
            self._last_loop_time = time.time()
            while not self._terminate_event.is_set():
                self.do()
                diff = time.time() - self._last_loop_time
                sleep_time = self._default_interval - diff
                if sleep_time <= 0.0:
                    self.logger.warning(
                        "Default interval for `%s` is too small (%s) \
                        for the task. Last loop: %s" %
                        (self.name, self._default_interval, diff))
                else:
                    # Process Command Queue in idle time
                    idle_start = time.time()
                    #self.logger.info(
                    #    "[running time] %s, %.9f", self.name, diff)
                    while True:
                        remaining_time = idle_start + sleep_time - time.time()
                        if remaining_time < 0:
                            break
                        try:
                            cmd, task, meta = self.cmd_queue.get(
                                block=True, timeout=remaining_time)
                            if cmd == 'a':
                                self.feedback_queue.put(
                                    self.register_task_core(task, meta))
                            elif cmd == 'r':
                                self.feedback_queue.put(
                                    self.remove_task_core(task, meta))
                            else:
                                raise ValueError(
                                    "cmd %s not recognized in %s"
                                    % (cmd, self))
                        except Empty:
                            break

                self._last_loop_time = time.time()

            while not self.feedback_queue.empty():
                self.feedback_queue.get()
            self.logger.debug("Task %s terminated.", self)
        except:
            self.logger.warning(
                "Task(%s) exited with '%s'" %
                (self.name, sys.exc_info()))

        return True
