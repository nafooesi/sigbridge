from time import sleep
from smtplib import SMTP
from Queue import Queue
from email.mime.text import MIMEText


class EmailSender:
    def __init__(self, host, port, from_addr, logger, max_retry=7, queue_time=5):
        self.host = host
        self.port = port
        self.from_addr = from_addr
        self.logger = logger
        self.server = None
        self.msg_queue = Queue()        # used to queue messages
        self.max_retry = max_retry      # max retry count for sending email
        self.queue_time = queue_time    # queue wait time in seconds

    def connect(self):
        self.server = SMTP(self.host, self.port, timeout=3)

    def send(self, to_addr, subj, body):
        msg = MIMEText(body)
        msg['Subject'] = subj
        msg['From'] = self.from_addr
        msg['To'] = ','.join(to_addr)
        retry_sec = 0

        while True:
            try:
                if not self.test_conn_open():
                    self.connect()
                self.server.sendmail(self.from_addr, to_addr, msg.as_string())
                retry_sec += 1
                self.logger.info("Emailed to: %s" % to_addr[0])
                break
            except Exception as e:
                self.logger.error(e)
                if retry_sec >= self.max_retry:
                    self.logger.error("Max retry reached. Fails to send email!")
                    break
                self.logger.error("retrying ...")
                sleep(retry_sec * 2)

    def daemon_sender(self, email_list):
        slept_time = 0
        while True:
            if not self.msg_queue.empty():
                # Only start sleep timer when there's message in queue
                slept_time += 1

            if slept_time >= self.queue_time:
                # send queued emails since queuing time has exceeded
                msg = ''
                while not self.msg_queue.empty():
                    msg += self.msg_queue.get() + '\n'
                """
                Mobile phone receiving server seems to block email that
                does not have matching "to" header to actual addressee.
                This makes it impossible to send bulk email in BCC fashion since putting
                addressee in bcc header defeats the purpose of bcc.
                Unfortunately, we'll have to send it one by one to ensure privacy.
                """
                for email in email_list:
                    self.send([email], 'SigBridge Alert', msg)

                # reset timer
                slept_time = 0

            sleep(1)

    def queue_trade(self, trade_str):
        self.msg_queue.put(trade_str)

    def test_conn_open(self):
        try:
            status = self.server.noop()[0]
        except:  # smtplib.SMTPServerDisconnected
            status = -1
        return True if status == 250 else False

    def quit(self):
        self.server.quit()
