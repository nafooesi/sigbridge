# -*- coding: utf-8 -*-
import re
from time import sleep
import yaml
from threading import Event

from ib.ext.Contract import Contract
from ib.ext.Order import Order
from ib.opt import ibConnection
from sig_logger import SigLogger


TS2IB_ORDER_TYPE_MAP = {'market': 'mkt'}


class IBWrapper:
    def __init__(self, ib_host, uilogger=None):
        self.nextOrderId = 0
        self.account_id = None
        self.reconnected = False
        self.stop_event = Event()
        self.logger = SigLogger("IBWrapper", uilogger=uilogger)

        self.con_str = ''.join([ib_host['server'], ":", str(ib_host['port'])])
        self.con = ibConnection(ib_host['server'], ib_host['port'], ib_host['client_id'])
        self.sig_multiplier = ib_host['sig_multiplier'] or 0.01
        self.skip_list = ib_host.get('skip_list', list())

        # Assign corresponding handling function to message types
        self.con.register(self.my_account_handler, 'UpdateAccountValue')
        self.con.register(self.error_handler, 'Error')
        self.con.register(self.next_valid_id_handler, 'NextValidId')
        self.con.register(self.managed_account_handler, 'ManagedAccounts')
        # self.con.register(self.my_tick_handler, message.tickSize, message.tickPrice)

        # Assign rest of server reply messages to the
        # reply_handler function
        # self.con.registerAll(self.reply_handler)

        # reading ib's symbol mapping
        with open('conf/ibsymbols.yml', 'r') as cf:
            self.symbol_map = yaml.load(cf, Loader=yaml.FullLoader)

    def connect(self):
        cnt = 0
        while not (self.stop_event and self.stop_event.is_set()):
            if self.con.connect():
                # give it a second to get data
                sleep(1)
                if self.account_id:
                    self.log_all("Connected to IB: " + self.account_id)
                return True
            else:
                # keep max retry count
                cnt += 1
                if cnt > 15:
                    return False
                sleep_time = 2 * cnt
                acct = self.account_id if self.account_id else self.con_str
                self.log_all('Not connected to IB account %s, will retry in %d sec...' % 
                             (acct, sleep_time),
                             level="error")
                sleep(sleep_time)

    def my_account_handler(self, msg):
        self.logger.info(msg)

    def managed_account_handler(self, msg):
        """Handles the capturing of account id"""
        regex = re.search(r'accountsList=(\w+)', str(msg))
        if regex:
            self.account_id = regex.group(1)
            self.logger.info("IB account: %s" % self.account_id)
        else:
            raise ValueError("No account id found in msg: " + msg)

    def my_tick_handler(self, msg):
        self.logger.info(msg)

    def next_valid_id_handler(self, msg):
        """Handles the capturing of next valid order id"""
        regex = re.search(r'orderId=(\d+)', str(msg))
        if regex:
            self.nextOrderId = int(regex.group(1))
            self.logger.info("next valid id: %d" % self.nextOrderId)
        else:
            raise ValueError("No next valid id found in msg: " + msg)

    def error_handler(self, msg):
        """Handles the capturing of error messages"""
        regex = re.search(r'<.*errorCode=(.*),\serrorMsg=(.*)>', str(msg))
        if regex:
            err_code = regex.group(1)
            err_msg = regex.group(2)
            self.logger.info("IB MSG [code: %s, message: %s]" % (err_code, err_msg))
            if err_code == 'None' and err_msg.startswith('unpack requires a string'):
                self.log_all("IB account " + self.account_id + " was shutdown!", level="error")
            if err_code == '504' and err_msg.startswith('Not connected'):
                self.log_all("IB account not connected.  Will try connecting.", level="error")
                self.connect()
                self.reconnected = True  # turn on flag to resubmit order
        else:
            self.logger.error("IB Error: %s" % msg)

    def reply_handler(self, msg):
        """Handles of server replies"""
        self.logger.info("Server Response: %s, %s" % (msg.typeName, msg))

    def create_contract(self, symbol, sec_type, exch='SMART', prim_exch='SMART', curr='USD'):
        """
        Create a Contract object defining what will
        be purchased, at which exchange and in which currency.

        symbol - The ticker symbol for the contract
        sec_type - The security type for the contract ('STK' is 'stock')
        exch - The exchange to carry out the contract on
        prim_exch - The primary exchange to carry out the contract on
        curr - The currency in which to purchase the contract
        """
        sec_type = sec_type.lower()
        symbol = symbol.lower()

        # check the symbol map to see if any attributes were defined for this symbol's order
        # e.g. "GLD" has primary exchange defined to disambiguate from "GLD" of foreign exchanges.
        if sec_type in self.symbol_map:
            if symbol in self.symbol_map[sec_type]:
                if 'prim_exch' in self.symbol_map[sec_type][symbol]:
                    prim_exch = str(self.symbol_map[sec_type][symbol]['prim_exch'])

        contract = Contract()
        contract.m_symbol = symbol
        contract.m_secType = sec_type
        contract.m_exchange = exch
        contract.m_primaryExch = prim_exch
        contract.m_currency = curr

        return contract

    def create_order(self, order_type, quantity, action):
        """Create an Order object (Market/Limit) to go long/short.

        order_type - 'MKT', 'LMT' for Market or Limit orders
        quantity - Integral number of assets to order
        action - 'BUY' or 'SELL'
        """
        order = Order()
        order.m_orderType = order_type
        order.m_totalQuantity = quantity
        order.m_action = action
        return order

    def placeOrder(self, order_id, contract, order):
        return self.con.placeOrder(order_id, contract, order)

    def disconnect(self):
        self.log_all("Disconnecting IB: %s @ %s" % (self.account_id, self.con_str))
        self.con.disconnect()
        self.stop_event.set()

    def reqQuote(self, contract):
        self.con.reqMktData(1, contract, '', False)

    def log_all(self, message, level='info'):
        self.logger.log_all(message, level=level)

    def process_order(self, ts_signal):
        # check if this cient has skip list and whether the signal
        # is in this list
        if len(self.skip_list) and ts_signal.symbol in self.skip_list:
            return

        quantity = int(round(ts_signal.quantity * self.sig_multiplier))
        self.placeOrder(self.nextOrderId,
                        self.create_contract(ts_signal.symbol, 'stk'),
                        self.create_order(
                            TS2IB_ORDER_TYPE_MAP[ts_signal.order_type],
                            quantity,
                            ts_signal.action)
                        )

        # placeOrder will caused an error if IB is not connected.  It will
        # attempt to reconnect, but the order will need to be re-submited.
        # so we'll check the reconnection flag here and resubmit.
        if self.reconnected:
            self.placeOrder(self.nextOrderId,
                        self.create_contract(ts_signal.symbol, 'stk'),
                        self.create_order(
                            TS2IB_ORDER_TYPE_MAP[ts_signal.order_type],
                            quantity,
                            ts_signal.action)
                        )
            self.reconnected = False

        self.log_all(' '.join(["sent IB:", self.account_id, ts_signal.action,
                               str(quantity), ts_signal.symbol,
                               '@', ts_signal.order_type]))
        self.nextOrderId += 1


if __name__ == '__main__':
    # print 'acct update...'
    # con.reqAccountUpdates(1, '')
    # sleep(1)

    ib = IBWrapper({'server': 'localhost', 'port': 7496, 'sig_multiplier': 1})
    ib.connect()

    # Create an order ID which is 'global' for this session. This
    # will need incrementing once new orders are submitted.
    order_id = ib.nextOrderId

    print ">>> order id is", order_id

    # Create a contract 
    contract = ib.create_contract('gld', 'stk')

    # create order
    order = ib.create_order('mkt', 200, 'sell')

    # Use the connection to the send the order to IB
    ret = ib.placeOrder(order_id, contract, order)

    print "placeOrder returned: ", ret
    sleep(1)
    # print 'disconnected', con.disconnect()
    # sleep(3)
    # print 'reconnected', con.reconnect()
    print 'disconnected', ib.disconnect()
    sleep(1)
