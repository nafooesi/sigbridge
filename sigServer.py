import yaml
import asyncore
import os
import logging
import threading

from smtpd import SMTPServer
from logging.handlers import TimedRotatingFileHandler
from time import sleep, time

from ibWrapper import IBWrapper
from slack import Slack
from emailSender import EmailSender
from tradeStationSignal import TradeStationSignal


class SigServer(SMTPServer):

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

        self.ib_clients = dict()    # a dict to reference different client by account id
        self.em_clients = list()    # list of emails only clients
        self.ems = None             # email sender object
        self.slack = None           # slack client
        self.sig_shutdown = False   # signal to shut down

        # Retrieve application config from app.yml to initialize emailsender and slack
        with open('conf/app.yml', 'r') as cf:
            conf = yaml.load(cf, Loader=yaml.FullLoader)

        if "email_sender" in conf:
            self.ems = EmailSender(
                                    conf["email_sender"]["smtp_server"],
                                    conf["email_sender"]["smtp_port"],
                                    conf["email_sender"]["sender"],
                                    self.uilogger,
                                    max_retry=conf["email_sender"].get("max_retry", 7),
                                    queue_time=conf["email_sender"].get("queue_time", 5),
                                    send_opt=conf["email_sender"].get("send_opt", 1)
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

        try:
            # sending order to each IB client
            # make this threaded perhaps?
            for ib_cli in self.ib_clients.itervalues():
                ib_cli.process_order(ts_signal)
        except Exception as e:
            self.log_all('<IB Client> ' + str(e), level="error")

        # send data to slack channel
        if self.slack:
            self.process_slack(trade_str)
        else:
            self.logger.info(" --- No slack configuration found.")

        try:
            # send to email list
            if self.ems:
                self.ems.queue_trade(trade_str)
            else:
                self.logger.info(" --- No email client configuration found.")
        except Exception as e:
            self.log_all('<Email Client> ' + str(e), level="error")

    def process_slack(self, trade_str):
        try_cnt = 0
        while try_cnt <= 5:
            try:
                self.slack.send(trade_str)
                break
            except Exception as e:
                try_cnt += 1
                if try_cnt > 5:
                    self.log_all('<Slack Client> ' + str(e), level="error")
                else:
                    self.log_all('<Slack Client> ' + str(e), level="info")
                sleep(try_cnt)

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

            # create a thread to connect each IB client so that it's non-blocking
            ib_thread = threading.Thread(target=self.ib_thread,
                                         kwargs=dict(ib_host=client))
            ib_thread.daemon = True
            ib_thread.start()

        if self.ems:
            # start email sender daemon
            ems_thread = threading.Thread(target=self.ems.daemon_sender,
                                          args=(self.em_clients,))
            ems_thread.daemon = True
            ems_thread.start()

        self.sig_shutdown = False
        try:
            asyncore.loop(timeout=0.8)
        except Exception as e:
            # captures 'Bad file descriptor' error when server quits.
            self.logger.error(e)

    def shutdown(self):
        self.sig_shutdown = True
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

        ib = IBWrapper(ib_host, self.uilogger)
        connected = ib.connect()
        """
        wait_sec = 5
        while not ib.account_id:
            if self.sig_shutdown:
                return
            ib.connect()
            if not ib.account_id:
                self.log_all(' '.join(
                    ["Failed to connect to", ib_host['server'], ':', str(ib_host['port']),
                     "retrying in", str(wait_sec), "seconds."]
                ), 'error')
                sleep(wait_sec)
            wait_sec = int(wait_sec * 1.5)   # relax the wait time by 50% on each retry
        """
        if connected:
            self.ib_clients[ib.account_id] = ib  # provides a reference to ib client for interaction
            self.log_all('Connected to IB account: ' + ib.account_id)
        else:
            self.log_all(' '.join(['Failed to connect to', ib_host['server'], ':', str(ib_host['port'])]))
