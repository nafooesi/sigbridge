from smtplib import SMTP
from email.mime.text import MIMEText
import json
import socket
import sys


class EmailSender:
    def __init__(self, host, port, from_addr, logger):

        self.host = host
        self.port = port
        self.from_addr = from_addr
        self.logger = logger

    def connect(self):
        try:
            self.server = SMTP(self.host, self.port, timeout=3)
        except socket.timeout:
            self.logger.error("Error: host connection timed out.")
        except socket.gaierror:
            self.logger.error("Error: unknown host name: %s" % host)
        except socket.error:
            self.logger.error("Error: Connection refused for %s" % host)

    def send(self, to_addr, subj, body):
        msg = MIMEText(body)
        msg['Subject'] = subj
        msg['From'] = self.from_addr
        msg['To'] = ','.join(to_addr)

        try:
            self.server.sendmail(self.from_addr, to_addr, msg.as_string())
            self.logger.info("Emailed to: %s" % to_addr[0])
        except:
            self.logger.error("to_addr "+ ','.join(to_addr) + " has unexpected error: " + str(sys.exc_info()[0]))

    def quit(self):
        self.server.quit()
