# -*- coding: utf-8 -*-

"""
Common functions and classes for dimon
"""

# idea from : http://stackoverflow.com/a/9252020/1215297
#concurrency_impl = 'gevent' # single process, single thread
#concurrency_impl = 'threading' # single process, multiple threads
concurrency_impl = 'multiprocessing' # multiple processes

if concurrency_impl == 'gevent':
    import gevent.monkey; gevent.monkey.patch_all()

if concurrency_impl in ['gevent', 'threading']:
    from threading import Thread, Event, Lock
    from Queue import Queue, Empty, Full
if concurrency_impl == 'multiprocessing':
    from multiprocessing import Process as Thread
    from multiprocessing import Queue, Event
    from Queue import Empty, Full

import sys
import logging
import time

class __dimon__error():
    def __init__(self):
        self.SUCCESS  = 0
        self.NOTFOUND = 1
        self.ACCESSDENIED = 2
        self.TIMEOUT = 3
        self.RUNTIME = 4
        self.UNEXPECTED = 5

DimonError = __dimon__error()

# TODO: Write test
def namedtuple_to_dict(nt):
    return {name:getattr(nt, name) for name in nt._fields}

# TODO: Refactor to Python < 2.7
# TODO: Write test
def psutil_convert(data):
    if isinstance(data, tuple):
        return namedtuple_to_dict(data)
    elif type(data) is list:
        if isinstance(data[0], tuple):
            return [namedtuple_to_dict(d) for d in data]
        else:
            # TODO: Why not just return the list?
            return data
    else:
        return data

# TODO: Merge these classes
class TaskBase(Thread):
    def __init__(self, result_queue, default_interval, name = ""):
        Thread.__init__(self, target = None, name = name)
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

    def __repr__(self):
        name =  self.__class__.__name__
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
                return self.feedback_queue.get(block = True, timeout = 5)
            except Empty:
                return DimonError.TIMEOUT
        except Full:
            logging.error("Queue is full %s", self)

    def remove_task(self, task):
        try:
            self.cmd_queue.put(('r', task, ''))
            try:
                # Wait 5 seconds for the feeback
                return self.feedback_queue.get(block = True, timeout = 5)
            except Empty:
                return DimonError.TIMEOUT
        except Full:
            logging.error("Queue is full %s", self)

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
                # Process command queue
                # while not self.cmd_queue.empty():
                #     cmd, task = self.cmd_queue.get()
                #     # Send feedback using feedback_queue
                #     if cmd == 'a':
                #         self.feedback_queue.put(self.register_task_core(task))
                #     elif cmd == 'r':
                #         self.feedback_queue.put(self.remove_task_core(task))
                #     else:
                #         raise ValueError("cmd %s not recognized in %s" % (cmd, self))
                self.do()
                diff = time.time() - self._last_loop_time
                sleep_time = self._default_interval - diff
                if sleep_time <= 0.0:
                    logging.warning("Default interval for `%s` is too small (%s) for the task. Last loop: %s" % (self.name, self._default_interval, diff))
                else:
                    # Process Command Queue in idle time
                    idle_start = time.time()
                    while True:
                        remaining_time = idle_start + sleep_time - time.time()
                        if remaining_time < 0:
                            break
                        try:
                            cmd, task, meta = self.cmd_queue.get(block=True, timeout=remaining_time)
                            if cmd == 'a':
                                self.feedback_queue.put(self.register_task_core(task, meta))
                            elif cmd == 'r':
                                self.feedback_queue.put(self.remove_task_core(task))
                            else:
                                raise ValueError("cmd %s not recognized in %s" % (cmd, self))
                        except Empty:
                            break

                self._last_loop_time = time.time()

            while not self.feedback_queue.empty():
                self.feedback_queue.get()
            logging.debug("Task %s terminated.", self)
        except:
            logging.warning("Task(%s) exited with '%s'" % (self.name, sys.exc_info()))

        return True
