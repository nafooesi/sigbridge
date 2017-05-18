import httplib
import urllib
import json


class Slack:
    def __init__(self):
        web_hook_url = 'hooks.slack.com'
        self.conn = httplib.HTTPSConnection(web_hook_url)

    def send(self, message):
        payload = {
            "channel": '#sigbridge',
            "username": "sb-bot",
            "icon_emoji": ":satellite:",
            "text": message
        }
        self.conn.request(
            "POST", "/services/T2GLAPJHM/B4H2LRVS9/7fSoJ9VIrY5v5E0TQvML5kgC",
            urllib.urlencode({
                'payload': json.dumps(payload)
            }),
            {"Content-type": "application/x-www-form-urlencoded"}
        )

        return self.conn.getresponse()

if __name__ == '__main__':
    Slack().send("Hi there, I'm a robot added by Jay!! Reporting from SigBridge.")
