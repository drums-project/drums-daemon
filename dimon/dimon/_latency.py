# -*- coding: utf-8 -*-

"""
Latency monitoring daemon
"""

from _common import *

import ping
from pprint import pprint

"""
The [base] LatencyMonitor. For now, each instance will monitor only one other
host/ip using python-ping library. It is possible to do all pings in one
thread/process/coroutine though.
"""

class LatencyMonitor(TaskBase):
    def __init__(self, result_queue, default_interval, pings_per_interval, wait_between_pings = 0.1, name = ""):
        TaskBase.__init__(self, result_queue, default_interval, name)
        self.inet = inet
        self.pings_per_interval = pings_per_interval
        self.target = None
        self.wait_between_pings = wait_between_pings

    def register_task_core(self, task):
        self.target = task

    def remove_task_core(self, task):
        self.target = None

    def do(self):
        if not self.target:
            return

        # from `quiet_ping`
        mrtt = None
        artt = None
        err = None # This holds only last error
        plist = []

        sent = success = 0
        for i in xrange(self.pings_per_interval):
            sent += 1
            try:
                delay = do_one(self.target, timeout = 2, psize = 64)
                success += 1
            except socket.gaierror, e:
                err = e[1]
                continue

            if delay != None:
                plist.append(delay)

            time.sleep(self.wait_between_pings)

        # Find max and avg round trip time
        if plist:
            mnrtt = min(plist)
            mxrtt = max(plist)
            artt = sum(plist) / len(plist)

        dummy = dict()
        dummy['sent'] = sent
        dummy['loss'] = sent - count
        dummy['avg'] = artt
        dummy['max'] = mxrtt
        dummy['min'] = mnrtt
        data['latency'] = dict()
        data['latency'][self.target] = dummy

        if data:
            try:
                self.result_queue.put(data)
            except Queue.Full:
                logging.error("[in %s] Output queue is full in"
                    % (self, ))
            finally:
                pass#pprint(data)
