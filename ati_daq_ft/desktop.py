#!/usr/bin/env python3
"""Live NI USB-621x acquisition and official ATI DAQ F/T conversion."""

import argparse
import csv
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import os

CONFIG = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "ati_daq_ft/reader.json"
)


from .core import AnalogReader, Calibration
from .firmware import ensure_loaded


def cli(args):
    cal = Calibration(args.cal, args.cal_index) if args.cal else None
    reader = None
    out = None
    try:
        ensure_loaded()
        reader = AnalogReader(args.device, args.terminal)
        if args.tare:
            if not cal:
                raise ValueError("--tare requires --cal.")
            readings = [reader.read() for _ in range(20)]
            cal.bias(
                [sum(row[i] for row in readings) / len(readings) for i in range(7)]
            )
        fields = ["unix_time"] + [f"ai{i}_V" for i in range(7)]
        if cal:
            fields += ["Fx_N", "Fy_N", "Fz_N", "Tx_Nm", "Ty_Nm", "Tz_Nm"]
            print(
                f"ATI {cal.serial}; N / N-m; temperature compensation: {cal.tempcomp}; bias: {args.tare}"
            )
        else:
            print(
                "RAW VOLTAGES ONLY — supply this sensor’s .cal file for forces/torques."
            )
        print(" ".join(fields))
        writer = None
        if args.csv:
            out = open(args.csv, "x", newline="")
            writer = csv.writer(out)
            writer.writerow(fields)
        start = time.monotonic()
        while args.seconds <= 0 or time.monotonic() - start < args.seconds:
            volts = reader.read()
            row = [time.time()] + volts + (cal.convert(volts) if cal else [])
            print(" ".join(f"{v:+.6f}" for v in row), flush=True)
            if writer:
                writer.writerow(row)
                out.flush()
            time.sleep(1 / args.hz)
    except KeyboardInterrupt:
        pass
    finally:
        if reader:
            reader.close()
        if cal:
            cal.close()
        if out:
            out.close()


