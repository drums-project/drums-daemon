#!/usr/bin/env python
# -*- coding: utf-8 -*-

# TODO

try:
    import unittest2 as unittest  # pyhon < 2.7 + unittest2 installed
except ImportError:
    import unittest

import time
import random
import os
import sys

from dimon._common import *
from pprint import pprint

class BasicTask(TaskBase):
    def __init__(self, result_queue, default_interval):
        TaskBase.__init__(self, result_queue, default_interval)

    def register_task_core(self, task):
        self.task_map[task] = 0

    def remove_task_core(self, task):
        del self.task_map[task]

    def do(self):
        sys.stdout.write('>')
        sys.stdout.flush()
        self.task_map = {key:val+1 for key,val in self.task_map.items()}
        if self.result_queue.empty():
            self.result_queue.put(self.task_map)

class TaskBaseTest(unittest.TestCase):
    def test_loop(self):
        q = Queue()
        task = BasicTask(q, 0.1)
        task.register_task('t1')
        task.start()
        try:
            time.sleep(0.1)
            d = q.get()
            self.assertEqual(len(d), 1)
            task.register_task('t2')
            time.sleep(0.1)
            d = q.get()
            self.assertEqual(len(d), 2)
            time.sleep(0.5)
            self.assertGreater(d['t1'], 0)
            self.assertGreater(d['t2'], 0)
            task.flush_result_queue()
            task.remove_task('t2')
            time.sleep(0.1)
            d = q.get()
            self.assertEqual(len(d), 1)
        finally:
            while task.is_alive():
                task.terminate()
                time.sleep(0.1)
            task.join()

from dimon._process import ProcessMonitor
from psutil import Process
class ProcessTaskTest(unittest.TestCase):
    def test_creation(self):
        q = Queue()
        task = ProcessMonitor(q, 0.1)
        pid = os.getpid()
        task.register_task(pid)
        task.start()
        time.sleep(0.1)
        try:
            try:
                d = q.get(block = True, timeout = 1)
            except Empty:
                self.fail("Process monitor did not report anything in 1 seconds")
            threads = d[pid]['get_threads']
            mem = d[pid]['get_memory_info']['rss']
            name = d[pid]['name']
            self.assertGreater(len(threads), 0, "Testing number of threads")
            self.assertGreater(mem, 0, "Testing memory")
            self.assertEqual(name, "python", "Testing app name")
            task.remove_task(pid)
            task.flush_result_queue()
            time.sleep(0.1)
            # The task list is empty, no update should be done
            #self.assertRaises(Queue.Empty, task.result_queue.get(), 1)
            try:
                d = q.get(block = True, timeout = 0.1)
                self.fail("No data should be put into the queue when task map is empty.")
            except Empty:
                pass

        finally:
            while task.is_alive():
                task.terminate()
                time.sleep(0.1)
            task.join()

from dimon import Dimon
class DimonProcessTest(unittest.TestCase):
    def setUp(self):
        self.flag = False
        self.pid = os.getpid()
        self.d = None

    def test_pid(self):
        def callback(pid, data):
            self.assertEqual(pid, self.pid)
            threads = data['get_threads']
            mem = data['get_memory_info']['rss']
            name = data['name']
            self.assertGreater(len(threads), 0, "Testing number of threads")
            self.assertGreater(mem, 0, "Testing memory")
            self.assertEqual(name, "python", "Testing app name")

        self.d = Dimon(process_interval = 0.1)
        self.d.monitor_pid(self.pid, callback)
        self.d.spin_once()

    def tearDown(self):
        self.d.shutdown()

def get_suite():
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(TaskBaseTest))
    test_suite.addTest(unittest.makeSuite(ProcessTaskTest))
    test_suite.addTest(unittest.makeSuite(DimonProcessTest))
    return test_suite

