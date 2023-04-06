import time
import pprint as pp
from Queue import Queue
from threading import Event

import quickfix as fix
from sig_logger import SigLogger
from fixapp.fix_wrapper import FixWrapper as FixClient


class FixProcessor():
    def __init__(self, cfg_file_path, uilogger=None):
        self.settings     = fix.SessionSettings(cfg_file_path)
        self.storeFactory = fix.FileStoreFactory(self.settings)
        self.logFactory   = fix.FileLogFactory(self.settings)

        self.app          = FixClient(self.settings)
        self.initiator    = fix.SocketInitiator(
                                self.app,
                                self.storeFactory,
                                self.settings,
                                self.logFactory)
        self.uilogger = uilogger
        self.msg_queue = Queue()
        self.stop_event = Event()

    @property
    def session_id(self):
        return str(self.app.sessionID)

    def is_logged_in(self):
        return self.app.is_logged_in

    def start(self):
        try:
            self.initiator.start()
            time.sleep(2)
            logged_in = False  # logged in state check for printing message
            while not (self.stop_event and self.stop_event.is_set()):

                if not self.is_logged_in() and not self.stop_event.is_set():
                    # send not logged-in error
                    self.uilogger.error("fix client is not logged in: " + self.session_id)
                    # login will automatically retried every 30s of heartbeat.
                    time.sleep(5)
                    continue

                # we're logged in. Only show connected message on the first 
                # iteration of the loop using the flag.
                if not logged_in:
                    self.uilogger.info("Connected to FIX: " + self.session_id)
                    logged_in = True

                if self.msg_queue.empty():
                    time.sleep(0.2)
                    continue

                # loop to check incoming signals
                sig = self.msg_queue.get()
                self.uilogger.info(' '.join(["sent", self.session_id, sig.action,
                               str(sig.quantity), sig.symbol,
                               '@', sig.order_type]))

                options = self.convert_order(sig)
                if sig.action == 'buy':
                    self.app.buy(**options)
                elif sig.action == 'sell':
                    self.app.sell(**options)
                else:
                    self.uilogger.error(
                        "Unrecognized action: "
                        + sig.action + " for " + self.session_id)

                time.sleep(0.2)
        except (fix.ConfigError, fix.RuntimeError, ValueError) as e:
            pp.pprint(e)

    def process_order(self, ts_signal):
        self.msg_queue.put(ts_signal)

    def convert_order(self, ts_signal):
        return {
            '55': ts_signal.symbol,
            '38': ts_signal.quantity,
        }

    def stop(self):
        self.uilogger.info("Disconnecting FIX: " + str(self.session_id))
        self.app.logout()       # send logout to fix server
        self.initiator.stop()   # stop fix client
        self.stop_event.set()   # stop this thread
        

if __name__ == '__main__':
  proc = FixProcessor("./conf/wex_dv.cfg")
  proc.start()
