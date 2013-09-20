# -*- coding: utf-8 -*-

__version__ = "0.1.0"
__api__ = "1.0"

version_info = tuple([int(num) for num in __version__.split('.')])


import logging
import bottle
from threading import Thread, current_thread
from dimon import Dimon, DimonError

__err_map = {DimonError.SUCCESS: 200, DimonError.NOTFOUND: 404,
        DimonError.ACCESSDENIED: 403, DimonError.RUNTIME: 406,
        DimonError.UNEXPECTED: 500}

def http_response(err):
    bottle.abort(__err_map.get(err, 400))

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

        #bottle.debug(debug_server)
        logging.info("Dimon and Bottle initialized")

    def loop(self):
        while True:
            print ">>> loop"
            try:
                self.dimon.spin_once()
            except KeyboardInterrupt:
                logging.info("Shutting down dimon ...")
                self.dimon.shutdown()
                return True

    def _callback_pid(self, pid, data):
        print "[%s] data for %s received" % (current_thread().ident, pid)

    def add_pid(self, pid):
        http_response(self.dimon.monitor_pid(pid, self._callback_pid))


    def remove_pid(self, pid):
        http_response(self.dimon.remove_pid(pid))

if __name__ == "__main__":

    config = dict()
    rp = "/dimon/api/%s" % (__api__,)

    logging.info("Starting dimon-daemon.")
    app = DimonDaemon(config)


    ### Routes
    bottle.debug(True)
    bottle.route(rp + "/monitor/pid/<pid:int>", "POST", app.add_pid)
    bottle.route(rp + "/monitor/pid/<pid:int>", "DELETE", app.remove_pid)

    server = Thread(target = bottle.run, kwargs = {'host': config.get("host", "localhost"), 'port': config.get("port", 8001)})
    server.daemon = True;
    server.start()
    app.loop()
