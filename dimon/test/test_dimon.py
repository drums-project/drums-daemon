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
        #if self.result_queue.empty():
        #pprint(self.task_map)
        self.result_queue.put(self.task_map)

class TaskBaseTest(unittest.TestCase):
    def test_basic_task_loop(self):
        q = Queue()
        task = BasicTask(q, 0.1)
        task.register_task('t1')
        task.start()
        try:
            time.sleep(0.1)
            d = q.get(); task.flush_result_queue()
            self.assertEqual(len(d), 1)
            task.register_task('t2')
            time.sleep(0.1)
            d = q.get(); task.flush_result_queue()
            self.assertEqual(len(d), 2)
            time.sleep(0.5)
            d = q.get(); task.flush_result_queue()
            self.assertGreater(d['t1'], 0)
            self.assertGreater(d['t2'], 0)
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
    def test_process_creation(self):
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

from dimon._host import HostMonitor
import psutil
class HostTaskTest(unittest.TestCase):
    def test_host_creation(self):
        q = Queue()
        task = HostMonitor(q, 0.1)
        task.register_task(None)
        task.start()
        time.sleep(0.1)
        try:
            try:
                d = q.get(block = True, timeout = 1)
            except Empty:
                self.fail("Host monitor did not report anything in 1 seconds")
            #pprint(d)
            net_count = d['host']['net_io_counters']
            vm = d['host']['virtual_memory']
            self.assertGreater(len(net_count), 0, "net_io_counter type test")
            self.assertGreater(vm['active'], 0)
            task.remove_task('host')
            task.flush_result_queue()
            time.sleep(0.25)
            # The task list is empty, no update should be done
            #self.assertRaises(Queue.Empty, task.result_queue.get(), 1)
            try:
                d = q.get(block = True, timeout = 0.25)
                self.fail("No data should be put into the queue when task map is empty.")
            except Empty:
                pass

        finally:
            while task.is_alive():
                task.terminate()
                time.sleep(0.1)
            task.join()

from dimon import Dimon
import subprocess
class DimonProcessTest(unittest.TestCase):
    def setUp(self):
        self.flag = False
        self.flag_another = False
        self.pid = os.getpid()
        self.d = None
        p = subprocess.Popen(["sleep", "10"])
        self.pid_another = p.pid

    def test_dimon_pids_callback(self):
        def callback(pid, data):
            self.flag = True
            self.assertEqual(pid, self.pid)
            threads = data['get_threads']
            mem = data['get_memory_info']['rss']
            name = data['name']
            self.assertGreater(len(threads), 0, "Testing number of threads")
            self.assertGreater(mem, 0, "Testing memory")
            self.assertEqual(name, "python", "Testing app name")

        def callback_another(pid, data):
            self.flag_another = True
            self.assertEqual(pid, self.pid_another)

        self.d = Dimon(process_interval = 0.1)
        self.d.monitor_pid(self.pid, callback)
        self.d.monitor_pid(self.pid_another, callback_another)
        time.sleep(0.2)
        # Flush all data generated so far
        self.d.flush_result_queue()
        # Trigger the callbacks with the most fresh one
        self.d.spin_once()
        self.assertEqual(self.flag, True)
        self.assertEqual(self.flag_another, True)

    def tearDown(self):
        self.d.shutdown()

def get_suite():
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(TaskBaseTest))
    test_suite.addTest(unittest.makeSuite(ProcessTaskTest))
    test_suite.addTest(unittest.makeSuite(HostTaskTest))
    test_suite.addTest(unittest.makeSuite(DimonProcessTest))
    return test_suite

