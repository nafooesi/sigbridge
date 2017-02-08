class TradeStationSignal:
    action = None
    sig_type = None
    symbol = None
    quantity = 0
    order_type = None
    account_name = None
    order_id = None

    def __init__(self, data):
        """
        Parses email data into wanted attributes
        """
        subject_key = 'tradestation - '

        if data:
            for line in data.split('\n'):
                line = line.strip().lower()
                if line.startswith('subject:'):
                    # ensure this email is intended
                    if subject_key not in line:
                        print "Error: unrecognized subject:", line
                        return
                    else:
                        if "new order has been placed" in line:
                            self.sig_type = 'opened'
                        elif "order has been filled" in line:
                            self.sig_type = 'filled'
                        elif "test message" in line:
                            print "TradeStation test email received!"
                            return
                elif line.startswith('order:'):
                    line = line.replace('buy to cover', 'buy')
                    line = line.replace('sell short', 'sell')
                    line = line.replace(',', '')
                    params = line.split(' ')
                    self.action = params[1]
                    if self.sig_type == 'opened':
                        self.quantity = int(params[2])
                    self.symbol = params[3]
                    self.order_type = params[5]
                elif line.startswith('qty filled:'):
                    line = line.replace(',', '')
                    params = line.split(' ')
                    self.quantity = int(params[2])
                elif line.startswith('account:'):
                    params = line.split(' ')
                    self.account_name = params[1]
                elif line.startswith('order#:'):
                    params = line.split(' ')
                    self.order_id = params[1]

    def verify_attributes(self):
        if not self.symbol:
            print "Error: no symbol found!"
            return False
        if not self.action or self.action not in ['sell', 'buy']:
            print "Error: unexpected action: ", self.action
            return False
        if not self.order_type or self.order_type not in ['market']:
            print "Error: unexpected order type: ", self.order_type
            return False
        if not self.quantity or self.quantity <= 0:
            print "Error: unexpected quantity: ", self.quantity
            return False
        if not self.account_name:
            print "Error: no account name!"
            return False
        if not self.order_id:
            print "Error: no order id!"
            return False
        return True
