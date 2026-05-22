import tkinter as tk
import customtkinter as ctk
import asyncio
import threading
import queue
import time
import csv
import os
import argparse
from collections import deque
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from datetime import datetime
from kasa import Device

DEFAULT_IP = "10.1.10.149"
MAX_POINTS = 300

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class AsyncKasaWorker(threading.Thread):
    def __init__(self, ip, data_queue, cmd_queue):
        super().__init__(daemon=True)
        self.ip = ip
        self.data_queue = data_queue
        self.cmd_queue = cmd_queue
        self.interval = 2.0
        self.running = True

    def run(self):
        asyncio.run(self._main_loop())

    async def _main_loop(self):
        dev = None

        while self.running:
            loop_start = time.time()

            while not self.cmd_queue.empty():
                cmd, val = self.cmd_queue.get()
                if cmd == "SET_INTERVAL":
                    self.interval = float(val)
                elif cmd == "STOP":
                    self.running = False
                    return

            try:
                if not dev:
                    print("Worker: Connecting to device...")
                    dev = await Device.connect(host=self.ip)
                    print(f"Worker: Connected to {dev.alias}")

                if dev:
                    await dev.update()
                    timestamp = datetime.now()

                    snapshot = {}
                    for child in dev.children:
                        energy = child.modules.get("Energy")
                        if energy:
                            snapshot[child.alias] = {
                                'power': energy.current_consumption,
                                'voltage': energy.voltage,
                                'current': energy.current,
                                'total': energy.consumption_total,
                            }

                    self.data_queue.put(("DATA", timestamp, snapshot))

            except Exception as e:
                self.data_queue.put(("ERROR", str(e), None))
                dev = None
                await asyncio.sleep(2)

            elapsed = time.time() - loop_start
            await asyncio.sleep(max(0.1, self.interval - elapsed))


