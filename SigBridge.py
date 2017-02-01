#!/usr/bin/python
# -*- coding: iso-8859-1 -*-
from Tkinter import Tk, Label, StringVar, Entry, Button, END
from smtpd import SMTPServer
from ibWrapper import IBWrapper

import json
import asyncore
import threading


class SigServer(SMTPServer):
    orderTypeMap = {'market': 'mkt'}
    ib = None
    with open('conf/ibclients.json', 'r') as cf:
        ib_conf = json.loads(cf.read())

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

                # sending order to IB
                res = self.ib.placeOrder(self.orderId,
                    self.ib.create_contract(ts_signal.symbol, 'stk'),
                    self.ib.create_order(self.orderTypeMap[ts_signal.orderType],
                        ts_signal.quantity, ts_signal.action))
                self.orderId += 1

    def run(self):
        # TODO Add multiple IB connections
        self.ib = IBWrapper(self.ib_conf[0]['server'],
                                self.ib_conf[0]['port'],
                                self.ib_conf[0]['client_id'])
        self.orderId = int(self.ib.nextOrderId)
        try:
            asyncore.loop()
        except KeyboardInterrupt:
            print "Keyboard Interrupt Intercepted."

    def shutdown(self):
        if self.ib:
            self.ib.disconnect()
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


class SigBridgeUI(Tk):
    def __init__(self,parent):
        Tk.__init__(self,parent)
        self.parent = parent
        self.initialize()

    def initialize(self):
        self.grid()

        # from_label = Label(self, text="From:").grid(column=0, row=0)

        # text box input for smtp ip
        # self.entry_variable = StringVar()
        # self.entry = Entry(self, textvariable=self.entry_variable)
        # self.entry.grid(column=0, row=0, sticky='W')
        # self.entry.bind("<Return>", self.on_press_enter)
        # self.entry_variable.set("localhost")

        # button
        self.button = Button(self, text="Start Server", command=self.start_server)
        self.button.grid(column=0, row=0)
        
        # label output
        self.label_variable = StringVar()
        label = Label(self, textvariable=self.label_variable, anchor="w", fg="black")
        label.grid(column=0, row=1, columnspan=3, sticky='EW')
        self.label_variable.set("")

        # general config
        self.grid_columnconfigure(0, weight=1)
        self.resizable(True, False)
        self.update()
        self.set_geometry()
        # self.entry.focus_set()
        # self.entry.selection_range(0, END)

    def set_geometry(self):
        # set position in window
        w = 200  # width for the Tk
        h = 100  # height for the Tk

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
            self.server = SigServer(('0.0.0.0', 25), None)
            self.server_thread = threading.Thread(name='server', target=self.server.run)
            self.server_thread.daemon = True
            self.server_thread.start()
            # TODO: Not sure how to send message to UI if IB thread fails to connect
            # Perhaps use a Queue as messaging pipe between the two?
            if self.server.ib is None:
                print "ib object is None"
            self.button.configure(text="Stop Server", command=self.stop_server)
            self.label_variable.set("Signal Server Started.")
        except Exception as err:
            print "Cannot start the server: %s" % err.message
            self.label_variable.set("ERROR: %s" % err.message)

        # self.label_variable.set(self.entry_variable.get()+"(Started Signal Server)")
        # self.entry.focus_set()
        # self.entry.selection_range(0, END)

    def stop_server(self):
        self.server.shutdown()
        self.button.configure(text="Start Server", command=self.start_server)
        self.label_variable.set("Signal Server Stopped.")

    # def on_press_enter(self, event):
        # self.label_variable.set(self.entry_variable.get()+" (You pressed ENTER)")
        # self.entry.focus_set()
        # self.entry.selection_range(0, END)


if __name__ == '__main__':
    app = SigBridgeUI(None)
    app.title('SigBridge')
    app.mainloop()
