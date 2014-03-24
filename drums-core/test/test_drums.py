#!/usr/bin/env python
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

try:
    import unittest2 as unittest  # pyhon < 2.7 + unittest2 installed
except ImportError:
    import unittest

import time
import os
import sys
import signal
import logging

from drums._common import *
from pprint import pprint


class BasicTask(TaskBase):
    def __init__(self, result_queue, default_interval):
        TaskBase.__init__(self, result_queue, default_interval)

    def register_task_core(self, task, meta=''):
        self.task_map[task] = (0, meta)
        return DrumsError.SUCCESS

    def remove_task_core(self, task, meta=''):
        try:
            del self.task_map[task]
            return DrumsError.SUCCESS
        except KeyError:
            return DrumsError.NOTFOUND

    def do(self):
        if self.task_map:
            sys.stdout.write('>')
            sys.stdout.flush()
            self.task_map = {
                key: (val+1, meta) for
                key, (val, meta) in self.task_map.items()}
            #if self.result_queue.empty():
            #pprint(self.task_map)
            self.result_queue.put(self.task_map)


class TaskBaseTest(unittest.TestCase):
    def test_basic_task_loop(self):
        q = Queue()
        meta = 'dummytask'
        task = BasicTask(q, 0.1)
        task.start()
        self.assertEqual(task.register_task('t1', meta), DrumsError.SUCCESS)
        try:
            time.sleep(0.25)
            d = q.get()
            task.flush_result_queue()
            self.assertEqual(len(d), 1)
            self.assertEqual(task.register_task('t2'), DrumsError.SUCCESS)
            time.sleep(0.25)
            d = q.get()
            task.flush_result_queue()
            self.assertEqual(len(d), 2)
            time.sleep(0.5)
            d = q.get()
            task.flush_result_queue()
            self.assertGreater(d['t1'][0], 0)
            self.assertGreater(d['t2'][0], 0)
            self.assertEqual(d['t1'][1], meta)
            self.assertEqual(d['t2'][1], '')
            task.remove_task('t2')
            time.sleep(0.1)
            task.flush_result_queue()
            d = q.get()
            self.assertEqual(len(d), 1)
        finally:
            task.set_terminate_event()
            task.join()

from drums._process import ProcessMonitor


class ProcessTaskTest(unittest.TestCase):
    def test_process_creation(self):
        q = Queue()
        _name = 'dummy'
        task = ProcessMonitor(q, 0.1, _name)
        task.start()
        meta = 'myself'
        #TODO: Why does the following return's the subprocess PID?
        pid = os.getpid()
        self.assertEqual(task.register_task(pid, meta), DrumsError.SUCCESS)
        time.sleep(0.1)
        try:
            try:
                d = q.get(block=True, timeout=1)
            except Empty:
                self.fail(
                    "Process monitor did not report anything in 1 seconds")
            threads = d[pid]['get_threads']
            mem = d[pid]['get_memory_info']['rss']
            #name = d[pid]['name']
            getmeta = d[pid]['meta']
            self.assertGreater(len(threads), 0, "Testing number of threads")
            self.assertGreater(mem, 0, "Testing memory")
            #self.assertEqual(name, _name, "Testing app name")
            self.assertEqual(meta, getmeta)
            task.remove_task(pid)
            task.flush_result_queue()
            time.sleep(0.1)
            # The task list is empty, no update should be done
            #self.assertRaises(Queue.Empty, task.result_queue.get(), 1)
            try:
                d = q.get(block=True, timeout=0.1)
                self.fail(
                    "No data should be put into the queue when task \
                    map is empty.")
            except Empty:
                pass

        finally:
            task.set_terminate_event()
            task.join()

from drums._host import HostMonitor


