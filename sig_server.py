import os
import yaml
import asyncore
from threading import Thread

from smtpd import SMTPServer
from time import sleep, time

from ib_wrapper import IBWrapper
from slack_web_hook import SlackWebHook
from email_sender import EmailSender
from trade_station_signal import TradeStationSignal
from fix_processor import FixProcessor
from sig_logger import SigLogger


class SigServer(SMTPServer):

    def __init__(self, laddr, raddr, uilogger):
        SMTPServer.__init__(self, laddr, raddr)
        self.uilogger = uilogger
        self.logger = SigLogger("SigServer", uilogger=uilogger)

        self.ib_clients = []        # a dict to reference different client by account id
        self.fix_clients = dict()   # a dict to reference fix clients
        self.em_clients = list()    # list of emails only clients
        self.ems = None             # email sender object
        self.slack = None           # slack client
        self.sig_shutdown = False   # signal to shut down
        self._init_app()
        self._init_client()

    def _init_app(self):
        """
        Initialize application settings from app.yml.
        """
        with open('conf/app.yml', 'r') as cf:
            conf = yaml.load(cf, Loader=yaml.FullLoader)

        if "email_sender" in conf:
            self.ems = EmailSender(
                                    conf["email_sender"]["smtp_server"],
                                    conf["email_sender"]["smtp_port"],
                                    conf["email_sender"]["sender"],
                                    self.uilogger,
                                    conf["email_sender"]["user"],
                                    conf["email_sender"]["password"],
                                    max_retry=conf["email_sender"].get("max_retry", 7),
                                    queue_time=conf["email_sender"].get("queue_time", 5),
                                    send_opt=conf["email_sender"].get("send_opt", 1)
                                  )

            # start email sender daemon
            ems_thread = Thread(target=self.ems.daemon_sender,
                                          args=(self.em_clients,))
            ems_thread.daemon = True
            ems_thread.start()

        if "slack" in conf:
            self.slack = SlackWebHook(
                               conf['slack']['webhook_path'],
                               url=conf['slack']['webhook_url'],
                               channel=conf['slack']['channel'],
                               username=conf['slack']['username'],
                               icon=conf['slack']['icon']
                             )

    def _init_client(self):
        """
        Initialize client settings from clients.yml.
        """
        with open('conf/clients.yml', 'r') as cf:
            conf = yaml.load(cf, Loader=yaml.FullLoader)

        for client in conf:
            # skip any client without active flag of value True
            if not client.get('active'):
                continue

            # add email client to a list
            if client.get('email'):
                # email client
                self.em_clients.append(client['email'])
                continue

            if client.get('fix_cfg_path'):
                fix_thread = Thread(target=self.fix_thread,
                                    kwargs=dict(client=client))
                fix_thread.daemon = True
                fix_thread.start()
                continue

            # remainings are IBs
            # create a thread to connect each IB client so that it's non-blocking
            ib_thread = Thread(target=self.ib_thread,
                               kwargs=dict(ib_host=client))
            ib_thread.daemon = True
            ib_thread.start()

    def log_all(self, msg, level="info"):
        self.logger.log_all(msg, level=level)

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
            for ib_cli in self.ib_clients:
                ib_cli.process_order(ts_signal)
        except Exception as e:
            self.log_all('<IB Client> ' + str(e), level="error")

        try:
            # send order to fix client
            for (key, fix_cli) in self.fix_clients.items():
                print(" --- send order to fix client: " + key)
                fix_cli.process_order(ts_signal)
        except Exception as e:
            self.log_all('<Fix client>' + str(e), level="error")

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
        Start up the server.
        """
        self.sig_shutdown = False
        try:
            asyncore.loop(timeout=0.8)
        except Exception as e:
            # captures 'Bad file descriptor' error when server quits.
            self.logger.error(e)

    def shutdown(self):
        """Shutdown the server."""
        self.sig_shutdown = True
        print(" >>>>> shutdown <<<<<< ")
        for ib_cli in self.ib_clients:
            ib_cli.disconnect()

        for (k, fix_cli) in self.fix_clients.items():
            fix_cli.stop()

        del self.ib_clients[:]
        self.fix_clients.clear() 
        self.em_clients = []
        self.close()

    def ib_thread(self, ib_host=None):
        """
        This function calls by each IB client thread for connection to TWS.
        It will retry connection until successful.
        :param ib_host:
        :return:
        """
        if not ib_host:
            return

        ib = IBWrapper(ib_host, self.uilogger)
        self.ib_clients.append(ib)  # provides a reference to ib client for interaction
        ib.connect()

    def fix_thread(self, client=None):
        """
        This function initialize connection to a FIX client.
        """
        if not client:
            return

        cfg_path = client.get("fix_cfg_path")

        proc = FixProcessor(cfg_path, uilogger=self.uilogger)
        self.fix_clients[cfg_path] = proc
        proc.start()


