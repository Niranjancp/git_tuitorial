#!/usr/bin/env python3
"""
LoRa Messenger relay (backend half of the contact system).

Protocol shared with the display (lora_ui):
  uplink payload   "<TO>:<text>"      the display puts the CONTACT's ID in front of every message
  downlink payload "<FROM>:<text>"    the relay puts the SENDER's ID in front, so the receiving
                                      display files it under the contact that has that ID
  IDs are 1-4 letters/digits, not case-sensitive (the relay always writes them in upper case).
  Uplinks on poll_port (default 3) are the "check messages" button; they carry no message.

The relay needs exactly one table: which device owns which ID ("users" in the config).
Contacts themselves live only on the displays, so adding a contact never needs a relay change;
a new PERSON just needs an entry in "users".

Default wiring is ChirpStack v4's MQTT integration (JSON). Change uplink_topic / downlink_topic
and the two small functions parse_uplink() / build_downlink() for another network server.

Class A reminder: a downlink goes out only after the recipient's next uplink, so the recipient
taps the refresh icon to collect it.

Run:   pip install paho-mqtt     then     python3 relay.py relay_config.json
"""
import base64
import json
import re
import sys

TAG_RE = re.compile(r'^([A-Za-z0-9]{1,4}):(.*)$', re.S)


def log(*a):
    print(*a, flush=True)


def printable(b: bytes) -> str:
    return ''.join(chr(c) if 32 <= c <= 126 else ' ' for c in b)


# ---------- network-server adapter (ChirpStack v4, JSON) ----------
def parse_uplink(payload: bytes):
    """-> (dev_eui_lowercase, f_port, f_cnt_or_None, raw_bytes)"""
    ev = json.loads(payload)
    eui = ev['deviceInfo']['devEui'].lower()
    return eui, ev.get('fPort'), ev.get('fCnt'), base64.b64decode(ev.get('data') or '')


def build_downlink(cfg, dev_eui: str, data: bytes):
    """-> (topic, payload_json_string)"""
    topic = cfg['downlink_topic'].format(app=cfg['application_id'], eui=dev_eui)
    body = {
        'devEui': dev_eui,                       # ChirpStack v4: must match the topic
        'confirmed': False,
        'fPort': cfg.get('downlink_port', 10),   # must be > 0; the display ignores port 0 only
        'data': base64.b64encode(data).decode('ascii'),
    }
    return topic, json.dumps(body)


# ---------- relay logic ----------
class Relay:
    def __init__(self, cfg, publish):
        self.cfg = cfg
        self.publish = publish                   # publish(topic, payload_str)
        self.id_to_eui = {k.upper(): v.lower() for k, v in cfg['users'].items()}
        self.eui_to_id = {}
        for uid, eui in self.id_to_eui.items():
            if eui in self.eui_to_id:
                raise ValueError(f'device {eui} is listed under two IDs')
            if not re.fullmatch(r'[A-Z0-9]{1,4}', uid):
                raise ValueError(f'ID {uid!r} must be 1-4 letters/digits')
            self.eui_to_id[eui] = uid
        self.last_fcnt = {}

    def _send(self, dev_eui, text):
        data = text.encode('ascii', 'replace')[: self.cfg.get('max_downlink_bytes', 48)]
        topic, payload = build_downlink(self.cfg, dev_eui, data)
        self.publish(topic, payload)

    def handle_uplink(self, payload: bytes):
        try:
            eui, port, fcnt, raw = parse_uplink(payload)
        except Exception as e:                   # not an uplink we understand
            log('ignored malformed uplink:', e)
            return

        if port == self.cfg.get('poll_port', 3):
            log(f'poll from {eui} (no message)')
            return
        if fcnt is not None:                     # same frame delivered twice
            if self.last_fcnt.get(eui) == fcnt:
                return
            self.last_fcnt[eui] = fcnt

        sender = self.eui_to_id.get(eui)
        if sender is None:
            log(f'uplink from unregistered device {eui}: add it to "users"')
            return

        text = printable(raw).strip()
        m = TAG_RE.match(text)
        if not m:
            log(f'{sender}: untagged message ignored: {text!r}')
            return
        dest, body = m.group(1).upper(), m.group(2).strip()
        if not body:
            return

        dest_eui = self.id_to_eui.get(dest)
        if dest_eui is None:
            log(f'{sender} -> {dest}: unknown ID')
            self._send(self.id_to_eui[sender], f'No such ID {dest}')   # lands in "LoRa Radio" on the sender
            return
        if dest == sender:
            return
        log(f'{sender} -> {dest}: {body}')
        self._send(dest_eui, f'{sender}:{body}')


def main():
    import paho.mqtt.client as mqtt
    cfg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'relay_config.json'))
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)     # paho-mqtt 2.x
    except AttributeError:
        client = mqtt.Client()                                     # paho-mqtt 1.x
    m = cfg['mqtt']
    if m.get('username'):
        client.username_pw_set(m['username'], m.get('password', ''))

    relay = Relay(cfg, lambda topic, payload: client.publish(topic, payload, qos=0))
    sub = cfg.get('uplink_topic', 'application/{app}/device/+/event/up').format(app=cfg['application_id'])

    def on_connect(c, userdata, flags, rc, *extra):
        log('connected to broker, subscribing to', sub)
        c.subscribe(sub)

    def on_message(c, userdata, msg):
        relay.handle_uplink(msg.payload)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(m['host'], m.get('port', 1883), 60)
    client.loop_forever()


if __name__ == '__main__':
    main()
