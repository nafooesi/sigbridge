import json
import asyncore
import os
import logging
import threading

from smtpd import SMTPServer
from ibWrapper import IBWrapper
from logging.handlers import TimedRotatingFileHandler
from time import sleep
from slack import Slack

from tradeStationSignal import TradeStationSignal


class SigServer(SMTPServer):
    order_type_map = {'market': 'mkt'}
    ib_clients = dict()  # a dict to reference different client by account id
    # --- creating log file handler --- #
    if not os.path.isdir('logs'):
        os.makedirs('logs')
    logger = logging.getLogger("SigServer")
    logger.setLevel(logging.INFO)

    # create file, formatter and add it to the handlers
    fh = TimedRotatingFileHandler('logs/SigServer.log', when='d',
                                  interval=1, backupCount=10)
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(process)d - %(name)s '
                                  '(%(levelname)s) : %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    # --- Done creating log file handler --- #

    def __init__(self, laddr, raddr, uilogger):
        SMTPServer.__init__(self, laddr, raddr)
        self.uilogger = uilogger

    def process_message(self, peer, mailfrom, rcpttos, data):
        """
        This is the function for smtpServer to receive emails
        from TradeStation
        :param peer:
        :param mailfrom:
        :param rcpttos:
        :param data:
        :return:
        """
        # TODO: restrict sender ip via peer?
        self.logger.info(' '.join(["Receiving signal from:", str(peer), ' with\n', data]))
        # send data to slack channel
        Slack().send(data)
        # print "mailfrom:", mailfrom
        # print "rcpttos:", rcpttos
        if data:
            ts_signal = TradeStationSignal(data)
            if ts_signal.verify_attributes():
                self.log_all(' '.join(['verified signal:', ts_signal.action,
                                       str(ts_signal.quantity), ts_signal.symbol,
                                       '@', ts_signal.order_type, "\n\n"]))

                # make this threaded perhaps?
                for ib_cli in self.ib_clients.itervalues():
                    # sending order to each IB client
                    quantity = int(round(ts_signal.quantity * ib_cli.sig_multiplier))
                    ib_cli.placeOrder(ib_cli.nextOrderId, ib_cli.create_contract(ts_signal.symbol, 'stk'),
                                      ib_cli.create_order(self.order_type_map[ts_signal.order_type],
                                                          quantity, ts_signal.action))

                    self.log_all(' '.join(["sent", ib_cli.account_id, ts_signal.action,
                                           str(quantity), ts_signal.symbol,
                                           '@', ts_signal.order_type]))
                    ib_cli.nextOrderId += 1

    def run(self):
        """
        This function will read the IB client config file and attempt to connet
        to specified TWS in its own thread.
        :return:
        """
        with open('conf/ibclients.json', 'r') as cf:
            ib_conf = json.loads(cf.read())

        for ib_host in ib_conf:
            ib_thread = threading.Thread(target=self.ib_thread,
                                         kwargs=dict(ib_host=ib_host))
            ib_thread.daemon = True
            ib_thread.start()

        asyncore.loop()

    def shutdown(self):
        for ib_cli in self.ib_clients.itervalues():
            if ib_cli:
                ib_cli.disconnect()
        self.close()

    def log_all(self, message, level="info"):
        """
        print to both log file and the ui logger
        :param message:
        :param level: log level
        :return:
        """
        if level == "info":
            self.logger.info(message)
            self.uilogger.info(message)
        else:
            self.logger.error(message)
            self.uilogger.error(message)

    def ib_thread(self, ib_host=None):
        """
        This function calls by each IB client thread for connection to TWS.
        It will retry connection until successful.
        :param ib_host:
        :return:
        """
        if not ib_host:
            return

        if 'active' in ib_host and not ib_host['active']:
            # skip inactive client
            return

        ib = IBWrapper(ib_host['server'], ib_host['port'], ib_host['client_id'],
                       ib_host['sig_multiplier'], self.uilogger)
        wait_sec = 5
        while not ib.account_id:
            ib.connect()
            if not ib.account_id:
                self.log_all(' '.join(
                    ["Failed to connect to", ib_host['server'], ':', str(ib_host['port']),
                     "retrying in", str(wait_sec), "seconds."]
                ), 'error')
                sleep(wait_sec)
            wait_sec = int(wait_sec * 1.5)      # relax the wait time by 50% on each retry

        self.ib_clients[ib.account_id] = ib     # provides a reference to ib client for interaction
        self.log_all('Connected to IB account: ' + ib.account_id)
