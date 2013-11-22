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
import json

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
                    try:
                        d = reduce(lambda di, key: di.get(key, None), path, d)
                    except AttributeError:
                        d = None

                    if d:
                        data['data'] = d
                        return copy(data)
                    else:
                        return None


class Filter(object):
    def __init__(self):
        self.tree = dict()

    def __str__(self):
        return json.dumps(self.tree)

    def __search_keys(self, _dict, _list):
        ret_l = []
        for l in _list:
            if str(l) in _dict:
                ret_l.append(str(l))
        return ret_l

    def reset(self):
        self.tree = dict()

    def add(self, _type, _key, key_path):
        key = str(_key)
        # for test only
        path = key_path.split('/')
        if len(path) > 7 or len(path) < 1:
            return False

        if not _type in self.tree:
            self.tree[_type] = dict()

        # TODO: Check if key is valid
        if not key in self.tree[_type]:
            # sets are not JSON serializable!
            self.tree[_type][key] = dict()

        # Store the string only
        if not key_path in self.tree[_type][key]:
            self.tree[_type][key][key_path] = True

        pprint(self.tree)
        return True

    def remove(self, _type, key, key_path):
        try:
            del self.tree[_type][key][key_path]
            if not self.tree[_type][key]:
                del self.tree[_type][key]
            if not self.tree[_type]:
                del self.tree[_type]

        except KeyError:
            return False

    def apply(self, data):
        # The empty tree -> no filters
        if not self.tree:
            return data

        types = self.__search_keys(self.tree, [data['type'], '~'])
        #print "Matched Types: %s" % types
        if not types:
            return None

        keys = {}
        found = False
        for _type in types:
            keys[_type] = self.__search_keys(self.tree[_type], [data['key'], '~'])
            if keys[_type]:
                found = True

        #print "Matched Keys: %s" % keys
        if not found:
            return None

        ret = {}
        ret['type'] = data['type']
        ret['key'] = data['key']
        ret['timestamp'] = data['data'].get('timestamp', 'nan')
        ret['data'] = {}
        # Save the root pointer
        ret_root = ret
        for _type in types:
            for key in keys[_type]:
                for key_path in self.tree[_type][key].keys():
                    path = key_path.split('/')
                    #print "Checking Path %s" % path
                    try:
                        # This is non-destructive
                        if path[0]:
                            d = reduce(lambda di, key: di.get(key, None), path, data['data'])
                        else:
                            d = data['data']
                    except AttributeError:
                        d = None

                    # Path is valid
                    # `if d` will return false for values equal to 0, nasty bug
                    if not d is None:
                        # Traverse back to root
                        ret = ret_root['data']
                        #print "Path is valid"
                        for p in path:
                            #print "%s/" % p
                            if not p in ret:
                                ret[p] = dict()
                            prev = ret
                            ret = ret[p]
                        prev[p] = d


        if ret_root['data']:
            return ret_root
        else:
            return None

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
        self.data_filter = Filter()

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

    def __send_data_filtered(self, d, d_packed):
        d_filtered = self.data_filter.apply(d)
        if d_filtered:
            if d_filtered == d:
                # if no filtering applied to data, do not pack it again
                self.sock.send(d_packed)
            else:
                self.sock.send(msgpack.dumps(d_filtered))

    def _callback_pid(self, pid, data):
        #pprint(data)
        d = {'type': 'pid', 'key' : pid, 'data' : data}
        d_packed = msgpack.dumps(d)
        self.cache_pid.put('pid', pid, d_packed)
        self.__send_data_filtered(d, d_packed)


    def _callback_host(self, host, data):
        d = {'type': 'host', 'key' : 'host', 'data' : data}
        d_packed = msgpack.dumps(d)
        self.cache_host.put('host', 'host', d_packed)
        self.__send_data_filtered(d, d_packed)

    def _callback_latency(self, target, data):
        d = {'type': 'latency', 'key' : target, 'data' : data}
        d_packed = msgpack.dumps(d)
        self.cache_latency.put('latency', target, d_packed)
        self.__send_data_filtered(d, d_packed)

    # Data is not fine-grained per filter
    def _callback_sock(self, sock, data):
        d = {'type': 'socket', 'key' : 'socket', 'data' : data}
        d_packed = msgpack.dumps(d)
        self.cache_socket.put('socket', 'socket', d_packed)
        self.__send_data_filtered(d, d_packed)

    # These are called in Bottle thread's context
    def add_filter(self, kind, key, key_path):
        if (self.data_filter.add(kind, key, key_path)):
            return http_response(DimonError.SUCCESS)
        else:
            return http_response(DimonError.RUNTIME)

    def remove_filter(self, kind, key, key_path):
        if (self.data_filter.remove(kind, key, key_path)):
            return http_response(DimonError.SUCCESS)
        else:
            return http_response(DimonError.NOTFOUND)
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

    def add_filter_pid(self, pid, key_path):
        return self.add_filter('pid', pid, key_path)

    def remove_filter_pid(self, pid, key_path):
        return self.remove_filter('pid', pid, key_path)

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

    def add_filter_host(self, key_path):
        return self.add_filter('host', 'host', key_path)

    def remove_filter_host(self, key_path):
        return self.remove_filter('host', 'host', key_path)

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

    def add_filter_latency(self, target, key_path):
        if target == '~' or self.__host_regex.match(target) or self.__ip_regex.match(target):
            return self.add_filter('latency', target, key_path)
        else:
            http_response(DimonError.NOTFOUND)

    def remove_filter_latency(self, target, key_path):
        if target == '~' or self.__host_regex.match(target) or self.__ip_regex.match(target):
            return self.remove_filter('latency', target, key_path)
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

    def add_filter_socket(self, key_path):
        return self.add_filter('socket', 'socket', key_path)

    def remove_filter_socket(self, key_path):
        return self.add_filter('socket', 'socket', key_path)

    def get_socket(self, key_path = None):
        d = self.cache_socket.get('socket', 'socket', key_path)
        if d:
            return d
        else:
            http_response(DimonError.NOTFOUND)

    def get_filters(self):
        return str(self.data_filter)

    def remove_filters(self):
        try:
           self.data_filter.reset()
           return http_response(DimonError.SUCCESS)
        except:
            return http_response(DimonError.RUNTIME)

