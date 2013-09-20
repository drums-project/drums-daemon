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
import logging

from dimon._common import *
from pprint import pprint

class BasicTask(TaskBase):
    def __init__(self, result_queue, default_interval):
        TaskBase.__init__(self, result_queue, default_interval)

    def register_task_core(self, task):
        self.task_map[task] = 0
        return ERR_SUCCESS

    def remove_task_core(self, task):
        try:
            del self.task_map[task]
            return ERR_SUCCESS
        except KeyError:
            return ERR_NOTFOUND

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
        task.start()
        task.register_task('t1')
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
            task.flush_result_queue()
            d = q.get()
            self.assertEqual(len(d), 1)
        finally:
            task.set_terminate_event()
            task.join()

from dimon._process import ProcessMonitor
from psutil import Process
class ProcessTaskTest(unittest.TestCase):
    def test_process_creation(self):
        q = Queue()
        task = ProcessMonitor(q, 0.1)
        task.start()

        pid = os.getpid()
        task.register_task(pid)
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
            task.set_terminate_event()
            task.join()

from dimon._host import HostMonitor
import psutil
class HostTaskTest(unittest.TestCase):
    def test_host_creation(self):
        q = Queue()
        task = HostMonitor(q, 0.1)
        task.start()
        task.register_task(None)
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
            task.set_terminate_event()
            task.join()

from dimon._sock import SocketMonitor
import subprocess

class SocketTaskTest(unittest.TestCase):
    def setUp(self):
        self.p_list = list()
        # write socket for this as well
        #self.null = open(os.devnull, 'w')
        #self.p1 = os.pipe()
        #self.p2 = os.pipe()

        cmds = list()
        cmds.append("netcat -l -p 3333 > /dev/null")
        cmds.append("netcat -l -u -p 4444 > /dev/null")
        cmds.append("netcat localhost 3333 < /dev/urandom")
        cmds.append("netcat -u localhost 4444 < /dev/urandom")

        # Process Groups are needed in order to properly kill the netcats running on a spawned shell, from: http://stackoverflow.com/a/4791612/1215297
        for c in cmds:
            self.p_list.append(subprocess.Popen(c, shell=True, preexec_fn=os.setsid))
            time.sleep(0.1)

        # self.p_list.append(subprocess.Popen(["netcat", "-l", "3333"], stdout = self.null, stderr = self.null))
        # self.p_list.append(subprocess.Popen(["netcat", "3333"], stdin = self.p1, stdout = self.null, stderr = self.null))
        # self.p_list.append(subprocess.Popen(["cat", "/dev/urandom"], stdout = self.p1))

        # self.p_list.append(subprocess.Popen(["netcat", "-ul", "4444"], stdout = self.null, stderr = self.null))
        # self.p_list.append(subprocess.Popen(["netcat", "-u", "3333"], stdin = self.p2, stdout = self.null, stderr = self.null))
        # self.p_list.append(subprocess.Popen(["cat", "/dev/urandom"], stdout = self.p2))

        #time.sleep(0.1)

    def test_socket_basic(self):
        q = Queue()
        task = SocketMonitor(q, 0.5, "lo")
        task.start()

        t1 = ("tcp", "dst", "3333")
        t2 = ("udp", "dst", "4444")
        task.register_task(t2)
        task.register_task(t1)
        # Wait some time until all packets get captured,
        # threaded mode needs more time
        #task.flush_result_queue()

        try:
            try:
                d = q.get(block = True, timeout = 1)
            except Empty:
                self.fail("Socket monitor did not report anything in 1 seconds")
            time.sleep(0.5)
            d = q.get()
            pprint(d)
            byte_count = d['sock']['tcp'][3333]
            #print "Byte Count: %s" % byte_count
            self.assertGreater(byte_count, 1024, "Bytes captured should be greater than 1KiB")

            byte_count = d['sock']['udp'][4444]
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
            task.set_terminate_event()
            task.join()

    def tearDown(self):
        #self.null.close()
        for p in self.p_list:
            os.killpg(p.pid, signal.SIGTERM)

