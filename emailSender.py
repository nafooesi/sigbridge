from smtplib import SMTP
from email.mime.text import MIMEText
import json
import socket
import sys


class EmailSender:
    def __init__(self, server, port, from_addr, logger):

        self.from_addr = from_addr
        self.logger = logger

        try:
            self.server = SMTP(server, port, timeout=3)
        except socket.timeout:
            self.logger.error("Error: server connection timed out.")
        except socket.gaierror:
            self.logger.error("Error: unknown server name: %s" % server)
        except socket.error:
            self.logger.error("Error: Connection refused for %s" % server)

    def send(self, to_addr, subj, body):
        msg = MIMEText(body)
        msg['Subject'] = subj
        msg['From'] = self.from_addr
        msg['To'] = ','.join(to_addr)

        try:
            self.server.sendmail(self.from_addr, to_addr, msg.as_string())
            self.logger.info("Emailed to: %s" % to_addr[0])
        except:
            self.logger.error("to_addr", to_addr, " has unexpected error:", sys.exc_info()[0])

    def quit(self):
        self.server.quit()
