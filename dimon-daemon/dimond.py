# -*- coding: utf-8 -*-

__version__ = "0.1.0"
__api__ = "1.0"

version_info = tuple([int(num) for num in __version__.split('.')])


import logging
import re
from threading import Thread, current_thread

import bottle
import zmq
import msgpack

from dimon import Dimon, DimonError
from pprint import pprint

__err_map = {
    DimonError.SUCCESS: 200,
    DimonError.NOTFOUND: 404,
    DimonError.ACCESSDENIED: 403,
    DimonError.RUNTIME: 406,
    DimonError.UNEXPECTED: 500
}

def http_response(err):
    bottle.response.status = __err_map.get(err, 400)

class DimonDaemon(object):
    def __init__(self, config = dict(), debug = None):
        self.config = config
        self.dimon = Dimon(
            process_interval = self.config.get('process_interval', 1.0),
            host_interval = self.config.get('host_interval', 1.0),
            socket_interval = self.config.get('socket_interval', 1.0),
            late_interval = self.config.get('late_interval', 1.0),
            late_pings_per_interval = self.config.get('late_pings_per_interval', 5),
            late_wait_between_pings = self.config.get("late_wait_between_pings", 0.1),
            process_fields = self.config.get("process_fields", list()),
            host_fields = self.config.get("host_fields", list()))

        logging.info("Dimon and Bottle initialized")
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.PUB)
        self.zmq_addr = "tcp://*:" + str(self.config.get('publish_port', 8002))
        self.sock.bind(self.zmq_addr)
        self.loop_counter = 0

        self.__host_regex = re.compile("(?=^.{1,254}$)(^(?:(?!\d|-)[a-zA-Z0-9\-]{1,63}(?<!-)\.?)+(?:[a-zA-Z]{2,})$)")
        self.__ip_regex = re.compile("^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")

    def loop(self):
        while True:
            self.loop_counter += 1
            print ">>> loop ", self.loop_counter
            try:
                # This is a blocking call
                self.dimon.spin_once()
            except KeyboardInterrupt:
                logging.info("Shutting down dimon ...")
                self.dimon.shutdown()
                return True

    def _callback_pid(self, pid, data):
        #pprint(data)
        self.sock.send(msgpack.dumps({'type': 'pid', 'key' : pid, 'data' : data}))

    def _callback_host(self, host, data):
        self.sock.send(msgpack.dumps({'type': 'host', 'key' : 'host', 'data' : data}))

    def _callback_latency(self, target, data):
        self.sock.send(msgpack.dumps({'type': 'latency', 'key' : target, 'data' : data}))

    # Data is not fine-grained per filter
    def _callback_sock(self, sock, data):
        self.sock.send(msgpack.dumps({'type': 'socket', 'key' : 'socket', 'data' : data}))

    # These are called in Bottle thread's context
    def get_info(self):
        return {"name": "Dimon Daemon",
                "version": __version__,
                "api_version": __api__,
                "zmq_publish": self.zmq_addr}

    def add_pid(self, pid):
        http_response(self.dimon.monitor_pid(pid, self._callback_pid))

    def remove_pid(self, pid):
        http_response(self.dimon.remove_pid(pid))

    def enable_host(self):
        http_response(self.dimon.monitor_host(self._callback_host))

    def disable_host(self):
        http_response(self.dimon.remove_host())

    def add_latency(self, target):
        if self.__host_regex.match(target) or self.__ip_regex.match(target):
            http_response(self.dimon.monitor_target_latency(target, self._callback_latency))
        else:
            http_response(DimonError.NOTFOUND)

    def remove_latency(self, target):
        if self.__host_regex.match(target) or self.__ip_regex.match(target):
            http_response(self.dimon.remove_target_latency(target))
        else:
            http_response(DimonError.NOTFOUND)

    def add_socket(self, proto, direction, port):
        # This will happen if necessary
        res = self.dimon.create_monitor_socket(self._callback_sock)
        if  res == DimonError.SUCCESS:
            if direction == "bi":
                direction = ""
            http_response(self.dimon.add_socket_to_monitor((proto, direction, port)))
        else:
            http_response(res)

    def remove_socket(self, proto, direction, port):
        if direction == "bi":
                direction = ""
        http_response(self.dimon.remove_socket((proto, direction, port)))

if __name__ == "__main__":
    config = dict()

    # TODO: Level
    logging.basicConfig(filename=config.get('logfile', 'dimond.log'), level=logging.DEBUG, format='%(asctime)s %(message)s')
    rp = "/dimon/api/%s" % (__api__,)

    logging.info("Starting dimon-daemon.")
    app = DimonDaemon(config)

    ### Routes
    bottle.debug(True)
    bottle.route(rp + "/info", "GET", app.get_info)
    bottle.route(rp + "/monitor/pid/<pid:int>", "POST", app.add_pid)
    bottle.route(rp + "/monitor/pid/<pid:int>", "DELETE", app.remove_pid)
    bottle.route(rp + "/monitor/host", "POST", app.enable_host)
    bottle.route(rp + "/monitor/host", "DELETE", app.disable_host)
    bottle.route(rp + "/monitor/latency/<target>", "POST", app.add_latency)
    bottle.route(rp + "/monitor/latency/<target>", "DELETE", app.remove_latency)
    bottle.route(rp + "/monitor/socket/<proto:re:tcp|udp>/<direction:re:bi|src|dst>/<port:int>", "POST", app.add_socket)
    bottle.route(rp + "/monitor/socket/<proto:re:tcp|udp>/<direction:re:bi|src|dst>/<port:int>", "DELETE", app.remove_socket)
    #bottle.route(rp + "/monitor/latency/<target>", "DELETE", app.remove_socket)

    server = Thread(target = bottle.run, kwargs = {'host': config.get("host", "localhost"), 'port': config.get("port", 8001)})
    server.daemon = True;
    server.start()
    app.loop()
