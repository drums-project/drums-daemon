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
import signal

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

from dimon._sock import SocketMonitor
import subprocess
import socket

class SocketTaskTest(unittest.TestCase):
    def setUp(self):
        self.p_list = list()
        # write socket for this as well
        self.null = open(os.devnull, 'w')
        self.p_list.append(subprocess.Popen(["netcat", "-l", "3333"], stdout = self.null, stderr = self.null))
        self.p_list.append(subprocess.Popen(["netcat", "-ul", "4444"], stdout = self.null, stderr = self.null))
        time.sleep(0.1)
        self.s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s1.connect(("localhost", 3333))
        self.s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s2.connect(("localhost", 4444))

    def test_socket_basic(self):
        q = Queue()
        task = SocketMonitor(q, 0.5, "lo")
        t1 = ("tcp", "", "3333")
        t2 = ("udp", "", "4444")
        task.register_task(t2)
        task.register_task(t1)
        task.start()
        dummy = "m" * 1024
        self.s1.sendall(dummy)
        self.s2.sendall(dummy)

        # Wait some time until all packets get captured
        task.flush_result_queue()
        time.sleep(0.5)
        try:
            try:
                d = q.get(block = True, timeout = 1)
            except Empty:
                self.fail("Socket monitor did not report anything in 1 seconds")

            pprint(d)
            byte_count = d['tcp'][3333]
            #print "Byte Count: %s" % byte_count
            self.assertGreater(byte_count, 1024, "Bytes captured should be greater than 1KiB")

            byte_count = d['udp'][4444]
            #print "Byte Count: %s" % byte_count
            self.assertGreater(byte_count, 1024, "Bytes captured should be greater than 1KiB")

            task.remove_task(t1)
            task.remove_task(t2)
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

    def tearDown(self):
        self.null.close()
        self.s1.close()
        self.s2.close()
        for p in self.p_list:
            p.terminate()


from dimon import Dimon
class DimonTest(unittest.TestCase):
    def setUp(self):
        self.flag = 0
        self.flag_another = 0
        self.flag_host = 0
        self.pid = os.getpid()
        self.d = None
        p = subprocess.Popen(["sleep", "10"])
        self.pid_another = p.pid

    def test_dimon_pids_callback(self):
        def callback(pid, data):
            self.flag += 1
            self.assertEqual(pid, self.pid)
            threads = data['get_threads']
            mem = data['get_memory_info']['rss']
            name = data['name']
            self.assertGreater(len(threads), 0, "Testing number of threads")
            self.assertGreater(mem, 0, "Testing memory")
            self.assertEqual(name, "python", "Testing app name")

        def callback_another(pid, data):
            self.flag_another += 1
            self.assertEqual(pid, self.pid_another)

        def callback_host(host, data):
            self.flag_host += 1
            self.assertGreater(data['swap_memory']['free'], 0)

        self.d = Dimon(process_interval = 0.1, host_interval = 0.5)
        self.d.monitor_pid(self.pid, callback)
        self.d.monitor_pid(self.pid_another, callback_another)
        self.d.monitor_host(callback_host)
        for i in range(20):
            self.d.spin_once()

        #print self.flag, self.flag_another, self.flag_host
        self.assertGreater(self.flag, 0)
        self.assertGreater(self.flag_another, 0)
        self.assertGreater(self.flag_host, 0)
        self.assertGreater(self.flag, self.flag_host, "Host monitor should have been called less than process monitor")

    def tearDown(self):
        self.d.shutdown()
        os.kill(self.pid_another, signal.SIGKILL)

def get_suite():
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(TaskBaseTest))
    test_suite.addTest(unittest.makeSuite(ProcessTaskTest))
    test_suite.addTest(unittest.makeSuite(HostTaskTest))
    test_suite.addTest(unittest.makeSuite(SocketTaskTest))
    test_suite.addTest(unittest.makeSuite(DimonTest))
    return test_suite

