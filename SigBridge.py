#!/usr/bin/python
# -*- coding: iso-8859-1 -*-
from Tkinter import Tk, Button, END, Frame
from smtpd import SMTPServer
from ibWrapper import IBWrapper
from logging.handlers import TimedRotatingFileHandler
from ScrolledText import ScrolledText

import json
import asyncore
import threading
import os
import logging
import Queue


# TODO:
# fail catch on one of the IB clients
# queue messages
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

        self.orderTypeMap = {'market': 'mkt'}
        self.ib_clients = dict()  # a dict to reference different client by account id

    def process_message(self, peer, mailfrom, rcpttos, data):
        # TODO: restrict sender ip via peer?
        print "peer:", peer
        # print "mailfrom:", mailfrom
        # print "rcpttos:", rcpttos
        if data:
            ts_signal = TradeStationSignal(data)
            print "TradeStation signal:"
            if ts_signal.verify_attributes():
                print ts_signal.action, ts_signal.quantity, ts_signal.symbol, '@',\
                    ts_signal.orderType, "\n\n"

                for ib_cli in self.ib_clients.itervalues():
                    # sending order to each IB client
                    ib = ib_cli['ib']
                    ib.placeOrder(ib_cli['nextOrderId'],
                                  ib.create_contract(ts_signal.symbol, 'stk'),
                                  ib.create_order(self.orderTypeMap[ts_signal.orderType],
                                  ts_signal.quantity, ts_signal.action))
                    ib_cli['nextOrderId'] += 1

    def run(self):
        with open('conf/ibclients.json', 'r') as cf:
            ib_conf = json.loads(cf.read())

        # create multiple IB connections
        for ib_host in ib_conf:
            ib = IBWrapper(ib_host['server'], ib_host['port'], ib_host['client_id'])
            if ib.account_id:
                self.ib_clients[ib.account_id] = {
                    'ib': ib,
                    'nextOrderId': int(ib.nextOrderId)
                }
                self.uilogger.info('Connected to account: ' + ib.account_id)
            else:
                self.uilogger.error(' '.join(["Failed to connect to",
                                             ib_host['server'], ':',
                                             ib_host['port']]))
        try:
            # start smtp server with asyncore
            asyncore.loop()
        except KeyboardInterrupt:
            print "Keyboard Interrupt Intercepted."

    def shutdown(self):
        for ib_cli in self.ib_clients.itervalues():
            if ib_cli:
                ib_cli['ib'].disconnect()
        self.close()


class TradeStationSignal:
    subject_key = 'tradestation - new order has been placed for '
    action = None
    symbol = None
    quantity = 0
    orderType = None
    accountName = None
    orderId = None

    def __init__(self, data):
        """
        Parses email data into wanted attributes
        """
        if data:
            for line in data.split('\n'):
                line = line.strip().lower()
                if line.startswith('subject:'):
                    # ensure this email is intended
                    if self.subject_key not in line:
                        print "Error: unrecognized subject:", line
                        return
                elif line.startswith('order:'):
                    line = line.replace('buy to cover', 'buy')
                    line = line.replace('sell short', 'sell')
                    line = line.replace(',', '')
                    params = line.split(' ')
                    self.action = params[1]
                    self.quantity = int(params[2])
                    self.symbol = params[3]
                    self.orderType = params[5]
                elif line.startswith('account:'):
                    params = line.split(' ')
                    self.accountName = params[1]
                elif line.startswith('order#:'):
                    params = line.split(' ')
                    self.orderId = params[1]

    def verify_attributes(self):
        if not self.symbol:
            print "Error: no symbol found!"
            return False
        if not self.action or self.action not in ['sell', 'buy']:
            print "Error: unexpected action: ", self.action
            return False
        if not self.orderType or self.orderType not in ['market']:
            print "Error: unexpected order type: ", self.orderType
            return False
        if not self.quantity or self.quantity <= 0:
            print "Error: unexpected quantity: ", self.quantity
            return False
        if not self.accountName:
            print "Error: no accountName!"
            return False
        if not self.orderId:
            print "Error: no order id!"
            return False
        return True


