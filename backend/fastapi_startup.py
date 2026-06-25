from database import init_db, get_all_stations, get_latest_reading, get_recent_readings

# Should return 7 station dicts
stations = get_all_stations()
print(len(stations), stations[0])

# Should return a dict with pm25 key
reading = get_latest_reading("Peenya")
print(reading)

# Should return list of ~48 dicts
history = get_recent_readings("Peenya", n=48)
print(len(history), history[-1]["pm25"])  # last item = most recent