#!/usr/bin/env python3
"""Tiny local server for Gains Brain. Stdlib only.

Serves index.html and stores everything in data.json next to this file.
If calendar_url.txt holds a Google Calendar secret iCal address, workouts
moved or deleted in that calendar are sent to the page via /api/schedule.
Run: python3 server.py [port]
"""
import json
import os
import re
import socket
import sys
import urllib.request
from datetime import date, datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
SEED = os.path.join(HERE, "seed.json")
CAL_URL = os.path.join(HERE, "calendar_url.txt")
WORKOUT_TITLE = re.compile(r"^billy (lifting|muay thai)\b", re.I)
_cache = {"body": None}  # last good result, used if Google can't be reached


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def do_GET(self):
        if self.path == "/api/data":
            path = DATA if os.path.exists(DATA) else SEED
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/schedule":
            body = json.dumps(schedule()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ("/", "/index.html"):
            self.path = "/index.html"
            super().do_GET()
        else:
            self.send_error(404)

    def do_PUT(self):
        if self.path != "/api/data":
            return self.send_error(404)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            json.loads(raw)
        except ValueError:
            return self.send_error(400, "invalid JSON")
        tmp = DATA + ".tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, DATA)  # atomic, so a crash never leaves half a file
        self.send_response(204)
        self.end_headers()
        print("saved", self.log_date_time_string(), flush=True)

    def log_message(self, fmt, *args):
        pass


def parse_ics(text):
    """Return VEVENTs as dicts of NAME -> list of (params, value)."""
    lines = re.sub(r"\r?\n[ \t]", "", text).splitlines()  # unfold continuation lines
    events, ev = [], None
    for line in lines:
        if line == "BEGIN:VEVENT":
            ev = {}
        elif line == "END:VEVENT":
            events.append(ev)
            ev = None
        elif ev is not None and ":" in line:
            head, value = line.split(":", 1)
            name, *params = head.split(";")
            ev.setdefault(name.upper(), []).append((dict(p.split("=", 1) for p in params if "=" in p), value))
    return events


def local_date(params, value):
    """Turn an iCal date/datetime into a date in this computer's time zone."""
    if params.get("VALUE") == "DATE" or len(value) == 8:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    dt = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        dt = dt.replace(tzinfo=timezone.utc)
    elif "TZID" in params:
        dt = dt.replace(tzinfo=ZoneInfo(params["TZID"]))
    else:
        return dt.date()
    return dt.astimezone().date()


def sun0(d):
    return (d.weekday() + 1) % 7  # Sun=0 … Sat=6, matching the page


def schedule():
    """Workouts moved or deleted in the calendar, keyed by their original weekday."""
    if not os.path.exists(CAL_URL):
        return {"ok": False, "error": "not set up yet"}
    try:
        with open(CAL_URL) as f:
            url = f.read().strip()
        with urllib.request.urlopen(url, timeout=10) as r:
            events = parse_ics(r.read().decode("utf-8"))
    except Exception as e:
        return _cache["body"] or {"ok": False, "error": "couldn't reach calendar (%s)" % type(e).__name__}

    moves, cancels = [], []
    for ev in events:
        title = ev.get("SUMMARY", [({}, "")])[0][1].replace("\\,", ",")
        if not WORKOUT_TITLE.match(title):
            continue
        if "RECURRENCE-ID" in ev:  # one occurrence of a repeating event that was changed
            orig = local_date(*ev["RECURRENCE-ID"][0])
            if ev.get("STATUS", [({}, "")])[0][1].upper() == "CANCELLED":
                cancels.append({"date": orig.isoformat(), "day": sun0(orig), "title": title})
            else:
                new = local_date(*ev["DTSTART"][0])
                if new != orig:
                    moves.append({"from": orig.isoformat(), "to": new.isoformat(), "day": sun0(orig), "title": title})
        for params, value in ev.get("EXDATE", []):  # occurrences deleted from a repeating event
            for v in value.split(","):
                d = local_date(params, v)
                cancels.append({"date": d.isoformat(), "day": sun0(d), "title": title})

    _cache["body"] = {"ok": True, "moves": moves, "cancels": cancels}
    return _cache["body"]


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no packets sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "localhost"


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8642
    print("Gains Brain running:")
    print("  this computer: http://localhost:%d" % port)
    print("  your phone:    http://%s:%d  (same Wi-Fi)" % (lan_ip(), port), flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
