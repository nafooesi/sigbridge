import httplib
import urllib
import json


class SlackWebHook:
    def __init__(self, webhook_path, url='hooks.slack.com', channel='#test_bed',
                    username="sb-bot", icon=":satellite:"):
        self.web_hook_url = url
        self.webhook_path = webhook_path
        self.channel = channel
        self.username = username
        self.icon = icon

    def send(self, message):
        if message:
            conn = httplib.HTTPSConnection(self.web_hook_url)
            payload = {
                "channel": self.channel,
                "username": self.username,
                "icon_emoji": self.icon,
                "text": message
            }

            conn.request(
                "POST", self.webhook_path,
                urllib.urlencode({
                    'payload': json.dumps(payload)
                }),
                {"Content-type": "application/x-www-form-urlencoded"}
            )
            return conn.getresponse()

if __name__ == '__main__':
    slack = Slack("/services/T2GLAPJHM/B4H2LRVS9/7fSoJ9VIrY5v5E0TQvML5kgC")
    slack.send("Hi there, I'm a robot added by Jay!! Reporting from SigBridge.")
