# -*- coding: utf-8 -*-

__version__ = "0.1.0"
# Who needs precision for API version?
__api__ = "1"

version_info = tuple([int(num) for num in __version__.split('.')])


import logging
import re
from threading import Thread, Lock
from copy import copy

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


# Fine-grained thread safe cache for on-demand data
class MsgpackSafeCache:
    def __init__(self):
        self.index = dict()
        self.caches = dict()
        self.locks = dict()
        self.index_lock = Lock()

    def _key(self, _type, key):
        return str(_type) + str(key)

    def remove_key(self, _type, key):
        k = self._key(_type, key)
        with self.index_lock:
            try:
                del self.index[k]
                del self.locks[k]
                del self.caches[k]
            except KeyError:
                return False
        return True

    def put(self, _type, key, data):
        k = self._key(_type, key)
        with self.index_lock:
            if not k in self.index:
                self.index[k] = True
                self.locks[k] = Lock()
                self.caches[k] = dict()

        with self.locks[k]:
            self.caches[k] = copy(data)

    # returns json
    def get(self, _type, key, key_path = None):
        k = self._key(_type, key)
        with self.index_lock:
            if not k in self.index:
                return None

        with self.locks[k]:
            if not key_path:
                # TODO: Should we do an extra copy?
                return msgpack.loads(self.caches[k])
            else:
                path = key_path.split('/')
                # Hard limit to avoid nasty lengthy requests
                if len(path) > 7 or len(path) < 1:
                    return None
                else:
                    cached = msgpack.loads(self.caches[k])
                    data = dict()
                    data['type'] = cached['type']+'/'+ key_path
                    data['key'] = cached['key']
                    data['timestamp'] = cached['data'].get('timestamp', None)

                    d = cached['data']
                    for segment in path:
                        if segment in d:
                            d = d[segment]
                        else:
                            # Path does not exists
                            return None
                    data['data'] = d
                    return copy(data)



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


        self.cache_socket = MsgpackSafeCache()
        self.cache_host = MsgpackSafeCache()
        self.cache_latency = MsgpackSafeCache()
        self.cache_pid = MsgpackSafeCache()

    def loop(self):
        while True:
            self.loop_counter += 1
            #print ">>> loop ", self.loop_counter
            try:
                # This is a blocking call
                self.dimon.spin_once()
            except KeyboardInterrupt:
                logging.info("Shutting down dimon ...")
                self.dimon.shutdown()
                return True

    def _callback_pid(self, pid, data):
        #pprint(data)
        d = msgpack.dumps({'type': 'pid', 'key' : pid, 'data' : data})
        self.sock.send(d)
        self.cache_pid.put('pid', pid, d)

    def _callback_host(self, host, data):
        d = msgpack.dumps({'type': 'host', 'key' : 'host', 'data' : data})
        self.sock.send(d)
        self.cache_host.put('host', 'host', d)

    def _callback_latency(self, target, data):
        d = msgpack.dumps({'type': 'latency', 'key' : target, 'data' : data})
        self.sock.send(d)
        self.cache_latency.put('latency', target, d)

    # Data is not fine-grained per filter
    def _callback_sock(self, sock, data):
        d = msgpack.dumps({'type': 'socket', 'key' : 'socket', 'data' : data})
        self.sock.send(d)
        self.cache_socket.put('socket', 'socket', d)

    # These are called in Bottle thread's context
    def get_info(self):
        return {"name": "Dimon Daemon",
                "version": __version__,
                "api_version": __api__,
                "zmq_publish": self.zmq_addr}

    def add_pid(self, pid):
        # Cache entry will be created automatically on first callback call
        http_response(self.dimon.monitor_pid(pid, self._callback_pid))

    def remove_pid(self, pid):
        # Cache entry should manually be removed
        self.cache_pid.remove_key('pid', pid)
        http_response(self.dimon.remove_pid(pid))

    def get_pid(self, pid, key_path = None):
        d = self.cache_pid.get('pid', pid, key_path)
        if d:
            return d
        else:
            http_response(DimonError.NOTFOUND)

    def enable_host(self):
        http_response(self.dimon.monitor_host(self._callback_host))

    def disable_host(self):
        http_response(self.dimon.remove_host())

    def get_host(self, key_path = None):
        d = self.cache_host.get('host', 'host', key_path)
        if d:
            return d
        else:
            http_response(DimonError.NOTFOUND)

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

    def get_latency(self, target, key_path = None):
        if not (self.__host_regex.match(target) or self.__ip_regex.match(target)):
            http_response(DimonError.NOTFOUND)
        d = self.cache_latency.get('latency', target, key_path)
        if d:
            return d
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

    def get_socket(self, key_path = None):
        d = self.cache_socket.get('socket', 'socket', key_path)
        if d:
            return d
        else:
            http_response(DimonError.NOTFOUND)

if __name__ == "__main__":
    config = dict()

    # TODO: Level
    logging.basicConfig(filename=config.get('logfile', 'dimond.log'), level=logging.DEBUG, format='%(asctime)s %(message)s')
    rp = "/dimon/v/%s" % (__api__,)

    path_pid_base = rp + "/monitor/pid"
    path_pid = path_pid_base + "/<pid:int>"
    path_host = rp + "/monitor/host"
    path_latency_base = rp + "/monitor/latency"
    path_latency = path_latency_base + "/<target>"
    path_socket_base = rp + "/monitor/socket"
    path_socket = path_socket_base + "/<proto:re:tcp|udp>/<direction:re:bi|src|dst>/<port:int>"

    logging.info("Starting dimon-daemon.")
    app = DimonDaemon(config)

    ### Routes
    bottle.debug(True)
    bottle.route(rp + "/info", "GET", app.get_info)

    bottle.route(path_pid, "POST", app.add_pid)
    bottle.route(path_pid, "DELETE", app.remove_pid)
    bottle.route(path_pid, "GET", app.get_pid)
    bottle.route(path_pid + "/<key_path:path>", "GET", app.get_pid)

    bottle.route(path_host, "POST", app.enable_host)
    bottle.route(path_host, "DELETE", app.disable_host)
    bottle.route(path_host, "GET", app.get_host)
    bottle.route(path_host + "/<key_path:path>", "GET", app.get_host)

    bottle.route(path_latency, "POST", app.add_latency)
    bottle.route(path_latency, "DELETE", app.remove_latency)
    bottle.route(path_latency, "GET", app.get_latency)
    bottle.route(path_latency + "/<key_path:path>", "GET", app.get_latency)


    bottle.route(path_socket, "POST", app.add_socket)
    bottle.route(path_socket, "DELETE", app.remove_socket)
    bottle.route(path_socket_base, "GET", app.get_socket)
    bottle.route(path_socket_base + "/<key_path:path>", "GET", app.get_socket)

    server = Thread(target = bottle.run, kwargs = {'host': config.get("host", "0.0.0.0"), 'port': config.get("port", 8001)})
    server.daemon = True;
    server.start()
    app.loop()
