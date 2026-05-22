import asyncio
import csv
import time
import os
import argparse
from kasa import Device

POLLING_INTERVAL = 2  # seconds
CSV_FILENAME = "hs300_log.csv"


async def main(ip: str):
    strip = await Device.connect(host=ip)

    file_exists = os.path.isfile(CSV_FILENAME)

    with open(CSV_FILENAME, mode='a', newline='') as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow(["Timestamp", "Outlet_Alias", "Power_W", "Voltage_V", "Current_A", "Total_Wh"])
            print(f"Created {CSV_FILENAME} with headers.")

        print(f"Connected to {strip.alias}. Logging to {CSV_FILENAME}...")

        while True:
            try:
                loop_start = time.time()

                await strip.update()

                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

                for outlet in strip.children:
                    emeter = outlet.modules.get("Energy")
                    if emeter:
                        writer.writerow([
                            timestamp,
                            outlet.alias,
                            emeter.current_consumption,
                            emeter.voltage,
                            emeter.current,
                            emeter.consumption_total,
                        ])
                        print(f"{outlet.alias}: {emeter.current_consumption} W")

                file.flush()

                processing_time = time.time() - loop_start
                await asyncio.sleep(max(0, POLLING_INTERVAL - processing_time))

            except (KeyboardInterrupt, asyncio.CancelledError):
                print("\nStopped.")
                break
            except Exception as e:
                print(f"Error in loop (retrying in {POLLING_INTERVAL}s): {e}")
                await asyncio.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Log HS300 energy data to CSV.")
    parser.add_argument("--ip", default="10.1.10.149", help="IP address of the HS300 strip")
    args = parser.parse_args()
    asyncio.run(main(args.ip))
