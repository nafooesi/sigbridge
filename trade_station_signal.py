################################################################################
# This is class that translates TradeStation Email into actionable signals.
# sample TS email content:
"""
Date: 17 Sep 2019 19:50:20 UTC
From:  <xxxxx@roadrunner.com>
X-Priority: 3 (Normal)
To: <xxxxx@roadrunnerl.com>
Subject: TradeStation - Order has been filled for TQQQ
MIME-Version: 1.0
Content-type: text/plain; charset="US-ASCII"
Content-Transfer-Encoding: 7bit
TradeStation - Order has been filled for TQQQ
    Order: Buy 300 TQQQ @ Market
    Qty Filled: 300
    Filled Price: 65.2000
    Duration: Day
    Route: Intelligent
    Account: SIMXXXX
    Order#: 5-5733-7770
"""
################################################################################
import re


class TradeStationSignal:

    def __init__(self, data, conf):
        """
        Parses email data into wanted attributes
        """
        self.action = None
        self.sig_type = None
        self.symbol = None
        self.quantity = 0
        self.order_type = None
        self.account_name = None
        self.order_id = None
        self.price = 0
        self.sec_type = 'STK' # default to stock
        self.future_regex = conf.get('future_regex')

        if data:
            for line in data.split('\n'):
                line = line.strip().lower()
                if line.startswith('subject:'):
                    self._parse_subject(line)
                elif line.startswith('order:'):
                    self._parse_order(line)
                elif line.startswith('qty filled:'):
                    self._parse_qty(line)
                elif line.startswith('filled price:'):
                    self._parse_price(line)
                elif line.startswith('account:'):
                    params = line.split(' ')
                    self.account_name = params[1]
                elif line.startswith('order#:'):
                    params = line.split(' ')
                    self.order_id = params[1]

    def _parse_subject(self, line):
        # ensure this email is intended
        if 'tradestation - ' not in line:
            print("Error: unrecognized subject: %s" % line)
        elif "new order has been placed" in line:
            self.sig_type = 'opened'
        elif "order has been filled" in line:
            self.sig_type = 'filled'
        elif "test message" in line:
            print("TradeStation test email received!")
    
    def _parse_order(self, line):
        line = line.replace('buy to cover', 'buy')
        line = line.replace('sell short', 'sell')
        line = line.replace(',', '')
        params = line.split(' ')
        self.action = params[1]
        if self.sig_type == 'opened':
            self.quantity = int(params[2])
        self.symbol = params[3].upper()
        if self.symbol and re.match(self.future_regex, self.symbol):
            # detect future contract from symbol and converts it to ib's symbol
            self.sec_type = 'FUT'
            self.symbol = self.symbol[0:-2] + self.symbol[-1]
        self.order_type = params[5]

    def _parse_qty(self, line):
        line = line.replace(',', '')
        params = line.split(' ')
        self.quantity = int(params[2])

    def _parse_price(self, line):
        params = line.split(' ')
        self.price = float(params[2])

    def verify_attributes(self):
        if not self.symbol:
            print("Error: no symbol found!")
            return False
        if not self.action or self.action not in ['sell', 'buy']:
            print("Error: unexpected action: %s" % self.action)
            return False
        if not self.order_type or self.order_type not in ['market']:
            print("Error: unexpected order type: %s" % self.order_type)
            return False
        if not self.quantity or self.quantity <= 0:
            print("Error: unexpected quantity: %d" % self.quantity)
            return False
        if not self.account_name:
            print("Error: no account name!")
            return False
        if not self.order_id:
            print("Error: no order id!")
            return False
        return True
