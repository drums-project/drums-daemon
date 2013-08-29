#!/usr/bin/env python
# -*- coding: utf-8 -*-

# TODO

try:
    import unittest2 as unittest  # pyhon < 2.7 + unittest2 installed
except ImportError:
    import unittest

import time
import random

from dimon._common import *
from pprint import pprint

class BasicTask(TaskBase):
    def __init__(self, default_interval):
        TaskBase.__init__(self, default_interval)

    def register_task_core(self, task):
        self.task_map[task] = 0

    def remove_task_core(self, task):
        del self.task_map[task]

    def do(self):
        print "beep"
        self.task_map = {key:val+1 for key,val in self.task_map.items()}
        if self.result_queue.empty():
            self.result_queue.put(self.task_map)

class TaskBaseTest(unittest.TestCase):
    def test_loop(self):
        task = BasicTask(0.1)
        task.register_task('t1')
        task.start()
        try:
            time.sleep(0.1)
            d = task.result_queue.get()
            self.assertEqual(len(d), 1)
            task.register_task('t2')
            time.sleep(0.1)
            d = task.result_queue.get()
            self.assertEqual(len(d), 2)
            time.sleep(1)
            self.assertGreater(d['t1'], 0)
            self.assertGreater(d['t2'], 0)
            d = task.result_queue.get() # flush queue
            task.remove_task('t2')
            time.sleep(0.1)
            d = task.result_queue.get()
            self.assertEqual(len(d), 1)
        finally:
            while task.is_alive():
                task.terminate()
                time.sleep(0.1)
            task.join()


def get_suite():
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(TaskBaseTest))
    return test_suite

