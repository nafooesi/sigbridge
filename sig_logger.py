import os
import logging
from logging.handlers import TimedRotatingFileHandler


class SigLogger():

    def __init__(self, name, uilogger=None):
        if not os.path.isdir('logs'):
            os.makedirs('logs')

        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # create file, formatter and add it to the handlers
        fh = TimedRotatingFileHandler('logs/' + name + '.log', when='d',
                                      interval=1, backupCount=10)
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(process)d - %(name)s '
                                      '(%(lineno)d) %(levelname)s: %(message)s',
                                      "%Y-%m-%d %H:%M:%S")
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        self.uilogger = uilogger

    def log_all(self, message, level='info'):
        if level == 'info':
            self.logger.info(message)
            if self.uilogger:
                self.uilogger.info(message)
        else:
            self.logger.error(message)
            if self.uilogger:
                self.uilogger.error(message)

    def info(self, msg):
        self.logger.info(msg)

    def error(self, msg):
        self.logger.error(msg)
