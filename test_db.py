import sqlite3
import json

def test():
    conn = sqlite3.connect('data/processauth.db')
    c = conn.cursor()
    c.execute("SELECT raw_json FROM events WHERE event_type='doc_diff' ORDER BY id DESC LIMIT 5")
    results = [json.loads(row[0]) for row in c.fetchall() if row[0]]
    
    with open('tmp_dump.json', 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    test()
