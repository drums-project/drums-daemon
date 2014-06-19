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
Latency monitoring daemon
"""

from _common import *
from _ping import *

import socket

"""
The [base] LatencyMonitor. For now, each instance will monitor only one other
host/ip using python-ping library. It is possible to do all pings in one
thread/process/coroutine though.
"""


class LatencyMonitor(TaskBase):
    def __init__(
            self, result_queue, default_interval, pings_per_interval,
            wait_between_pings=0.1, name="drums_latencymonitor"):
        TaskBase.__init__(self, result_queue, default_interval, name)
        self.pings_per_interval = pings_per_interval
        self.target = None
        self.wait_between_pings = wait_between_pings

    # TODO: This is not thread safe
    def set_options(self, pings_per_interval, wait_between_pings):
        self.pings_per_interval = pings_per_interval
        self.wait_between_pings = wait_between_pings

    def register_task_core(self, task, meta=''):
        assert isinstance(meta, basestring)
        self.target = (task, meta)
        return DrumsError.SUCCESS

    def remove_task_core(self, task, meta=''):
        self.target = None
        return DrumsError.SUCCESS

    def do(self):
        if not self.target:
            return

        # from `quiet_ping`
        mxrtt = None
        mnrtt = None
        artt = None
        err = None  # This holds only last error
        plist = []

        sent = success = 0
        for i in xrange(self.pings_per_interval):
            sent += 1
            try:
                delay = do_one(self.target[0], timeout=2, psize=64)
                success += 1
            except socket.error, msg:
                err = msg[0]
                continue

            if delay is not None:
                plist.append(delay)

            time.sleep(self.wait_between_pings)

        # Find max and avg round trip time
        if plist:
            mnrtt = min(plist)
            mxrtt = max(plist)
            artt = sum(plist) / len(plist)

        dummy = dict()
        dummy['sent'] = sent
        dummy['loss'] = sent - success
        dummy['avg'] = artt
        dummy['max'] = mxrtt
        dummy['min'] = mnrtt
        dummy['error'] = err
        dummy['timestamp'] = time.time()
        dummy['meta'] = self.target[1]
        data = dict()
        data[self.target[0]] = dummy

        if data:
            try:
                self.result_queue.put(data)
            except Queue.Full:
                self.logger.error(
                    "[in %s] Output queue is full in" % (self, ))
            finally:
                pass
