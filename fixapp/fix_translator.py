import json
import pprint as pp

class FixTranslator():
    def __init__(self):
        self.fix_dict = {}
        self.load_dict()

    def load_dict(self):
        with open('./fixapp/dict_4.2.json', 'r') as df:
            data = json.loads(df.read())
            for f in data['Fields']:
                self.fix_dict[str(f['Tag'])] = f

    def translate(self, message):
        if "|35=0|" in message:
            # skip heartbeat message
            return

        data = message.split('|')
        for kv in data:
            if not kv or '=' not in kv:
                continue
            (k,v) = kv.split('=')
            m = self.fix_dict.get(str(k))
            if not m:
                print("key " + str(k) + " is not found in dict!")
                continue
            if "Val" in m:
                print(str(k) + "-" + str(m.get("Name")) + ': ' + m.get("Val").get(str(v)))
            else:
                print(str(k) + "-" + str(m.get("Name")) + ': ' + str(v))


if __name__=='__main__':
    ft = FixTranslator()
    with open('messages.fix') as df:
        for line in df:
            print("-"*80)
            ft.translate(line)
