# -*- coding: utf-8 -*-

"""
Socket monitoring daemon
"""

from _common import *

import pcapy
from impacket import ImpactDecoder, ImpactPacket
from pprint import pprint

"""
The [base] SocektMonitor will maintain a filter  list (of strings). The libpcap
callback will be fired if any packet matches any of filters. There is no
internal book-keeping to determine which part of the filter caused the
callback to fire.
"""

def tasktuple_to_filterstr(task):
    """
    task = (proto, src/dst, port), e.g ("UDP", "dst", 53) or ("TCP", "", 80)
    """
    proto, direction, port = task
    proto = proto.lower()
    direction = direction.lower()
    port = int(port)
    if not proto in ["tcp", "udp"]:
        raise ValueError("[in %s] Protocol %s not supported." % (self, proto))

    if not direction in ["src", "dst", ""]:
        raise ValueError("[in %s] Direction %s not supported." % (self, direction))

    if not port > 0:
        raise ValueError("[in %s] Invalid port number %s" % (self, port))

    return (proto, direction, port, "%s %s port %s" % (proto, direction, port))

def populate_data(data, port, len):
    if port in data:
        data[port] += len
    #else:
    #    data[port] = len

class SocketMonitor(TaskBase):
    def __init__(self, result_queue, default_interval, inet, name = ""):
        TaskBase.__init__(self, result_queue, default_interval, name)
        self.inet = inet

        # TODO: suid
        self.pc = pcapy.open_live(self.inet, 1514, False, 100)
        self.pc.setnonblock(False)

        datalink = self.pc.datalink()
        if pcapy.DLT_EN10MB == datalink:
            self.decoder = ImpactDecoder.EthDecoder()
        elif pcapy.DLT_LINUX_SLL == datalink:
            self.decoder = ImpactDecoder.LinuxSLLDecoder()
        else:
            raise Exception("Datalink type not supported: %s" % datalink)

        self.filter_str = ""
        self.packets_per_callback = 0
        self.data = dict()
        self.data['tcp'] = dict()
        self.data['udp'] = dict()

    def update_filters(self):
        filters = ["(%s)" % (f,) for f in self.task_map.keys()]
        self.filter_str = " or ".join(filters)
        logging.debug("Updating pcap filter to `%s`" % (self.filter_str,))
        print "Setting filter to %s" % self.filter_str
        self.pc.setfilter(self.filter_str)


    def register_task_core(self, task):
        proto, direction, port, filter_str = tasktuple_to_filterstr(task)
        self.task_map[filter_str] = True
        self.data[proto][port] = 0
        self.update_filters()
        return ERR_SUCCESS

    def remove_task_core(self, task):
        try:
            proto, direction, port, filter_str = tasktuple_to_filterstr(task)
            del self.task_map[filter_str]
            del self.data[proto][port]
            self.update_filters()
            return ERR_SUCCESS
        except KeyError:
            logging.error("Error removing socket filter: %s" % (task,))
            return ERR_NOTFOUND

    def do(self):
        # TODO: Check if re-implementing the IMPacket would improve performance
        def process_callback(hdr , packetdata):
            self.packets_per_callback += 1

            #packet_ts = float(hdr.getts()[0]) + float(hdr.getts()[1]) * 1.0e-6

            # getcaplen() is equal to the length of the part of the packet that has been captured, not the total length of the packet, thus should never be used for bw calculation

            packet_len = hdr.getlen()

            # Link layer decoder
            packet = self.decoder.decode(packetdata)
            # Get the higher layer packet (ip:datalink)
            ippacket = packet.child()
            # TCP or UDP?
            tpacket = ippacket.child()
            # It is not possible now to determine which part of the filter string
            # caused the callback to fire. So `tcp dst port 80` or `tcp src port 80`
            # are not distinguishable. The hack here is to cache the port numbers only
            # and see which port address field matches the cached list.
            if isinstance(tpacket, ImpactPacket.TCP):
                populate_data(self.data['tcp'], tpacket.get_th_sport(), packet_len)
                populate_data(self.data['tcp'], tpacket.get_th_dport(), packet_len)
            elif isinstance(tpacket, ImpactPacket.UDP):
                populate_data(self.data['udp'], tpacket.get_uh_sport(), packet_len)
                populate_data(self.data['udp'], tpacket.get_uh_dport(), packet_len)
        if not self.task_map:
            return

        self.packets_per_callback = 0
        # The only non-blocking way I found to work with pcapy
        self.pc.dispatch(0, process_callback)
        self.data['__ppc__'] = self.packets_per_callback

        _data = dict()
        _data['sock'] = self.data
        pprint(_data)
        if self.packets_per_callback > 0:
            try:
                self.result_queue.put(_data)
            except Full:
                logging.error("[in %s] Output queue is full in"
                    % (self, ))
            finally:
                pass#pprint(data)