class QueueLogger(logging.Handler):
    def __init__(self, queue):
        logging.Handler.__init__(self)
        self.queue = queue

    # write in the queue
    def emit(self, record):
        self.queue.put(self.format(record).rstrip('\n') + '\n')


# noinspection SpellCheckingInspection
class SigBridgeUI(Tk):
    server = None
    server_thread = None

    def __init__(self):
        Tk.__init__(self)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # 2 rows: firts with settings, second with registrar data
        self.main_frame = Frame(self)
        # Commands row doesn't expands
        self.main_frame.rowconfigure(0, weight=0)
        # Logs row will grow
        self.main_frame.rowconfigure(1, weight=1)
        # Main frame can enlarge
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.grid(row=0, column=0)

        # Run/Stop button
        self.server_button = Button(self.main_frame, text="Start Server", command=self.start_server)
        self.server_button.grid(row=0, column=0)

        # Clear button
        self.clear_button = Button(self.main_frame, text="Clear Log", command=self.clear_log)
        self.clear_button.grid(row=0, column=1)

        # Logs Widget
        self.log_widget = ScrolledText(self.main_frame)
        self.log_widget.grid(row=1, column=0, columnspan=2)
        # made not editable
        self.log_widget.config(state='disabled')

        # Queue where the logging handler will write
        self.log_queue = Queue.Queue()

        # Setup the logger
        self.uilogger = logging.getLogger('SigBridgeUI')
        self.uilogger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

        # Use the QueueLogger as Handler
        hl = QueueLogger(queue=self.log_queue)
        hl.setFormatter(formatter)
        self.uilogger.addHandler(hl)

        # self.log_widget.update_idletasks()
        self.set_geometry()

        # Setup the update_widget callback reading logs from the queue
        self.start_log()

    def clear_log(self):
        self.log_widget.config(state='normal')
        self.log_widget.delete(0.0, END)
        self.log_widget.config(state='disabled')

    def start_log(self):
        self.uilogger.info("Starting the logger")
        self.update_widget()
        # self.control_log_button.configure(text="Pause Log", command=self.stop_log)

    def update_widget(self):
        self.log_widget.config(state='normal')
        # Read from the Queue and add to the log widger
        while not self.log_queue.empty():
            line = self.log_queue.get()
            self.log_widget.insert(END, line)
            self.log_widget.see(END)  # Scroll to the bottom
            self.log_widget.update_idletasks()
        self.log_widget.config(state='disabled')
        self.log_widget.after(10, self.update_widget)

    def set_geometry(self):
        # set position in window
        w = 600  # width for the Tk
        h = 300  # height for the Tk

        # get screen width and height
        ws = self.winfo_screenwidth()   # width of the screen
        hs = self.winfo_screenheight()  # height of the screen

        # calculate x and y coordinates for the Tk window
        x = (ws/2) - (w/2)
        y = (hs/2) - (h/2)

        # set the dimensions of the screen 
        # and where it is placed
        self.geometry('%dx%d+%d+%d' % (w, h, x, y))

    def start_server(self):
        try:
            self.server = SigServer(('0.0.0.0', 25), None, self.uilogger)
            self.server_thread = threading.Thread(name='server', target=self.server.run)
            self.server_thread.daemon = True
            self.server_thread.start()
            # TODO: Not sure how to send message to UI if IB thread fails to connect
            # Perhaps use a Queue as messaging pipe between the two?
            self.server_button.configure(text="Stop Server", command=self.stop_server)
            # self.label_variable.set("Signal Server Started.")
        except Exception as err:
            print "Cannot start the server: %s" % err.message
            # self.label_variable.set("ERROR: %s" % err.message)

        # self.label_variable.set(self.entry_variable.get()+"(Started Signal Server)")
        # self.entry.focus_set()
        # self.entry.selection_range(0, END)

    def stop_server(self):
        self.server.shutdown()
        self.server_button.configure(text="Start Server", command=self.start_server)
        # self.label_variable.set("Signal Server Stopped.")


if __name__ == '__main__':
    app = SigBridgeUI()
    app.title('SigBridge')
    app.mainloop()
