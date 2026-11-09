# LoRa Messenger v2: runtime contacts, saved history, matching relay

Folders: `lora_ui/` (display), `heltec_modem/` (modem), `backend/` (relay).
`heltec_modem/credentials.cpp` is NOT included (it was redacted in your handoff): keep your own.

## How contacts work (the part the display and the relay share)
- Every device has one short **ID** (1-4 letters/digits, not case-sensitive). The relay's `users` table maps ID -> devEUI. That is the only thing the backend needs.
- A contact on the display = a name + the other person's ID. You add it yourself: **Messages -> "+"**, type name, OK, type ID, OK.
- Sending to a contact puts that contact's ID in front: `B2:hi`. The relay rewrites the front to the *sender's* ID and queues `K7:hi` for B2's device. B2's display files it under the contact whose ID is K7.
- Received text from an ID that is not a contact lands in "LoRa Radio" with the ID visible (`ZZ:hi`), so you can see who to add. A message to an ID the relay does not know comes back as `No such ID ZZ` in "LoRa Radio".
- Delete a contact: **long-press its row** -> Delete. Its saved messages go with it.
- Limits: 8 contacts + "LoRa Radio", 12-char names, 4-char IDs, 40 bytes per message *including* `ID:` (the input box counter now shows the real limit per chat).

## Saved to flash (survives reboot and reflashing without "erase all flash")
- Contact table and the **last 5 messages of every chat** (including "LoRa Radio"), with their sent/failed state.
- RAM holds the same set: when a 6th message arrives in a chat, that chat's oldest is dropped.
- Uses the ESP32 `Preferences` (NVS) library that ships with the core: no new library. A chat's blob is rewritten only when that chat changes.
- Not saved: unread marks, inbox times (show `--` until new traffic), a message still "Sending..." at power-off (comes back as failed).

## Files
Display, new: `store.h/.cpp`, `ui_contacts.h/.cpp`. Display, changed: `config.h`, `app_data.*`, `app_types.h`, `lora_modem.*`, `ui_chat.*`, `ui_inbox.*`, `ui_keyboard.*`, `ui_nav.*`, `lora_ui.ino`.
Heltec: unchanged from the A+B merge (poll button support is included). `LORA_MAX_PAYLOAD` (display `config.h`) must equal `MAX_MSG_BYTES` (Heltec `app_config.h`): both 40.
Backend: `relay.py`, `relay_config.example.json`, `test_relay.py`.

## Setup notes
1. `lv_conf.h` must have `LV_USE_MSGBOX 1` (the delete dialog). It is on in the default template; check if you trimmed widgets.
2. Backend: `pip install paho-mqtt`, copy `relay_config.example.json` to `relay_config.json`, fill in the ChirpStack application ID, your devEUIs and their IDs, then `python3 relay.py relay_config.json`.
3. The relay assumes **ChirpStack v4 JSON over MQTT** (topics and field names confirmed against the ChirpStack docs). For TTN or another server change only `parse_uplink()`, `build_downlink()` and the two topics.
4. Class A still applies: the recipient taps the refresh icon to collect a queued message.

## Checked / not checked
- Checked on a PC with stubs: contact add/validation, tag routing, per-chat cap of 5, flash save/restore across a simulated reboot, delete and slot reuse (`lora_modem.cpp`, `app_data.cpp`, `store.cpp`); relay logic incl. duplicate, poll, unknown ID, truncation (`test_relay.py`).
- UI files only passed a syntax/identifier check against a stub LVGL, and nothing was run on the boards. Layout of the Add screen (fields sit above the 172 px keyboard) and the long-press delete need a look on the real display.

## Test checklist
1. Flash both boards. Messages -> PIN -> "+" -> name "Ben", ID "B2" -> OK, OK. Ben appears in the inbox.
2. Open Ben, send "hi". Heltec serial shows `UL#n: B2:hi`.
3. Start the relay with your device under some ID (say K7) and a second ID B2 (a second device, or just watch the relay log). Relay log: `K7 -> B2: hi`.
4. Queue `K7:yo` for your own device (MQTTBox, port 10, base64 `Szc6eW8=`), tap refresh. With a contact whose ID is K7 it lands there; otherwise in "LoRa Radio".
5. Send 7 messages to one contact, power-cycle: only the newest 5 are back. Long-press a contact, Delete, power-cycle: it stays gone.
