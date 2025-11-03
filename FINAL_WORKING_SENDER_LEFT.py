import machine
import time
import sys

# Pin numbers (use integers matching the ESP32-C3 GPIO numbers)
COL_PINS = [6, 7, 8, 9, 10]
ROW_PINS = [4, 3, 2, 1, 20]

# Timing tuning
SCAN_DELAY = 0.002       # seconds between driving a row and reading columns
LOOP_DELAY = 0.01        # seconds between full matrix scans
DEBOUNCE_MS = 5          # simple debounce window in ms (used for per-scan tiny delay)

# Setup pins
cols = [machine.Pin(p, machine.Pin.IN, machine.Pin.PULL_UP) for p in COL_PINS]
rows = [machine.Pin(p, machine.Pin.OUT) for p in ROW_PINS]

# Initialize rows to HIGH (inactive). We assume switches connect row to column when pressed,
# and columns pull to GND when that row is driven low.
for r in rows:
    r.value(1)

def read_matrix_once():
    """
    Scan the matrix once. Returns a list of 25 integers (0/1) in row-major order.
    1 means pressed, 0 means released.
    """
    state = []
    for r in rows:
        # Drive current row low (active)
        r.value(0)
        # tiny settling delay
        time.sleep(SCAN_DELAY)
        # read columns (active low: 0 means pressed)
        for c in cols:
            val = c.value()
            pressed = 1 if val == 0 else 0
            state.append(pressed)
        # release row
        r.value(1)
        # tiny post-delay for stability
        time.sleep(DEBOUNCE_MS / 1000.0)
    return state

def format_line(state):
    # state is list of 25 ints -> "K:[0,1,0,...]"
    s = ",".join("1" if x else "0" for x in state)
    return "K:[" + s + "]"

def main():
    last = None
    # Small startup delay so serial monitor/host can be ready
    time.sleep(0.2)
    try:
        while True:
            st = read_matrix_once()
            if len(st) != 25:
                # Safety: always ensure 25 elements
                st = (st + [0]*25)[:25]
            if last is None or st != last:
                line = format_line(st)
                # Print line followed by newline so PC receiver can .readline()
                try:
                    print(line)
                except Exception:
                    # If print fails for any reason, try writing to sys.stdout
                    try:
                        sys.stdout.write(line + "\n")
                    except Exception:
                        pass
                last = st
            time.sleep(LOOP_DELAY)
    except KeyboardInterrupt:
        # graceful stop if running interactively
        pass

if __name__ == "__main__":
    main()