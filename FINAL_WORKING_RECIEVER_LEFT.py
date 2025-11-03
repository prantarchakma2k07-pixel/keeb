import argparse
import threading
import serial
import time
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pynput.keyboard import Controller, Key
import re
import queue

# Mapping between matrix positions (row-major) and the human label we want to display.
# We'll use the same labels as the firmware mapping:
labels = [
    ["1", "X", "Shift", "C", "5"],
    ["A", "S", "3", "WIN", "SPACE"],
    ["Z", "W", "E", "4", "V"],
    ["CTRL", "2", "D", "R", "F"],
    ["SPACE", "B", "G", "Q", "T"]
]

# Mapping to actual host key events for pynput emulation.
# For modifier keys we pass Key.shift or Key.ctrl etc.
pynput_keymap = {
    "1": "1", "2":"2", "3":"3", "4":"4", "5":"5",
    "A":"a","B":"b","C":"c","D":"d","E":"e","F":"f","G":"g","Q":"q","R":"r","S":"s","T":"t","V":"v","W":"w","X":"x","Z":"z",
    "SPACE":"space",
    "Shift":"shift",
    "CTRL":"ctrl",
    "WIN":"cmd"   # may map to cmd (mac) or left super
}

# Helper to convert name to pynput Key/char
def to_pynput_key(name):
    if name == "SPACE": return Key.space
    if name == "Shift": return Key.shift
    if name == "CTRL": return Key.ctrl
    if name == "WIN": return Key.cmd
    # normal single-character keys:
    if len(name) == 1:
        return name.lower()
    return None

# SerialReader thread: reads incoming lines and pushes parsed boolean lists to a queue
class SerialReader(threading.Thread):
    def __init__(self, port, baud, out_queue):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self._stop = threading.Event()
        self.out_queue = out_queue
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
        except Exception as e:
            self.out_queue.put(("error", f"Cannot open serial port: {e}"))
            return

        self.out_queue.put(("info", f"Connected to {self.port}"))
        line_re = re.compile(r"K:\[([01](?:,[01]){24})\]")  # expects exactly 25 values
        while not self._stop.is_set():
            try:
                raw = self.ser.readline().decode(errors="ignore").strip()
            except Exception as e:
                self.out_queue.put(("error", f"Serial read error: {e}"))
                break
            if not raw:
                continue
            m = line_re.search(raw)
            if m:
                data = m.group(1).split(",")
                bools = [bool(int(x)) for x in data]
                self.out_queue.put(("keys", bools))
            else:
                # forward other serial messages as info
                self.out_queue.put(("info", raw))
        try:
            self.ser.close()
        except:
            pass
        self.out_queue.put(("info", "Serial thread exiting"))

    def stop(self):
        self._stop.set()

# GUI app
class KeyGridApp:
    def __init__(self, root):
        self.root = root
        root.title("ESP32 Matrix Receiver")
        self.frame = ttk.Frame(root, padding=10)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Controls
        ctrl_frame = ttk.Frame(self.frame)
        ctrl_frame.pack(fill=tk.X, pady=(0,10))

        ttk.Label(ctrl_frame, text="Serial Port:").pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value="")
        self.port_entry = ttk.Entry(ctrl_frame, textvariable=self.port_var, width=15)
        self.port_entry.pack(side=tk.LEFT, padx=(5,10))

        ttk.Label(ctrl_frame, text="Baud:").pack(side=tk.LEFT)
        self.baud_var = tk.IntVar(value=115200)
        self.baud_entry = ttk.Entry(ctrl_frame, textvariable=self.baud_var, width=8)
        self.baud_entry.pack(side=tk.LEFT, padx=(5,10))

        self.connect_btn = ttk.Button(ctrl_frame, text="Connect", command=self.on_connect)
        self.connect_btn.pack(side=tk.LEFT, padx=(5,5))

        self.disconnect_btn = ttk.Button(ctrl_frame, text="Disconnect", command=self.on_disconnect, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=(5,5))

        self.emu_var = tk.BooleanVar(value=False)
        self.emu_chk = ttk.Checkbutton(ctrl_frame, text="Emulate keyboard", variable=self.emu_var)
        self.emu_chk.pack(side=tk.LEFT, padx=(10,0))

        # Info area
        self.info_var = tk.StringVar(value="Not connected")
        ttk.Label(self.frame, textvariable=self.info_var).pack(fill=tk.X)

        # Grid
        self.grid_frame = ttk.Frame(self.frame)
        self.grid_frame.pack()
        self.cell_labels = []
        for r in range(5):
            row_widgets = []
            for c in range(5):
                lbl = tk.Label(self.grid_frame, text=labels[r][c], relief=tk.RAISED, width=10, height=3, bg="lightgray")
                lbl.grid(row=r, column=c, padx=3, pady=3)
                row_widgets.append(lbl)
            self.cell_labels.append(row_widgets)

        # Serial thread and queue
        self.queue = queue.Queue()
        self.reader = None

        # For emulation
        self.keyboard = Controller() if True else None
        self.prev_pressed = [False]*25
        self.root.after(100, self._poll_queue)

    def _poll_queue(self):
        try:
            while True:
                typ, payload = self.queue.get_nowait()
                if typ == "keys":
                    self.update_keys(payload)
                elif typ == "info":
                    self.info_var.set(payload)
                elif typ == "error":
                    messagebox.showerror("Serial error", payload)
                    self.info_var.set(payload)
                    self.on_disconnect()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def update_keys(self, bools):
        # bools is length 25 row-major
        for i, v in enumerate(bools):
            r = i // 5
            c = i % 5
            lbl = self.cell_labels[r][c]
            if v:
                lbl.config(bg="lime")
            else:
                lbl.config(bg="lightgray")

        # Emulate keyboard events if enabled
        if self.emu_var.get():
            for i, pressed in enumerate(bools):
                if pressed != self.prev_pressed[i]:
                    label = labels[i//5][i%5]
                    kp = to_pynput_key(label)
                    if kp is None:
                        # unsupported mapping
                        pass
                    else:
                        try:
                            if pressed:
                                # press
                                self.keyboard.press(kp)
                            else:
                                self.keyboard.release(kp)
                        except Exception as e:
                            print("pynput error:", e)
            self.prev_pressed = list(bools)

    def on_connect(self):
        port = self.port_var.get().strip()
        baud = int(self.baud_var.get())
        if not port:
            messagebox.showwarning("Port required", "Please enter a serial port (e.g. COM3 or /dev/ttyUSB0)")
            return
        if self.reader is not None:
            messagebox.showinfo("Already connected", "Already connected")
            return
        self.reader = SerialReader(port, baud, self.queue)
        self.reader.start()
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.info_var.set(f"Connecting to {port}...")

    def on_disconnect(self):
        if self.reader:
            self.reader.stop()
            self.reader = None
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.info_var.set("Disconnected")

def main():
    parser = argparse.ArgumentParser(description="ESP32 Matrix Receiver GUI")
    parser.add_argument("--port", help="Serial port (e.g. COM3 or /dev/ttyUSB0)", default="")
    parser.add_argument("--baud", help="Baud rate", type=int, default=115200)
    args = parser.parse_args()

    root = tk.Tk()
    app = KeyGridApp(root)
    if args.port:
        app.port_var.set(args.port)
        app.baud_var.set(args.baud)
        app.on_connect()
    root.mainloop()

if __name__ == "__main__":
    main()