from dimon._latency import LatencyMonitor
class LatencyTaskTest(unittest.TestCase):
    def test_latency_basic(self):
        q = Queue()
        task = LatencyMonitor(q, 1, 5, 0.1)
        task.start()

        task.register_task("127.0.0.1")
        time.sleep(0.1)
        try:
            try:
                d = q.get(block = True, timeout = 5)
            except Empty:
                self.fail("Socket monitor did not report anything in 5 seconds")
            data = d['127.0.0.1']
            self.assertEqual(data['error'], None)
            self.assertGreater(data['avg'], 0)
            self.assertGreater(data['min'], 0)
            self.assertGreaterEqual(data['max'], data['min'])
        finally:
            task.set_terminate_event()
            task.join()

    def test_latency_error(self):
        q = Queue()
        task = LatencyMonitor(q, 1, 5, 0.1)
        task.start()

        invalid_domain = "ksajhdfkjhsadkjfhkdsahfhsdkhfjksdkf.ttt"
        task.register_task(invalid_domain)
        time.sleep(0.1)
        try:
            try:
                d = q.get(block = True, timeout = 5)
            except Empty:
                self.fail("Socket monitor did not report anything in 5 seconds")
            self.assertNotEqual(d[invalid_domain]['error'], None)
        finally:
            task.set_terminate_event()
            task.join()

from dimon import Dimon
class DimonTest(unittest.TestCase):
    def setUp(self):
        self.flag = 0
        self.flag_another = 0
        self.flag_host = 0
        self.flag_sock = 0
        self.flag_late = 0
        self.pid = os.getpid()
        self.d = None

        p = subprocess.Popen(["sleep", "10"])
        self.pid_another = p.pid

        self.p_list = list()

        cmds = list()
        cmds.append("netcat -l -p 3333 > /dev/null")
        cmds.append("netcat localhost 3333 < /dev/urandom")

        for c in cmds:
            self.p_list.append(subprocess.Popen(c, shell=True, preexec_fn=os.setsid))
            time.sleep(0.1)

        self.d = Dimon(process_interval = 0.1, host_interval = 0.5, socket_interval = 0.2, late_interval = 1, late_pings_per_interval = 5, late_wait_between_pings = 0.05)


    def test_dimon_callback(self):
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

        def callback_sock(sock, data):
            self.flag_sock += 1
            self.assertGreater(data['tcp'][3333], 0)

        def callback_late(target, data):
            self.flag_late += 1
            self.assertNotEqual(data['error'], data['avg'])


        self.d.monitor_pid(self.pid, callback)
        self.d.monitor_pid(self.pid_another, callback_another)
        self.d.monitor_host(callback_host)
        self.d.create_monitor_socket(callback_sock)
        self.d.add_socket_to_monitor(('tcp', 'dst', 3333))
        self.d.monitor_target_latency('localhost', callback_late)
        self.d.monitor_target_latency('google.co.jp', callback_late)
        for i in range(20):
            self.d.spin_once()

        #print self.flag, self.flag_another, self.flag_host
        self.assertGreater(self.flag, 0)
        self.assertGreater(self.flag_another, 0)
        self.assertGreater(self.flag_host, 0)
        self.assertGreater(self.flag_sock, 0)
        self.assertGreater(self.flag_late, 0)
        self.assertGreater(self.flag, self.flag_host, "Host monitor should have been called less than process monitor")
        self.assertGreater(self.flag_sock, self.flag_host, "Host monitor should have been called less than socket monitor")

        time.sleep(0.1)
    def tearDown(self):
        self.d.shutdown()
        os.kill(self.pid_another, signal.SIGKILL)
        for p in self.p_list:
            os.killpg(p.pid, signal.SIGTERM)

def get_suite():
    logging.basicConfig(filename='test.log', level=logging.DEBUG, format='%(asctime)s %(message)s')
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(TaskBaseTest))
    test_suite.addTest(unittest.makeSuite(ProcessTaskTest))
    test_suite.addTest(unittest.makeSuite(HostTaskTest))
    test_suite.addTest(unittest.makeSuite(SocketTaskTest))
    test_suite.addTest(unittest.makeSuite(LatencyTaskTest))
    test_suite.addTest(unittest.makeSuite(DimonTest))
    return test_suite

