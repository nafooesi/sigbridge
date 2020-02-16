import socket
from time import sleep
from smtplib import SMTP
from email.mime.text import MIMEText


class EmailSender:
    def __init__(self, host, port, from_addr, logger):
        self.host = host
        self.port = port
        self.from_addr = from_addr
        self.logger = logger
        self.server = None
        self.max_sleep_time = 32   # max sleep time in sec to allow retry

    def connect(self):
        try:
            self.server = SMTP(self.host, self.port, timeout=3)
        except socket.timeout:
            self.logger.error("Error: host connection timed out.")
        except socket.gaierror:
            self.logger.error("Error: unknown host name: %s" % self.host)
        except socket.error:
            self.logger.error("Error: Connection refused for %s" % self.host)

    def send(self, to_addr, subj, body):
        msg = MIMEText(body)
        msg['Subject'] = subj
        msg['From'] = self.from_addr
        msg['To'] = ','.join(to_addr)
        sleep_time = 1

        while True:
            # Allow retry of server disconnect
            try:
                self.server.sendmail(self.from_addr, to_addr, msg.as_string())
                self.logger.info("Emailed to: %s" % to_addr[0])
                break
            except:
                if sleep_time <= self.max_sleep_time:
                    sleep(sleep_time)
                    sleep_time *= 2
                    self.logger.warning("SMTP disconnected, will retry...")
                    self.connect()
                else:
                    self.logger.error("to_addr " + ','.join(to_addr) +
                                      " max retry on disconect reached")
                    break

    def quit(self):
        self.server.quit()
