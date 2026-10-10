# Gains Brain

A small mobile web app for tracking my workout plan, weights, and reps. It reads workout moves from Google Calendar.

## Run

```
python3 server.py
```

Then open the printed address on your phone (same Wi-Fi). Needs Python 3.9+ and nothing else.

## Files

- `index.html`: the app
- `server.py`: serves the app, saves data, and reads the calendar
- `seed.json`: the starting plan, used when `data.json` doesn't exist yet
- `data.json`: your plan and log (created on first save, not in git)
- `calendar_url.txt`: optional Google Calendar secret iCal address (not in git)