class HostTaskTest(unittest.TestCase):
    def test_host_creation(self):
        q = Queue()
        task = HostMonitor(q, 0.1)
        task.start()
        meta = 'hostishu'
        self.assertEqual(task.register_task(None, meta), DrumsError.SUCCESS)
        time.sleep(0.1)
        try:
            try:
                d = q.get(block=True, timeout=1)
            except Empty:
                self.fail("Host monitor did not report anything in 1 seconds")
            #pprint(d)
            net_count = d['host']['net_io_counters']
            vm = d['host']['virtual_memory']
            self.assertGreater(len(net_count), 0, "net_io_counter type test")
            self.assertGreater(vm['active'], 0)
            self.assertEqual(d['host']['meta'], meta)
            task.remove_task('host')
            task.flush_result_queue()
            time.sleep(0.25)
            # The task list is empty, no update should be done
            #self.assertRaises(Queue.Empty, task.result_queue.get(), 1)
            try:
                d = q.get(block=True, timeout=0.25)
                self.fail(
                    "No data should be put into the queue when task \
                    map is empty.")
            except Empty:
                pass

        finally:
            task.set_terminate_event()
            task.join()

from drums._sock import SocketMonitor
import subprocess


class SocketTaskTest(unittest.TestCase):
    def setUp(self):
        self.p_list = list()
        # write socket for this as well
        #self.null = open(os.devnull, 'w')
        #self.p1 = os.pipe()
        #self.p2 = os.pipe()

        cmds = list()
        cmds.append("nc -l 3333 > /dev/null")
        cmds.append("nc -l -u 4444 > /dev/null")
        cmds.append("nc localhost 3333 < /dev/urandom")
        cmds.append("nc -u localhost 4444 < /dev/urandom")

        # Process Groups are needed in order to properly kill
        # the netcats running on a spawned shell
        # from: http://stackoverflow.com/a/4791612/1215297
        for c in cmds:
            self.p_list.append(
                subprocess.Popen(c, shell=True, preexec_fn=os.setsid))
            time.sleep(0.1)

    def test_socket_basic(self):
        q = Queue()
        task = SocketMonitor(q, 1.0, "lo")
        task.start()

        t1 = ("tcp", "dst", "3333")
        t2 = ("udp", "dst", "4444")
        meta1 = 'nc'
        meta2 = 'dummy'
        self.assertEqual(task.register_task(t2, meta2), DrumsError.SUCCESS)
        self.assertEqual(task.register_task(t1, meta1), DrumsError.SUCCESS)
        # Wait some time until all packets get captured,
        # threaded mode needs more time
        #task.flush_result_queue()

        try:
            try:
                d = q.get(block=True, timeout=2)
            except Empty:
                self.fail("Socket monitor did not report anything in 2 seconds")
            time.sleep(0.5)
            d = q.get()
            pprint(d)
            byte_count = d['tcp:3333']['bytes']
            #print "Byte Count: %s" % byte_count
            self.assertGreater(
                byte_count, 1024,
                "Bytes captured should be greater than 1KiB")

            byte_count = d['udp:4444']['bytes']
            #print "Byte Count: %s" % byte_count
            self.assertGreater(
                byte_count, 1024,
                "Bytes captured should be greater than 1KiB")

            self.assertEquals(len(d['tcp:3333']['meta']), 1)
            self.assertEquals(len(d['udp:4444']['meta']), 1)
            self.assertEqual(d['tcp:3333']['meta'][0], meta1)
            self.assertEqual(d['udp:4444']['meta'][0], meta2)
            task.remove_task(t1)
            task.remove_task(t2)
            task.flush_result_queue()
            time.sleep(0.25)
            # The task list is empty, no update should be done
            #self.assertRaises(Queue.Empty, task.result_queue.get(), 1)
            try:
                d = q.get(block=True, timeout=0.25)
                self.fail(
                    "No data should be put into the queue when \
                    task map is empty.")
            except Empty:
                pass

        finally:
            task.set_terminate_event()
            task.join()

    def tearDown(self):
        #self.null.close()
        for p in self.p_list:
            os.killpg(p.pid, signal.SIGTERM)

from drums._latency import LatencyMonitor


class LatencyTaskTest(unittest.TestCase):
    def test_latency_basic(self):
        q = Queue()
        task = LatencyMonitor(q, 1, 5, 0.1)
        task.start()

        meta = "to-localhost"
        self.assertEqual(
            task.register_task("127.0.0.1", meta), DrumsError.SUCCESS)
        time.sleep(0.1)
        try:
            try:
                d = q.get(block=True, timeout=5)
            except Empty:
                self.fail("Socket monitor did not report anything in 5 seconds")
            data = d['127.0.0.1']
            self.assertEqual(data['meta'], meta)
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
                d = q.get(block=True, timeout=5)
            except Empty:
                self.fail(
                    "Latency monitor did not report anything in 5 seconds")
            self.assertNotEqual(d[invalid_domain]['error'], None)
        finally:
            task.set_terminate_event()
            task.join()


