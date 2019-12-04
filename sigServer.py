import yaml
import asyncore
import os
import logging
import threading

from smtpd import SMTPServer
from logging.handlers import TimedRotatingFileHandler
from time import sleep

from ibWrapper import IBWrapper
from slack import Slack
from emailSender import EmailSender
from tradeStationSignal import TradeStationSignal


class SigServer(SMTPServer):
    order_type_map = {'market': 'mkt'}

    # --- creating log file handler --- #
    # TODO: make a logging module
    if not os.path.isdir('logs'):
        os.makedirs('logs')
    logger = logging.getLogger("SigServer")
    logger.setLevel(logging.INFO)

    # create file, formatter and add it to the handlers
    fh = TimedRotatingFileHandler('logs/SigServer.log', when='d',
                                  interval=1, backupCount=10)
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(process)d - %(name)s '
                                  '(%(lineno)d) %(levelname)s: %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    # --- Done creating log file handler --- #

    def __init__(self, laddr, raddr, uilogger):
        SMTPServer.__init__(self, laddr, raddr)
        self.uilogger = uilogger

        self.ib_clients = dict()  # a dict to reference different client by account id
        self.em_clients = list()  # list of emails only clients
        self.ems = None           # email sender object
        self.slack = None         # slack client

        # Retrieve application config from app.yml to initialize emailsender and slack
        with open('conf/app.yml', 'r') as cf:
            conf = yaml.load(cf, Loader=yaml.FullLoader)

        if "email_sender" in conf:
            self.ems = EmailSender(
                                    conf["email_sender"]["smtp_server"],
                                    conf["email_sender"]["smtp_port"],
                                    conf["email_sender"]["sender"],
                                    self.uilogger
                                  )
        if "slack" in conf:
            self.slack = Slack(
                               conf['slack']['webhook_path'],
                               url=conf['slack']['webhook_url'],
                               channel=conf['slack']['channel'],
                               username=conf['slack']['username'],
                               icon=conf['slack']['icon']
                             )

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
        self.logger.info(' '.join(["Receiving signal from:",
                                   str(peer), ' with\n', data]))

        if not data:
            return

        ts_signal = TradeStationSignal(data)
        if not ts_signal.verify_attributes():
            return

        trade_str = ' '.join([
                                ts_signal.action,
                                str(ts_signal.quantity),
                                ts_signal.symbol, '@',
                                ts_signal.order_type
                            ])

        if ts_signal.price:
            # add price to signal if it has it.
            trade_str += ' price ' + str(ts_signal.price)

        self.log_all(' '.join(['-------> signal:', trade_str, "\n\n"]))

        # sending order to each IB client
        # make this threaded perhaps?
        for ib_cli in self.ib_clients.itervalues():
            quantity = int(round(ts_signal.quantity * ib_cli.sig_multiplier))
            ib_cli.placeOrder(ib_cli.nextOrderId, ib_cli.create_contract(ts_signal.symbol, 'stk'),
                              ib_cli.create_order(self.order_type_map[ts_signal.order_type],
                                                  quantity, ts_signal.action))

            self.log_all(' '.join(["sent", ib_cli.account_id, ts_signal.action,
                                   str(quantity), ts_signal.symbol,
                                   '@', ts_signal.order_type]))
            ib_cli.nextOrderId += 1

        # send data to slack channel
        if self.slack:
            self.slack.send(trade_str)

        # send to email list
        if self.ems:
            # make a fresh connection
            self.ems.connect()
            for email in self.em_clients:
                self.logger.info("Sending sig email to %s" % email)
                # Mobile phone receiving server seems to block email that
                # does not have matching "to" header to actual addressee.
                # This makes it impossible to send bulk email in BCC fashion since putting
                # addressee in bcc header defeats the purpose of bcc.
                # Unfortunately, we'll have to send it one by one to ensure privacy.
                self.ems.send([email], 'SigBridge Alert', trade_str)
            self.ems.quit()

    def run(self):
        """
        This function will read the IB client config file and attempt to connect
        to specified TWS in its own thread.
        :return:
        """
        with open('conf/clients.yml', 'r') as cf:
            conf = yaml.load(cf, Loader=yaml.FullLoader)

        for client in conf:
            # add email client to a list
            if 'email' in client:
                # email client
                if 'active' in client and client['active']:
                    self.em_clients.append(client['email'])
                continue

            # create a thread per IB client
            ib_thread = threading.Thread(target=self.ib_thread,
                                         kwargs=dict(ib_host=client))
            ib_thread.daemon = True
            ib_thread.start()

        try:
            asyncore.loop(timeout=0.8)
        except Exception as e:
            # captures 'Bad file descriptor' error when server quits.
            self.logger.error(e)

    def shutdown(self):
        for ib_cli in self.ib_clients.itervalues():
            if ib_cli:
                ib_cli.disconnect()

        self.em_clients = list()
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