if __name__ == "__main__":
    config = dict()

    # TODO: Level
    logging.basicConfig(filename=config.get('logfile', 'dimond.log'), level=logging.DEBUG, format='%(asctime)s %(message)s')

    # TODO: API version should be static for each call, not from __api__
    rp = "/dimon/v%s" % (__api__,)

    path_pid_base = rp + "/%s/pid"
    path_pid_monitor = (path_pid_base % 'monitor') + "/<pid:int>"
    path_pid_filter = (path_pid_base % 'filter') + "/<pid:re:[0-9]+|~>"

    path_host_base = rp + "/%s/host"
    path_host_monitor = (path_host_base % 'monitor')
    path_host_filter = (path_host_base % 'filter')

    path_latency_base = rp + "/%s/latency"
    path_latency_monitor = (path_latency_base % 'monitor') + "/<target>"
    path_latency_filter = (path_latency_base % 'filter') + "/<target>"

    path_socket_base = rp + "/%s/socket"
    path_socket_monitor = (path_socket_base % 'monitor') + "/<proto:re:tcp|udp>/<direction:re:bi|src|dst>/<port:int>"
    #path_socket_filter = (path_socket_base % 'filter') + "/<proto:re:tcp|udp|~>/<direction:re:bi|src|dst|~>/<port:re:[0-9]+|~>"

    logging.info("Starting dimon-daemon.")
    app = DimonDaemon(config)

    ### Routes
    bottle.debug(True)
    bottle.route(rp + "/info", "GET", app.get_info)

    bottle.route(path_pid_monitor, "POST", app.add_pid)
    bottle.route(path_pid_monitor, "DELETE", app.remove_pid)
    bottle.route(path_pid_monitor, "GET", app.get_pid)
    bottle.route(path_pid_monitor + "/<key_path:path>", "GET", app.get_pid)
    bottle.route(path_pid_filter + "/<key_path:path>", "POST", app.add_filter_pid)
    bottle.route(path_pid_filter + "/<key_path:path>", "DELETE", app.remove_filter_pid)

    bottle.route(path_host_monitor, "POST", app.enable_host)
    bottle.route(path_host_monitor, "DELETE", app.disable_host)
    bottle.route(path_host_monitor, "GET", app.get_host)
    bottle.route(path_host_monitor+ "/<key_path:path>", "GET", app.get_host)
    bottle.route(path_host_filter + "/<key_path:path>", "POST", app.add_filter_host)
    bottle.route(path_host_filter + "/<key_path:path>", "DELETE", app.remove_filter_host)

    bottle.route(path_latency_monitor, "POST", app.add_latency)
    bottle.route(path_latency_monitor, "DELETE", app.remove_latency)
    bottle.route(path_latency_monitor, "GET", app.get_latency)
    bottle.route(path_latency_monitor + "/<key_path:path>", "GET", app.get_latency)
    bottle.route(path_latency_filter + "/<key_path:path>", "POST", app.add_filter_latency)
    bottle.route(path_latency_filter + "/<key_path:path>", "DELETE", app.add_filter_latency)

    bottle.route(path_socket_monitor, "POST", app.add_socket)
    bottle.route(path_socket_monitor, "DELETE", app.remove_socket)
    bottle.route(path_socket_base % 'monitor', "GET", app.get_socket)
    bottle.route((path_socket_base % 'monitor') + "/<key_path:path>", "GET", app.get_socket)
    bottle.route((path_socket_base % 'filter') + "/<key_path:path>", "POST", app.add_filter_socket)
    bottle.route((path_socket_base % 'filter') + "/<key_path:path>", "DELETE", app.remove_filter_socket)

    bottle.route(rp + '/filter', "GET", app.get_filters)
    bottle.route(rp + '/filter', "DELETE", app.remove_filters)
    #bottle.route(path_filter, "POST", app.add_filter)
    #bottle.route(path_filter, "DELETE", app.remove_filter)

    server = Thread(target = bottle.run, kwargs = {'host': config.get("host", "0.0.0.0"), 'port': config.get("port", 8001)})
    server.daemon = True;
    server.start()
    app.loop()
