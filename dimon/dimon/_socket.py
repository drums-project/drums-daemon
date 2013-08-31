# -*- coding: utf-8 -*-

"""
Socket monitoring daemon
"""

from _common import *

import pcapy
from impacket import ImpacktDecoder, ImpacktPacket
from pprint import pprint

"""
string '(tcp/udp) (src/dst) port (port)'
"""

# TODO: regex?
def filter_decode(s):
    t = s.strip().split(" ")
    assert len(t) == 4
    return t


class SocketMonitor(TaskBase):
    def __init__(self, result_queue, default_interval, inet, name = ""):
        TaskBase.__init__(self, result_queue, default_interval, name)

        # TODO: suid
        self.pc = pcapy.open_live(self.inet, 1514, False, 100)
        self.pc.setnonblock(False)

        self.pc.filter = ""
        self.lookup = dict()

    def update_filters(self):
        filters = self.task_map.keys()



    def register_task_core(self, task):
        """
        task_map here contains filter:bytes_count map
        """
        logging.debug("Registering filter %s", (task, ))
        (proto, direction, dummpy, port) = filter_decode(ptask)
        if not proto in self.lookup.keys():
            self.lookup[proto] = dict()
        if not direction in self.lookup[proto].keys():
            self.lookup[proto][direction] = dict()
        self.lookup[proto][direction][port] = 0
        self.task_map[task] = 0
        self.update_filters()

    def remove_task_core(self, task):
        try:
            del self.task_map[task]
        except KeyError:
            logging.warning("Error removing socket filter: %s" % (task,))
        #finally:
        #    self.update_filters()