class App(ctk.CTk):
    def __init__(self, ip: str):
        super().__init__()

        self.title("HS300 Power Monitor")
        self.geometry("1200x800")

        self.session_active = False
        self.session_file = None
        self.csv_writer = None
        self.start_time = None

        self.data_buffer = {
            i: {
                'x': deque(maxlen=MAX_POINTS),
                'y_power': deque(maxlen=MAX_POINTS),
                'y_energy': deque(maxlen=MAX_POINTS),
            }
            for i in range(6)
        }
        self.outlet_configs = []
        self.initial_kwh = {}

        self.data_queue = queue.Queue()
        self.cmd_queue = queue.Queue()

        self.worker = AsyncKasaWorker(ip, self.data_queue, self.cmd_queue)
        self.worker.start()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_area()

        self.after(100, self._check_queue)

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(self.sidebar, text="HS300 Control", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)

        self.btn_session = ctk.CTkButton(self.sidebar, text="START SESSION", fg_color="green", command=self._toggle_session)
        self.btn_session.pack(pady=10, padx=20, fill="x")

        self.lbl_status = ctk.CTkLabel(self.sidebar, text="Ready", text_color="gray")
        self.lbl_status.pack(pady=(0, 20))

        ctk.CTkLabel(self.sidebar, text="Polling Interval (s)").pack(pady=(10, 0))
        self.slider_interval = ctk.CTkSlider(self.sidebar, from_=1, to=10, number_of_steps=9, command=self._update_interval)
        self.slider_interval.set(2)
        self.slider_interval.pack(pady=5, padx=20)
        self.lbl_interval = ctk.CTkLabel(self.sidebar, text="2.0s")
        self.lbl_interval.pack(pady=(0, 20))

        self.scroll_frame = ctk.CTkScrollableFrame(self.sidebar, label_text="Outlets")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        for i in range(6):
            f = ctk.CTkFrame(self.scroll_frame)
            f.pack(fill="x", pady=5)

            r1 = ctk.CTkFrame(f, fg_color="transparent")
            r1.pack(fill="x")

            show_var = tk.BooleanVar(value=True)
            ctk.CTkCheckBox(r1, text="", variable=show_var, width=24, command=self._update_chart_visibility).pack(side="left")

            name_var = tk.StringVar(value=f"Outlet {i+1}")
            ctk.CTkEntry(r1, textvariable=name_var, height=24, width=120).pack(side="left", padx=5)

            lbl = ctk.CTkLabel(f, text="-- W", font=ctk.CTkFont(size=16, weight="bold"), text_color="#4deeea")
            lbl.pack(anchor="e", padx=10)

            self.outlet_configs.append({"id": i, "name": name_var, "show": show_var, "label": lbl})

    def _build_main_area(self):
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        self.fig = Figure(figsize=(5, 5), dpi=100)
        self.fig.patch.set_facecolor('#2b2b2b')

        self.ax1 = self.fig.add_subplot(111)
        self.ax1.set_facecolor('#2b2b2b')
        self.ax1.set_ylabel("Power (W)", color='white')
        self.ax1.tick_params(axis='y', colors='white')
        self.ax1.tick_params(axis='x', colors='white')

        self.ax2 = self.ax1.twinx()
        self.ax2.set_ylabel("Energy (kWh)", color='cyan')
        self.ax2.tick_params(axis='y', colors='cyan')

        for ax in [self.ax1, self.ax2]:
            for spine in ax.spines.values():
                spine.set_color('white')

        self.ax1.grid(True, linestyle='--', alpha=0.3)

        self.colors = ['#FF5733', '#33FF57', '#3357FF', '#F333FF', '#33FFF6', '#F6FF33']
        self.lines_power = []
        self.lines_energy = []

        for i in range(6):
            line, = self.ax1.plot([], [], label=f"Outlet {i+1} (W)", color=self.colors[i], linewidth=2)
            self.lines_power.append(line)
            line2, = self.ax2.plot([], [], linestyle='--', color=self.colors[i], alpha=0.7)
            self.lines_energy.append(line2)

        self._update_legend()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.main_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _update_legend(self):
        self.ax1.legend(loc='upper left', facecolor='#2b2b2b', edgecolor='white', labelcolor='white')

    def _update_interval(self, val):
        val = int(val)
        self.lbl_interval.configure(text=f"{val}.0s")
        self.cmd_queue.put(("SET_INTERVAL", val))

    def _update_chart_visibility(self):
        self._redraw_chart()

    def _toggle_session(self):
        if not self.session_active:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_{timestamp_str}.csv"

            self.session_file = open(filename, 'w', newline='')
            self.csv_writer = csv.writer(self.session_file)
            self.csv_writer.writerow(["Timestamp", "Outlet", "Power_W", "Voltage_V", "Current_A", "Relative_Total_kWh"])

            self.session_active = True
            self.start_time = time.time()
            self.initial_kwh = {}

            for i in range(6):
                self.data_buffer[i]['x'].clear()
                self.data_buffer[i]['y_power'].clear()
                self.data_buffer[i]['y_energy'].clear()

            self.btn_session.configure(text="STOP SESSION", fg_color="red")
            self.lbl_status.configure(text=f"Recording: {filename}", text_color="#33FF57")

        else:
            self.session_active = False
            self.initial_kwh = {}
            if self.session_file:
                self.session_file.close()
                self.session_file = None

            self.btn_session.configure(text="START SESSION", fg_color="green")
            self.lbl_status.configure(text="Session Saved", text_color="white")

    def _check_queue(self):
        try:
            while True:
                msg = self.data_queue.get_nowait()
                type_, val1, val2 = msg if len(msg) == 3 else (msg[0], msg[1], None)
                if type_ == "DATA":
                    self._process_data(val1, val2)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._check_queue)

    def _process_data(self, timestamp, snapshot):
        current_time_rel = time.time() - self.start_time if self.session_active else 0

        for idx, (name, data) in enumerate(snapshot.items()):
            if idx >= 6:
                break

            p = data['power']
            total_abs = data['total']

            self.outlet_configs[idx]['label'].configure(text=f"{p:.1f} W")

            if self.session_active:
                if idx not in self.initial_kwh:
                    self.initial_kwh[idx] = total_abs

                rel_kwh = total_abs - self.initial_kwh[idx]

                self.data_buffer[idx]['x'].append(current_time_rel)
                self.data_buffer[idx]['y_power'].append(p)
                self.data_buffer[idx]['y_energy'].append(rel_kwh)

                self.csv_writer.writerow([
                    timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    self.outlet_configs[idx]['name'].get(),
                    p,
                    data['voltage'],
                    data['current'],
                    rel_kwh,
                ])

        if self.session_active:
            self._redraw_chart()

    def _redraw_chart(self):
        has_data = False
        max_x = 0

        for i in range(6):
            cfg = self.outlet_configs[i]
            x_data = list(self.data_buffer[i]['x'])

            if cfg['show'].get() and x_data:
                self.lines_power[i].set_data(x_data, list(self.data_buffer[i]['y_power']))
                self.lines_energy[i].set_data(x_data, list(self.data_buffer[i]['y_energy']))
                self.lines_power[i].set_label(cfg['name'].get())
                max_x = max(max_x, x_data[-1])
                has_data = True
            else:
                self.lines_power[i].set_data([], [])
                self.lines_energy[i].set_data([], [])

        if has_data:
            self.ax1.set_xlim(left=max(0, max_x - 60), right=max(10, max_x + 5))
            self.ax1.relim()
            self.ax1.autoscale_view(scalex=False, scaley=True)
            self.ax2.relim()
            self.ax2.autoscale_view(scalex=False, scaley=True)
            self._update_legend()
            self.canvas.draw_idle()

    def on_closing(self):
        self.cmd_queue.put(("STOP", None))
        self.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HS300 Power Monitor GUI")
    parser.add_argument("--ip", default=DEFAULT_IP, help="IP address of the HS300 strip")
    args = parser.parse_args()

    app = App(ip=args.ip)
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
