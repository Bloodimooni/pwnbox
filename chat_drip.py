#!/usr/bin/env python3
import json, os, sqlite3, time

DB = '/data/corpchat.db'
START_FILE = '/data/container_start'
STATE_FILE = '/data/drip_state'
MSGS_FILE = '/app/drip_messages.json'

def main():
    if not os.path.exists(START_FILE):
        return
    with open(START_FILE) as f:
        start_ts = float(f.read().strip())
    elapsed = (time.time() - start_ts) / 60.0

    state = 0
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            try:
                state = int(f.read().strip())
            except ValueError:
                state = 0

    with open(MSGS_FILE) as f:
        messages = json.load(f)

    db = sqlite3.connect(DB)
    inserted = 0
    new_state = state
    for i, msg in enumerate(messages):
        if i < state:
            continue
        if msg['offset_minutes'] > elapsed:
            break
        db.execute(
            "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
            (msg['channel_id'], msg['user_id'], msg['content'])
        )
        new_state = i + 1
        inserted += 1
    db.commit()
    db.close()

    if new_state != state:
        with open(STATE_FILE, 'w') as f:
            f.write(str(new_state))
    if inserted:
        print(f'[drip] Inserted {inserted} message(s). State now: {new_state}')

if __name__ == '__main__':
    main()
