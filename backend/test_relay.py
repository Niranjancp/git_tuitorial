import base64, json
from relay import Relay

cfg = json.load(open('relay_config.example.json'))
sent = []
r = Relay(cfg, lambda t, p: sent.append((t, json.loads(p))))

def up(eui, text, port=2, fcnt=1):
    return json.dumps({'deviceInfo': {'devEui': eui}, 'fPort': port, 'fCnt': fcnt,
                       'data': base64.b64encode(text.encode()).decode()}).encode()

K7, B2 = '0000000000000001', '0000000000000002'
r.handle_uplink(up(K7, 'b2:hello'))                         # lower-case ID is fine
t, p = sent[-1]
assert t.endswith(f'/device/{B2}/command/down') and p['devEui'] == B2 and p['fPort'] == 10 and p['confirmed'] is False
assert base64.b64decode(p['data']) == b'K7:hello'            # sender tag stamped, recipient sees K7

n = len(sent); r.handle_uplink(up(K7, 'b2:hello')); assert len(sent) == n     # duplicate fCnt ignored
r.handle_uplink(up(K7, '\x00', port=3, fcnt=2)); assert len(sent) == n        # poll uplink ignored
r.handle_uplink(up(K7, 'ZZ:hi', fcnt=3))                                      # unknown ID -> notice to sender
assert sent[-1][1]['devEui'] == K7 and base64.b64decode(sent[-1][1]['data']) == b'No such ID ZZ'
n = len(sent); r.handle_uplink(up(K7, 'K7:me', fcnt=4)); assert len(sent) == n  # to self ignored
r.handle_uplink(up(K7, 'plain', fcnt=5)); assert len(sent) == n                 # untagged ignored
r.handle_uplink(up('00000000000000ff', 'B2:x')); assert len(sent) == n          # unregistered device ignored
r.handle_uplink(up(B2, 'k7:' + 'x' * 80, fcnt=1))
assert len(base64.b64decode(sent[-1][1]['data'])) == 48                         # capped
r.handle_uplink(b'not json'); print('relay tests ok')