def _sr(s):
    """
    reverse a string
    """
    return s[::-1]

from drums import Drums


class DrumsTest(unittest.TestCase):
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
        cmds.append("nc -l 3333 > /dev/null")
        cmds.append("nc localhost 3333 < /dev/urandom")

        for c in cmds:
            self.p_list.append(
                subprocess.Popen(c, shell=True, preexec_fn=os.setsid))
            time.sleep(0.1)

        self.d = Drums(
            process_interval=0.5,
            host_interval=1.5,
            socket_interval=1.0,
            late_interval=1.0,
            late_pings_per_interval=5,
            late_wait_between_pings=0.05)
        self.d.init()

    def callback(self, pid, data):
        self.flag += 1
        self.assertEqual(pid, self.pid)
        threads = data['get_threads']
        mem = data['get_memory_info']['rss']
        #name = data['name']
        self.assertGreater(len(threads), 0, "Testing number of threads")
        self.assertGreater(mem, 0, "Testing memory")
        #self.assertEqual(name, "python", "Testing app name")

    def callback_another(self, pid, data):
        self.flag_another += 1
        self.assertEqual(pid, self.pid_another)
        self.assertEqual(_sr(str(pid)), data['meta'])

    def callback_host(self, host, data):
        self.flag_host += 1
        self.assertGreater(data['swap_memory']['free'], 0)
        self.assertEqual(_sr(host), data['meta'])

    def callback_sock(self, sock, data):
        self.flag_sock += 1
        self.assertGreater(data['bytes'], 0)
        self.assertEqual(_sr(sock) in data['meta'], True)

    def callback_late(self, target, data):
        self.flag_late += 1
        self.assertNotEqual(data['error'], data['avg'])
        self.assertEqual(_sr(target), data['meta'])

    def test_drums_callback(self):
        # The _sr is used to reverse the key before sending that as meta
        # This equality will be checked in callbacks to test if meta
        # is being transmitted back OK.
        self.d.monitor_pid(
            self.pid, self.callback,
            _sr(str(self.pid)))  # Reverse
        self.d.monitor_pid(
            self.pid_another, self.callback_another,
            _sr(str(self.pid_another)))
        self.d.monitor_host(self.callback_host, _sr('host'))
        self.d.monitor_socket(
            ('tcp', 'dst', '3333'),
            self.callback_sock, _sr('tcp:3333'))
        self.d.monitor_target_latency(
            'localhost', self.callback_late, _sr('localhost'))
        self.d.monitor_target_latency(
            'google.co.jp', self.callback_late, _sr('google.co.jp'))

        print "Waiting some 5 seconds ..."
        time.sleep(5)

        #print self.flag, self.flag_another, self.flag_host
        self.assertGreater(self.flag, 0)
        self.assertGreater(self.flag_another, 0)
        self.assertGreater(self.flag_host, 0)
        self.assertGreater(self.flag_sock, 0)
        self.assertGreater(self.flag_late, 0)
        self.assertGreater(
            self.flag, self.flag_host,
            "Host monitor should have been called less than process monitor")
        self.assertGreater(
            self.flag_sock, self.flag_host,
            "Host monitor should have been called less than socket monitor")

        time.sleep(0.1)

    def tearDown(self):
        self.d.shutdown()
        os.kill(self.pid_another, signal.SIGKILL)
        for p in self.p_list:
            os.killpg(p.pid, signal.SIGTERM)


def get_suite():
    logging.basicConfig(
        filename='test.log', level=logging.DEBUG,
        format='[%(asctime)s] [%(levelname)s] (%(name)s) %(message)s')
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(TaskBaseTest))
    test_suite.addTest(unittest.makeSuite(ProcessTaskTest))
    test_suite.addTest(unittest.makeSuite(HostTaskTest))
    test_suite.addTest(unittest.makeSuite(SocketTaskTest))
    test_suite.addTest(unittest.makeSuite(LatencyTaskTest))
    test_suite.addTest(unittest.makeSuite(DrumsTest))
    return test_suite
