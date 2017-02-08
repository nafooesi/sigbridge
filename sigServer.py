import json
import asyncore
import os
import logging

from smtpd import SMTPServer
from ibWrapper import IBWrapper
from logging.handlers import TimedRotatingFileHandler

from tradeStationSignal import TradeStationSignal


class SigServer(SMTPServer):
    def __init__(self, laddr, raddr, uilogger):
        SMTPServer.__init__(self, laddr, raddr)

        self.uilogger = uilogger
        # --- creating log file handler --- #
        if not os.path.isdir('logs'):
            os.makedirs('logs')
        self.logger = logging.getLogger("SigServer")
        self.logger.setLevel(logging.INFO)

        # create file, formatter and add it to the handlers
        fh = TimedRotatingFileHandler('logs/SigServer.log', when='d',
                                      interval=1, backupCount=10)
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(process)d - %(name)s '
                                      '(%(levelname)s) : %(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        # --- Done creating log file handler --- #

        self.order_type_map = {'market': 'mkt'}
        self.ib_clients = dict()  # a dict to reference different client by account id

    def process_message(self, peer, mailfrom, rcpttos, data):
        # TODO: restrict sender ip via peer?
        self.logger.info(' '.join(["Receiving signal from:", str(peer), ' with\n', data]))
        # print "mailfrom:", mailfrom
        # print "rcpttos:", rcpttos
        if data:
            ts_signal = TradeStationSignal(data)
            if ts_signal.verify_attributes():
                self.log_all(' '.join(['verified signal:', ts_signal.action, str(ts_signal.quantity), ts_signal.symbol,
                                       '@', ts_signal.order_type, "\n\n"]))

                for ib_cli in self.ib_clients.itervalues():
                    # sending order to each IB client
                    ib = ib_cli['ib']
                    ib.placeOrder(ib_cli['nextOrderId'],
                                  ib.create_contract(ts_signal.symbol, 'stk'),
                                  ib.create_order(self.order_type_map[ts_signal.order_type],
                                                  ts_signal.quantity, ts_signal.action))
                    ib_cli['nextOrderId'] += 1

    def run(self):
        with open('conf/ibclients.json', 'r') as cf:
            ib_conf = json.loads(cf.read())

        # create multiple IB connections
        for ib_host in ib_conf:
            ib = IBWrapper(ib_host['server'], ib_host['port'], ib_host['client_id'], self.uilogger)
            if ib.account_id:
                self.ib_clients[ib.account_id] = {
                    'ib': ib,
                    'nextOrderId': int(ib.nextOrderId)
                }
                self.uilogger.info('Connected to account: ' + ib.account_id)
            else:
                self.uilogger.error(' '.join(["Failed to connect to", ib_host['server'], ':', str(ib_host['port'])]))

        # start smtp server with asyncore
        asyncore.loop()

    def shutdown(self):
        for ib_cli in self.ib_clients.itervalues():
            if ib_cli:
                ib_cli['ib'].disconnect()
        self.close()

    def log_all(self, message):
        """
        print to both log file and the ui logger
        :param message:
        :return:
        """
        self.logger.info(message)
        self.uilogger.info(message)
