# TP-Link HS300 Power Meter

Python tools for logging and visualizing real-time energy data from a [TP-Link HS300](https://www.tp-link.com/us/home-networking/smart-plug/hs300/) smart power strip using the [python-kasa](https://github.com/python-kasa/python-kasa) library.

## Features

- **Headless logger** — polls all 6 outlets and appends readings to a CSV file
- **GUI monitor** — live power/energy chart with per-outlet controls, session recording, and configurable polling interval

## Requirements

- Python 3.10+
- TP-Link HS300 on the same local network
- Dependencies (install with pip):

```bash
pip install -r requirements.txt
```

## Usage

### Headless logger

```bash
python check_emeter_hs300.py --ip 10.1.10.149
```

Appends timestamped readings to `hs300_log.csv`. If the file doesn't exist, it is created with headers.

### GUI monitor

```bash
python hs300_gui.py --ip 10.1.10.149
```

- **START SESSION** — begins recording to a timestamped CSV and plots live data
- **STOP SESSION** — closes the CSV; the chart stays visible
- Use the **polling interval slider** to adjust how frequently the device is queried (1–10 s)
- Toggle individual outlets on/off with the checkboxes in the sidebar

### CSV columns

| Column | Description |
|---|---|
| `Timestamp` | Local time of the reading |
| `Outlet` / `Outlet_Alias` | Outlet name as configured on the device (or in the GUI) |
| `Power_W` | Instantaneous power in watts |
| `Voltage_V` | Voltage in volts |
| `Current_A` | Current in amps |
| `Total_Wh` / `Relative_Total_kWh` | Cumulative energy (logger: absolute Wh; GUI: relative kWh from session start) |

## Notes

- The HS300 must be accessible without cloud authentication (local access mode). If your device requires KLAP authentication, you may need to pass credentials via the `python-kasa` API.
- Both scripts use `--ip` with a default of `10.1.10.149`. Change the default in the source or always pass `--ip` explicitly.

## License

MIT
