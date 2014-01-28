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

from struct import *
from socket import ntohs

__eth_length = 14
__any_length = 16

 #SLL: http://www.tcpdump.org/linktypes/LINKTYPE_LINUX_SLL.html
LINK_LAYER_ETH = 1
LINK_LAYER_SLL = 2

def parse_header(packet, link_layer):
    tcp_sport, tcp_dport, udp_sport, udp_dport = None, None, None, None

    eth_protocol = 0
    if link_layer == LINK_LAYER_ETH:
        pad = __eth_length
        eth_header = packet[0:pad]
        eth = unpack('!6s6sH', eth_header)
        eth_protocol = ntohs(eth[2])
    elif link_layer == LINK_LAYER_SLL:
        pad = __any_length
        any_header = packet[0:pad]
        anyp = unpack("!HHH8sH", any_header)
        eth_protocol = ntohs(anyp[4])
    else:
        raise Exception("Datalink type not supported: %s" % link_layer)

    if eth_protocol == 8:
        ip_header = packet[pad:20+pad]
        iph = unpack('!BBHHHBBH4s4s', ip_header)
        version_ihl = iph[0]
        #version = version_ihl >> 4
        ihl = version_ihl & 0xF
        iph_length = ihl * 4
        #ttl = iph[5]
        protocol = iph[6]
        #s_addr = socket.inet_ntoa(iph[8]);
        #d_addr = socket.inet_ntoa(iph[9]);
        if protocol == 6:
            t = iph_length + pad
            tcp_header = packet[t:t+20]
            tcph = unpack('!HHLLBBHHH' , tcp_header)
            tcp_sport = tcph[0]
            tcp_dport = tcph[1]
            #sequence = tcph[2]
            #acknowledgement = tcph[3]
            #doff_reserved = tcph[4]
            #tcph_length = doff_reserved >> 4
        elif protocol == 17:
            u = iph_length + pad
            #udph_length = 8
            udp_header = packet[u:u+8]
            udph = unpack('!HHHH', udp_header)

            udp_sport = udph[0]
            udp_dport = udph[1]
            #length = udph[2]
            #checksum = udph[3]

    return tcp_sport, tcp_dport, udp_sport, udp_dport

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
    def __init__(self, result_queue, default_interval, inet, name="dimon_sockmonitor"):
        TaskBase.__init__(self, result_queue, default_interval, name)
        self.inet = inet

        # TODO: suid
        # TODO: Find good values for to_ms
        self.pc = pcapy.open_live(self.inet, 100, False, 900)
        self.pc.setnonblock(False)

        datalink = self.pc.datalink()
        if pcapy.DLT_EN10MB == datalink:
            self.link_layer = LINK_LAYER_ETH # Ethernet
        elif pcapy.DLT_LINUX_SLL == datalink:
            self.link_layer = LINK_LAYER_SLL # Any
        else:
            raise Exception("Datalink type not supported: %s" % datalink)

        logging.info("Datalink is : %d", self.link_layer)
        self.filter_str = ""
        self.packets_per_callback = 0
        self.data = dict()
        self.data['tcp'] = dict()
        self.data['udp'] = dict()

        self.meta = dict()
        self.meta['tcp'] = dict()
        self.meta['udp'] = dict()

    def update_filters(self):
        filters = ["(%s)" % (f,) for f in self.task_map.keys()]
        self.filter_str = " or ".join(filters)
        logging.debug("Updating pcap filter to `%s`" % (self.filter_str,))
        #print "Setting filter to %s" % self.filter_str
        self.pc.setfilter(self.filter_str)


    def register_task_core(self, task, meta=''):
        assert isinstance(meta, basestring)
        proto, direction, port, filter_str = tasktuple_to_filterstr(task)
        port = str(port)
        self.task_map[filter_str] = True
        if not port in self.meta[proto]:
            self.meta[proto][port] = set()
            self.data[proto][port] = 0

        if meta:
            self.meta[proto][port].add(meta)
        self.update_filters()
        return DimonError.SUCCESS

    def remove_task_core(self, task, meta=''):
        try:
            proto, direction, port, filter_str = tasktuple_to_filterstr(task)
            # Empty meta will delete all data
            if meta:
                self.meta[proto][str(port)].remove(meta)
            if not self.meta[proto][str(port)] or not meta:
                del self.task_map[filter_str]
                del self.data[proto][str(port)]
                del self.meta[proto][str(port)]
                self.update_filters()
            return DimonError.SUCCESS
        except KeyError:
            logging.error("Error removing socket filter: %s" % (task,))
            return DimonError.NOTFOUND

    def do(self):
        # TODO: Check if re-implementing the IMPacket would improve performance
        def process_callback(hdr, packetdata):
            self.packets_per_callback += 1

            #packet_ts = float(hdr.getts()[0]) + float(hdr.getts()[1]) * 1.0e-6

            # getcaplen() is equal to the length of the part of the packet that has been captured, not the total length of the packet, thus should never be used for bw calculation

            packet_len = hdr.getlen()

                #print "-" * 10, packet_len
            tcp_sport, tcp_dport, udp_sport, udp_dport = parse_header(packetdata, self.link_layer)
            if tcp_sport and tcp_dport:
                populate_data(self.data['tcp'], str(tcp_sport), packet_len)
                populate_data(self.data['tcp'], str(tcp_dport), packet_len)
            elif udp_sport and udp_dport:
                populate_data(self.data['udp'], str(udp_sport), packet_len)
                populate_data(self.data['udp'], str(udp_dport), packet_len)
            else:
                logging.warning("Parse Header failed for packet.")
            # Link layer decoder
            #packet = self.decoder.decode(packetdata)
            #return
            # Get the higher layer packet (ip:datalink)
            #ippacket = packet.child()
            # TCP or UDP?
            #tpacket = ippacket.child()
            # It is not possible now to determine which part of the filter string
            # caused the callback to fire. So `tcp dst port 80` or `tcp src port 80`
            # are not distinguishable. The hack here is to cache the port numbers only
            # and see which port address field matches the cached list.
            #if isinstance(tpacket, ImpactPacket.TCP):
                #pass
                #populate_data(self.data['tcp'], str(tpacket.get_th_sport()), packet_len)
                #populate_data(self.data['tcp'], str(tpacket.get_th_dport()), packet_len)
            #elif isinstance(tpacket, ImpactPacket.UDP):
                #pass
                #populate_data(self.data['udp'], str(tpacket.get_uh_sport()), packet_len)
                #populate_data(self.data['udp'], str(tpacket.get_uh_dport()), packet_len)

        if not self.task_map:
            return

        self.packets_per_callback = 0
        # The only non-blocking way I found to work with pcapy
        self.pc.dispatch(0, process_callback)
        logging.info("packets per callback: %d" % (self.packets_per_callback, ))

        _data = dict()
        #_data['__ppc__'] = self.packets_per_callback
        timestamp = time.time()
        #_data = dict()
        #_data['sock'] = self.data
        #_data['meta'] = self.meta
        #pprint(_data)
        # TODO: The first packet should be sent (0, 0, ...)
        if self.packets_per_callback > 0:
            for proto in ['tcp', 'udp']:
                for port, bytes in self.data[proto].items():
                    _key = "%s:%s" % (proto, port)
                    _data[_key] = {'timestamp': timestamp, 'bytes': bytes, 'meta': list(self.meta[proto][port])}
            try:
                self.result_queue.put(_data)
            except Full:
                logging.error("[in %s] Output queue is full in"
                    % (self, ))
            finally:
                pass#pprint(data)



