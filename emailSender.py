import re
from time import sleep
from smtplib import SMTP
from Queue import Queue
from email.mime.text import MIMEText


REG_TXT = re.compile('\d{10}@.+')

class EmailSender:
    def __init__(self, host, port, from_addr, logger, max_retry=7, queue_time=5, send_opt=1):
        self.host = host
        self.port = port
        self.from_addr = from_addr
        self.logger = logger
        self.server = None
        self.msg_queue = Queue()        # used to queue messages
        self.max_retry = max_retry      # max retry count for sending email
        self.queue_time = queue_time    # queue wait time in seconds
        self.send_opt = send_opt

    def connect(self):
        self.server = SMTP(self.host, self.port, timeout=3)

    def send(self, to_addr, subj, body):
        if not to_addr:
            return

        msg = MIMEText(body)
        msg['Subject'] = subj
        msg['From'] = self.from_addr
        # If there're more than 1 address, we will send it bcc style, otherwise
        # it will be addressed normally.
        msg['To'] = self.from_addr if len(to_addr) > 1 else to_addr[0]
        retry_sec = 0

        while True:
            try:
                if not self.test_conn_open():
                    self.connect()
                self.server.sendmail(self.from_addr, to_addr, msg.as_string())
                retry_sec += 1
                if self.logger:
                    self.logger.info("Emailed to: %s" % ','.join(to_addr))
                else:
                    print("Emailed to: %s" % ','.join(to_addr))
                break
            except Exception as e:
                if self.logger:
                    self.logger.info(e)
                if retry_sec >= self.max_retry:
                    if self.logger:
                        self.logger.error(
                            "Max retry reached. Fails to send email!")
                    break
                if self.logger:
                    self.logger.info("retrying ...")
                sleep(retry_sec * 2)

    def daemon_sender(self, email_list):
        """Wait for message in the queue, and sends message every 5 seconds
        """
        subj = 'SigBridge Alert'
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

                if self.send_opt == 1:
                    # Sending every email in bcc style
                    self.send(email_list, subj, msg)
                elif self.send_opt == 2:
                    # send regular email in bcc style, but txt msg email
                    # is sent one at a time.
                    self.batch_sorter(email_list, subj, msg)
                else:
                    # default: send all emails one at a time.
                    for email in email_list:
                        self.send([email], subj, msg)

                # reset timer
                slept_time = 0
            sleep(1)

    def batch_sorter(self, email_list, subj, msg):
        """Sort email into two batches: regular and txt msg email.
           Regular email are sent all at once bcc style. Txt msg email
           is sent one by one.
        """
        txt_emails = []
        reg_emails = []
        for email in email_list:
            if REG_TXT.match(email):
                txt_emails.append(email)
            else:
                reg_emails.append(email)

        # send regular email
        self.send(reg_emails, subj, msg)

        # send txt msg email
        for txt in txt_emails:
           self.send([txt], subj, msg)


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

if __name__ == '__main__':
    smtp_server = 'mail.twc.com'
    smtp_port = 587
    sender = 'bchi15@roadrunner.com'
    addrs = ['bowei.chi@gmail.com', '6263198202@tmomail.net', 'nafooesi@gmail.com']
    body = 'Just testing out email for bcc addrs.'

    es = EmailSender(smtp_server, smtp_port, sender, None)
    # es.batch_sorter(addrs, body)
    es.send(addrs, 'bcc SigBridge Alert', body)
    

