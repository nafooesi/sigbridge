import time
import pprint as pp
from Queue import Queue
from threading import Event

import quickfix as fix
from sig_logger import SigLogger
from fixapp.fix_wrapper import FixWrapper
from sig_logger import SigLogger


class FixProcessor():
    def __init__(self, client, uilogger=None):
        cfg_file_path       = client.get("fix_cfg_path")
        self.skip_list      = client.get('skip_list', [])
        self.security_types = client.get('security_types')
        self.sig_multiplier = client.get('sig_multiplier', 0.01)
        self.settings       = fix.SessionSettings(cfg_file_path)
        self.storeFactory   = fix.FileStoreFactory(self.settings)
        self.logFactory     = fix.FileLogFactory(self.settings)

        self.uilogger  = uilogger
        self.logger    = SigLogger("FixProcessor", uilogger=uilogger)

        self.app       = FixWrapper(self.settings, self.logger)
        self.initiator = fix.SocketInitiator(
                                self.app,
                                self.storeFactory,
                                self.settings,
                                self.logFactory)

        self.order_queue = Queue()  # used for order delivery
        self.stop_event = Event()   # used to signal thread exit

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
                    self.log_all("fix client is not logged in: " + self.session_id, level="error")
                    # login will automatically retried every 30s of heartbeat.
                    time.sleep(5)
                    continue

                # we're logged in. Only show connected message on the first 
                # iteration of the loop using the flag.
                if not logged_in:
                    self.log_all("Connected to FIX: " + self.session_id)
                    logged_in = True

                if self.order_queue.empty():
                    time.sleep(0.2)
                    continue

                # loop to check incoming signals
                sig = self.order_queue.get()
                qty = int(round(sig.quantity * self.sig_multiplier))
                self.log_all(' '.join(["sent", self.session_id, sig.action,
                               str(qty), sig.symbol, '@', sig.order_type]))

                options = self.convert_order(sig)
                if sig.action == 'buy':
                    self.app.buy(**options)
                elif sig.action == 'sell':
                    self.app.sell(**options)
                else:
                    self.log_all("Unrecognized action: "
                                + sig.action + " for " + self.session_id,
                                level="error")
                time.sleep(0.2)
        except (fix.ConfigError, fix.RuntimeError, ValueError) as e:
            self.logger.error(pp.pformat(e))

    def process_order(self, ts_signal):
        # skip symbol if it's in the skip list of the client
        if len(self.skip_list) and ts_signal.symbol in self.skip_list:
            return

        # if security type is defined, we will only process the defined ones
        if self.security_types and not self.security_types.get(
                ts_signal.sec_type.lower()):
            return

        self.order_queue.put(ts_signal)

    def convert_order(self, ts_signal):
        return {
            '55': ts_signal.symbol,
            '38': int(round(ts_signal.quantity * self.sig_multiplier)),
        }

    def stop(self):
        self.uilogger.info("Disconnecting FIX: " + str(self.session_id))
        self.app.logout()       # send logout to fix server
        self.initiator.stop()   # stop fix client
        self.stop_event.set()   # stop this thread
        
    def log_all(self, message, level='info'):
        self.logger.log_all(message, level=level)

if __name__ == '__main__':
  proc = FixProcessor({
    "fix_cfg_path": './conf/wex_dv.cfg',
    "sig_multiplier": 0.5,
    })
  proc.start()