def gui(args):
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
    except ImportError as error:
        raise RuntimeError(
            "The optional GUI requires python3-tk (sudo apt install python3-tk)."
        ) from error

    app = tk.Tk()
    app.title("ATI Gamma · live USB reader")
    app.geometry("770x540")
    app.configure(bg="#16202b")
    frame = ttk.Frame(app, padding=22)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="ATI Gamma", font=("Sans", 24, "bold")).pack(anchor="w")
    status = tk.StringVar(value="Connecting to the USB DAQ…")
    ttk.Label(frame, textvariable=status, wraplength=710).pack(anchor="w", pady=(6, 16))
    table = ttk.Frame(frame)
    table.pack(fill="x")
    ftvars = []
    for j, label in enumerate(
        ["Fx (N)", "Fy (N)", "Fz (N)", "Tx (N·m)", "Ty (N·m)", "Tz (N·m)"]
    ):
        col = j % 3
        row = (j // 3) * 2
        ttk.Label(table, text=label).grid(
            row=row, column=col, sticky="w", padx=12, pady=(6, 0)
        )
        v = tk.StringVar(value="—")
        ftvars.append(v)
        ttk.Label(table, textvariable=v, font=("Monospace", 24, "bold")).grid(
            row=row + 1, column=col, sticky="w", padx=12, pady=(0, 12)
        )
        table.columnconfigure(col, weight=1)
    raw = tk.StringVar(value="")
    ttk.Label(
        frame, text="Live strain-gauge voltages · ai0–ai5", font=("Sans", 11, "bold")
    ).pack(anchor="w", pady=(12, 4))
    ttk.Label(frame, textvariable=raw, font=("Monospace", 11)).pack(anchor="w")
    temperature = tk.StringVar(value="")
    ttk.Label(frame, textvariable=temperature).pack(anchor="w", pady=(4, 12))
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=8)
    cal = None
    reader = None
    latest = None
    bias_requested = False

    def load_cal(path=None):
        nonlocal cal
        path = path or filedialog.askopenfilename(
            title="Select THIS Gamma sensor’s ATI calibration",
            filetypes=[("ATI calibration", "*.cal"), ("All files", "*")],
        )
        if not path:
            return
        try:
            new = Calibration(path, args.cal_index)
        except Exception as e:
            messagebox.showerror("Calibration", str(e))
            return
        if cal:
            cal.close()
        cal = new
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps({"calibration": new.path}, indent=2) + "\n")

    def tare():
        nonlocal bias_requested
        if not cal:
            messagebox.showinfo(
                "Calibration needed", "Load this sensor’s .cal file first."
            )
            return
        bias_requested = True

    def clear_bias():
        if cal:
            cal.clear_bias()

    ttk.Button(buttons, text="Load calibration…", command=load_cal).pack(
        side="left", padx=(0, 8)
    )
    ttk.Button(buttons, text="Zero / tare current load", command=tare).pack(
        side="left", padx=(0, 8)
    )
    ttk.Button(buttons, text="Clear tare", command=clear_bias).pack(side="left")
    ttk.Label(
        frame,
        text="No automatic tare. Calibration must match the FT serial on your sensor.\nClose any other reader before opening this one.",
        wraplength=700,
    ).pack(anchor="w", pady=(12, 0))
    closed = False

    def close():
        nonlocal closed
        if closed:
            return
        closed = True
        if reader:
            reader.close()
        if cal:
            cal.close()
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", close)

    def tick():
        nonlocal latest, bias_requested, reader
        try:
            if reader is None:
                ensure_loaded()
                reader = AnalogReader(args.device, args.terminal)
            latest = reader.read()
            raw.set("  ".join(f"{v:+.5f}" for v in latest[:6]) + " V")
            temperature.set(f"Temperature channel ai6: {latest[6]:+.5f} V")
            if cal:
                if bias_requested:
                    readings = [latest] + [reader.read() for _ in range(19)]
                    cal.bias(
                        [sum(r[i] for r in readings) / len(readings) for i in range(7)]
                    )
                    bias_requested = False
                for v, x in zip(ftvars, cal.convert(latest)):
                    v.set(f"{x:+.3f}")
                status.set(
                    f"LIVE · {cal.serial} · N / N·m · temperature compensation {'on' if cal.tempcomp else 'unavailable'}"
                )
            else:
                status.set(
                    "LIVE VOLTAGES · Load this Gamma’s .cal file to display force and torque."
                )
        except Exception as e:
            status.set(
                "READ ERROR · "
                + str(e)
                + " — close and restart the reader after correcting the problem."
            )
            for v in ftvars:
                v.set("—")
            raw.set("No current sample")
            if reader:
                reader.close()
                reader = None
            return
        app.after(max(20, int(1000 / args.hz)), tick)

    if args.cal:
        load_cal(args.cal)
    elif CONFIG.exists():
        try:
            p = json.loads(CONFIG.read_text()).get("calibration")
            if p and Path(p).is_file():
                load_cal(p)
        except (OSError, ValueError, ET.ParseError):
            pass
    app.after(50, tick)
    try:
        app.mainloop()
    finally:
        close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--cal", help="Calibration for the FT serial on THIS sensor")
    parser.add_argument("--cal-index", type=int, default=1)
    parser.add_argument("--device", default="Dev1")
    parser.add_argument("--terminal", choices=["diff", "rse", "nrse"], default="diff")
    parser.add_argument("--hz", type=float, default=10)
    parser.add_argument(
        "--seconds", type=float, default=0, help="CLI duration; 0 means until Ctrl+C"
    )
    parser.add_argument("--csv", help="Write a NEW CSV file (refuses to overwrite)")
    parser.add_argument(
        "--tare", action="store_true", help="CLI: zero current load at startup"
    )
    args = parser.parse_args()
    if not 0 < args.hz <= 100:
        parser.error("--hz must be between 0 and 100")
    if args.tare and not args.cal and not args.gui:
        parser.error("--tare requires --cal")
    try:
        (gui if args.gui else cli)(args)
    except KeyboardInterrupt:
        pass
    except (RuntimeError, ValueError, OSError, ET.ParseError) as e:
        parser.exit(1, str(e) + "\n")


if __name__ == "__main__":
    main()
