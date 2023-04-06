"""
Wrapper module for Fix application.
"""
__all__ = ['BaseFixClient']
import pprint as pp
import datetime as dt
import time
import quickfix as fix

from fixapp.fix_translator import FixTranslator


def echo(f):
    def decorated(*args, **kwargs):
        print(" --- calling " + f.__name__)
        return f(*args, **kwargs)
    return decorated


class FixWrapper(fix.Application):

    def __init__(self, session_settings):
        super(FixWrapper, self).__init__()
        self.session_settings = session_settings

        self.orderID = 0
        self.execID  = 0
        self.settingsDic = {}
        self.sessionID = None

        # Keep track of orders and IDs
        self.ORDERS_DICT   = {}
        self.LASTEST_ORDER = {}

        # Keep track of orders and ids
        self.open_subs   = []
        self.open_orders = []

        self.fix_tran = FixTranslator()
        self.is_logged_in = False

    @staticmethod
    def unicode_fix(string):
        new_str = string.replace('\x01', '|')
        return new_str

    '''=========================================================================
    Internal message methdos
    '''
    def onCreate(self, sessionID):
        '''Improve this function later. Right now it expects exactly two 
           sessions which contain specific strings
        '''
        self.sessionID = sessionID
        self.settingsDic = self.session_settings.get(sessionID)
        print("created session id: " + sessionID.toString())
        return

    def onLogon(self, sessionID):
        print("Logon to session " + sessionID.toString())
        self.is_logged_in = True
        return


    def onLogout(self, sessionID):
        print("Logout from session " + sessionID.toString())
        self.is_logged_in = False
        return

    @echo
    def toAdmin(self, message, sessionID):
        msg_type    = message.getHeader().getField(fix.MsgType().getField())
        if msg_type == fix.MsgType_Logon:
            username = self.settingsDic.getString('SenderCompID')
            # password = self.settingsDic.getString('Password')
            #username = sessionID.getSenderCompID().getValue()
            message.setField(fix.Username(username))
            # message.setField(fix.Password(password))
        self.fix_tran.translate(self.unicode_fix(message.toString()))
        return

    @echo
    def fromAdmin(self, message, sessionID):
        fix_str = self.unicode_fix(message.toString())
        self.fix_tran.translate(fix_str)
        return

    @echo
    def toApp(self, message, sessionID):
        fix_str = self.unicode_fix(message.toString())
        self.fix_tran.translate(fix_str)
        return

    @echo
    def fromApp(self, message, sessionID):
        '''Capture Messages coming from the counterparty'''
        fix_str = self.unicode_fix(message.toString())
        self.fix_tran.translate(fix_str)
        return

    @echo
    def genOrderID(self):
    	self.orderID += 1
        #orderID = self.orderID
    	return str(self.orderID) + '-' + str(time.time())

    @echo
    def genExecID(self):
    	self.execID += 1
        #execID = self.execID
    	return str(self.execID) + '-' + str(time.time())

    @echo
    def _make_standard_header(self):
        '''Make a standard header for Fortex FIX 4.4 Server based on their instruction file.
        A standard header for Fortex has the following tags (first 6 tags must be in this exact order):
        *     8  - BeginString  - required
        *     9  - BodyLength   - required
        *     35 - MsgType      - required
        *     49 - SenderCompID - required
        *     56 - TargetCompID - required
        *     34 - MsgSeqNum    - required
        *     43 - PossDupFlag  - Not required (can be Y or N)
        *     52 - SendingTime  - required
        '''
        sender = self.settingsDic.getString('SenderCompID')
        target = self.settingsDic.getString('TargetCompID')
        msg = fix.Message()
        msg.getHeader().setField(fix.BeginString(fix.BeginString_FIX42))
        msg.getHeader().setField(fix.MsgType(fix.MsgType_Logon))
        msg.getHeader().setField(fix.SenderCompID(sender))
        msg.getHeader().setField(fix.TargetCompID(target))
        # Following line is a placeholder.
        # I am just trying to force quickfix to put this tag in this particular order
        # msg.getHeader().setField(fix.MsgSeqNum(3333))        
        # msg.getHeader().setField(fix.SendingTime(1))

        fix_str = self.unicode_fix(msg.toString())
        return msg


    '''=======================================================================
    Internally keep track of orders and subscriptions. (This might later be 
    moved to an external class)
    '''


    @echo
    def get_open_orders(self):
        return self.open_orders


    @echo
    def get_last_order(self):
        return self.open_orders[-1]


    @echo
    def close_order(self,id):
        self.open_orders.remove(id)


    @echo
    def add_order(self,id):
        self.open_orders.append(str(id))
        

    @echo
    def _record_json_order(self, msg, wanted_tags=[11,40,54,38,55,167]):
        order_object = {}

        #For now I am going to store the entire message as a string
        order_object['raw_msg'] = msg.toString()

        for tag in wanted_tags:
            order_object[tag] = msg.getField(tag)

        order_id = order_object.get(11) #tag for ClOrdID
        # add to list of order info using the ID as key
        self.ORDERS_DICT[order_id] = order_object  
        # remember the latest order for easier accessing
        self.LASTEST_ORDER = order_object  
        print("\n=====> Order recorded in memory with id = {}\n".format(order_id))

    
    @echo
    def _retrieve_json_order(self, id):
        if id == -1 or id == '-1' or id == 'latest':
            return self.LASTEST_ORDER
        return self.ORDERS_DICT[id]

    
    '''=========================================================================
    Message Templates
    '''
    @echo
    def _NewOrderSingle(self,kargs):
        '''
        _price       = kargs['44']          #Price
        _timeInForce = kargs['59']          #TimeInForce
        _orderQty    = kargs['38']          #OrderQty
        _asset       = kargs['55']          #Symbol
        _side        = kargs['43']          #Side
        _ordType     = kargs['40']          #OrdType
        _secType     = kargs['167']         #SecurityType
        '''
        _price       = float(kargs.get('44', 0))     # Price
        _asset       = kargs['55'].upper()           # Symbol
        _timeInForce = kargs.get('59', fix.TimeInForce_FILL_OR_KILL)  # TimeInForce
        # _timeInForce = kargs.get('59', fix.TimeInForce_GOOD_TILL_CANCEL)
        _orderQty    = float(kargs.get('38', 1))    # OrderQty
        _side        = kargs.get('54', fix.Side_BUY) # Side tag 54
        _ordType     = kargs.get('40', fix.OrdType_MARKET)  # OrdType
        _secType     = kargs.get('167', fix.SecurityType_COMMON_STOCK)         #SecurityType

        msg = self._make_standard_header()
        msg.getHeader().setField(fix.BeginString(fix.BeginString_FIX42))
        msg.getHeader().setField(fix.MsgType(fix.MsgType_NewOrderSingle)) #35=D
        msg.setField(fix.ClOrdID(self.genOrderID()))                 #11=Unique order

        # system complained of missing tag. This order is good for the day or for the session
        msg.setField(fix.TimeInForce(_timeInForce))   

        # added because system complained about missing tag. 
        # instead of 'FOR' it could be fix.SecurityType_FOR. 'FOR' is for forex
        msg.setField(fix.SecurityType(_secType))         

        #21=3 (Manual order, best execution)
        msg.setField(fix.HandlInst(fix.HandlInst_AUTOMATED_EXECUTION_ORDER_PRIVATE_NO_BROKER_INTERVENTION))
        msg.setField(fix.Symbol(_asset))      #55=SMBL
        msg.setField(fix.Side(_side))         #54=1 Buy
        msg.setField(fix.OrdType(_ordType))   #40=2 Limit order
        msg.setField(fix.OrderQty(_orderQty)) #38=100
        msg.setField(fix.Price(_price))       #tag 44 price
        time_stamp = int(time.time())
        msg.getHeader().setField(fix.SendingTime(1))
        msg.setField(fix.StringField(60,(dt.datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f"))[:-3]))

        return msg

    
    '''=========================================================================
    User interface
    '''
    @echo
    def buy(self,**kargs):
        kargs['54'] = fix.Side_BUY
        msg = self._NewOrderSingle(kargs)
        self._record_json_order(msg)
        fix.Session.sendToTarget(msg, self.sessionID)
    
    @echo
    def sell(self,**kargs):
        kargs['54'] = fix.Side_SELL
        msg = self._NewOrderSingle(kargs)
        self._record_json_order(msg)
        fix.Session.sendToTarget(msg, self.sessionID)

    @echo
    def limit_buy(self, **kargs):
        kargs['40'] = fix.OrdType_LIMIT
        kargs['54'] = fix.Side_BUY
        msg = self._NewOrderSingle(kargs)

        self._record_json_order(msg)
        fix.Sessions.sendToTarget(msg, self.sessionID)

    @echo
    def limit_sell(self, **kargs):
        kargs['40'] = fix.OrdType_LIMIT
        kargs['54'] = fix.Side_SELL
        msg = self._NewOrderSingle(kargs)

        self._record_json_order(msg)
        fix.Sessions.sendToTarget(msg, self.sessionID)

    @echo
    def cancel_order(self,**kargs):
        msg = self._OrderCancelRequest(kargs,wanted_tags=[11,40,54,38,55,167])
        fix.Session.sendToTarget(msg, self.sessionID)

    @echo
    def check_order_status(self,**kargs):
        msg = self._OrderStatusRequest(kargs)
        fix.Session.sendToTarget(msg, self.sessionID)

    @echo
    def logout(self):
        msg = fix.Message()
        msg.getHeader().setField(fix.BeginString(fix.BeginString_FIX42))
        msg.getHeader().setField(fix.MsgType(fix.MsgType_Logout))
        fix.Session.sendToTarget(msg, self.sessionID)

    
    def test_message(self):
        trade = self._make_standard_header()
        # added the following because system complained about missing tag.
        # instead of 'FOR' it could be fix.SecurityType_FOR. 'FOR' is for forex
        trade.setField(fix.SecurityType('FOR'))
        # system complained of missing tag. This order is good for the day or for the session
        trade.setField(fix.TimeInForce(fix.TimeInForce_GOOD_TILL_CANCEL))
        trade.setField(
            fix.HandlInst(fix.HandlInst_AUTOMATED_EXECUTION_ORDER_PRIVATE_NO_BROKER_INTERVENTION)
        ) #21=3 (Manual order, best execution)
        trade.setField(fix.Symbol('EUR/USD'))  #55=SMBL
        trade.setField(fix.Side(fix.Side_BUY)) #43=1 Buy
        trade.setField(fix.OrdType(fix.OrdType_MARKET)) #40=2 Limit order
        trade.setField(fix.OrderQty(10)) #38=100

        str_msg = trade.toString()
        return trade


if __name__ == '__main__':
    pass
