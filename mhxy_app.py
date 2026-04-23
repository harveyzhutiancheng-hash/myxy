# -*- coding: utf-8 -*-
"""
梦幻西游 五开日常助手
带图形界面，无需安装 Python，双击即用
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
import time
import random
import os
import sys

# ── 依赖检测（首次运行自动安装）──────────────────────────────
def check_deps():
    missing = []
    for pkg in ["pyautogui", "keyboard", "pynput"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install"] + missing, check=True)

try:
    import pyautogui
    import keyboard
    from pynput import mouse as pmouse
    pyautogui.FAILSAFE = True
except ImportError:
    check_deps()
    import pyautogui
    import keyboard
    from pynput import mouse as pmouse
    pyautogui.FAILSAFE = True

RECORD_FILE = os.path.join(os.path.dirname(sys.executable)
                           if getattr(sys, 'frozen', False)
                           else os.path.dirname(__file__),
                           "actions.json")

# ════════════════════════════════════════════════════
#  录制 / 回放核心逻辑
# ════════════════════════════════════════════════════

class Bot:
    def __init__(self, log_fn):
        self.log = log_fn
        self.recording = False
        self.actions = []
        self._listener = None

    # ── 录制 ──────────────────────────────────────────
    def start_record(self):
        self.recording = True
        self.actions = []
        self._last_t = time.time()
        self.log("录制已开始，请在第一个窗口操作日常任务…")
        self.log("完成后点击【停止录制】按钮")

        def on_click(x, y, button, pressed):
            if not pressed or not self.recording:
                return
            if button != pmouse.Button.left:
                return
            now = time.time()
            delay = round(now - self._last_t, 3)
            self._last_t = now
            self.actions.append({"x": x, "y": y, "delay": delay})
            self.log(f"  记录: ({x}, {y})  间隔 {delay:.2f}s")

        self._listener = pmouse.Listener(on_click=on_click)
        self._listener.start()

    def stop_record(self):
        self.recording = False
        if self._listener:
            self._listener.stop()
        with open(RECORD_FILE, "w", encoding="utf-8") as f:
            json.dump(self.actions, f, indent=2)
        self.log(f"录制完成，共 {len(self.actions)} 步，已保存")

    # ── 回放 ──────────────────────────────────────────
    def replay(self, window_lefts, ref_left, skip_first, stop_event):
        if not os.path.exists(RECORD_FILE):
            self.log("❌ 未找到录制文件，请先录制一次")
            return

        with open(RECORD_FILE, encoding="utf-8") as f:
            actions = json.load(f)

        if not actions:
            self.log("❌ 录制文件为空，请重新录制")
            return

        targets = window_lefts[1:] if skip_first else window_lefts

        self.log(f"开始回放，共 {len(targets)} 个窗口…")
        for idx, win_left in enumerate(targets):
            if stop_event.is_set():
                self.log("⏹ 已停止")
                return
            win_num = (window_lefts.index(win_left)) + 1
            self.log(f"\n── 窗口 {win_num}（x={win_left}）")
            time.sleep(0.8)

            for act in actions:
                if stop_event.is_set():
                    self.log("⏹ 已停止")
                    return
                ax = win_left + (act["x"] - ref_left)
                ay = act["y"]
                jx = random.randint(-3, 3)
                jy = random.randint(-3, 3)
                pyautogui.moveTo(ax + jx, ay + jy,
                                 duration=random.uniform(0.05, 0.12))
                pyautogui.click()
                wait = act["delay"] + random.uniform(0.05, 0.15)
                time.sleep(max(wait, 0.08))

            self.log(f"  ✓ 窗口 {win_num} 完成")

        self.log("\n✅ 全部窗口回放完毕！")


# ════════════════════════════════════════════════════
#  GUI 界面
# ════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("梦幻西游 五开日常助手")
        self.resizable(False, False)
        self._stop_event = threading.Event()
        self._bot = Bot(self._log)
        self._build_ui()
        self._center()

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")

    # ── 构建界面 ──────────────────────────────────────
    def _build_ui(self):
        PAD = {"padx": 10, "pady": 6}

        # ── 标题 ──
        tk.Label(self, text="梦幻西游  五开日常助手",
                 font=("微软雅黑", 14, "bold"), fg="#c04000").pack(pady=(14, 4))
        tk.Label(self, text="录制一次，自动在五个窗口重复操作",
                 font=("微软雅黑", 9), fg="#666").pack()

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=8)

        # ── 窗口坐标配置 ──
        frame_cfg = ttk.LabelFrame(self, text="  窗口左边界 X 坐标（从左到右）  ")
        frame_cfg.pack(fill="x", **PAD)

        self._x_vars = []
        defaults = [0, 384, 768, 1152, 1536]
        inner = tk.Frame(frame_cfg)
        inner.pack(pady=6)
        for i, d in enumerate(defaults):
            tk.Label(inner, text=f"窗口{i+1}", font=("微软雅黑", 9)).grid(
                row=0, column=i*2, padx=(8,2))
            v = tk.StringVar(value=str(d))
            tk.Entry(inner, textvariable=v, width=6, justify="center").grid(
                row=0, column=i*2+1, padx=(0,8))
            self._x_vars.append(v)

        tk.Button(frame_cfg, text="📍 查看当前鼠标坐标",
                  command=self._show_cursor,
                  font=("微软雅黑", 9)).pack(pady=(0, 6))

        # ── 录制区 ──
        frame_rec = ttk.LabelFrame(self, text="  第一步：录制操作  ")
        frame_rec.pack(fill="x", **PAD)

        btn_row = tk.Frame(frame_rec)
        btn_row.pack(pady=8)
        self._btn_rec_start = tk.Button(
            btn_row, text="▶  开始录制", width=14,
            bg="#e8f4e8", font=("微软雅黑", 10, "bold"),
            command=self._on_start_record)
        self._btn_rec_start.pack(side="left", padx=6)

        self._btn_rec_stop = tk.Button(
            btn_row, text="⏹  停止录制", width=14,
            bg="#fde8e8", font=("微软雅黑", 10, "bold"),
            state="disabled", command=self._on_stop_record)
        self._btn_rec_stop.pack(side="left", padx=6)

        # ── 回放区 ──
        frame_play = ttk.LabelFrame(self, text="  第二步：回放到其余窗口  ")
        frame_play.pack(fill="x", **PAD)

        self._skip_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame_play,
                       text="跳过第一个窗口（已手动操作过）",
                       variable=self._skip_var,
                       font=("微软雅黑", 9)).pack(anchor="w", padx=10, pady=(6,2))

        btn_row2 = tk.Frame(frame_play)
        btn_row2.pack(pady=(4, 8))
        self._btn_play = tk.Button(
            btn_row2, text="▶  开始回放", width=14,
            bg="#e8eef8", font=("微软雅黑", 10, "bold"),
            command=self._on_play)
        self._btn_play.pack(side="left", padx=6)

        self._btn_stop = tk.Button(
            btn_row2, text="⏹  停止", width=10,
            font=("微软雅黑", 10),
            state="disabled", command=self._on_stop)
        self._btn_stop.pack(side="left", padx=6)

        # ── 日志 ──
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=(6,0))
        self._log_box = scrolledtext.ScrolledText(
            self, height=10, font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4", state="disabled",
            wrap="word")
        self._log_box.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        tk.Label(self, text="鼠标移到屏幕左上角可紧急停止",
                 font=("微软雅黑", 8), fg="#999").pack(pady=(0, 8))

    # ── 日志 ──────────────────────────────────────────
    def _log(self, msg):
        def _do():
            self._log_box.config(state="normal")
            self._log_box.insert("end", msg + "\n")
            self._log_box.see("end")
            self._log_box.config(state="disabled")
        self.after(0, _do)

    # ── 查看坐标 ──────────────────────────────────────
    def _show_cursor(self):
        win = tk.Toplevel(self)
        win.title("鼠标坐标")
        win.resizable(False, False)
        lbl = tk.Label(win, text="x=0  y=0",
                       font=("Consolas", 16), width=20)
        lbl.pack(padx=20, pady=20)
        tk.Label(win, text="把鼠标移到各窗口左边界，记下 x 坐标",
                 font=("微软雅黑", 9), fg="#666").pack(pady=(0,10))

        def _update():
            if not win.winfo_exists():
                return
            x, y = pyautogui.position()
            lbl.config(text=f"x = {x:5d}    y = {y:5d}")
            win.after(100, _update)
        _update()

    # ── 录制 ──────────────────────────────────────────
    def _on_start_record(self):
        self._btn_rec_start.config(state="disabled")
        self._btn_rec_stop.config(state="normal")
        self._bot.start_record()

    def _on_stop_record(self):
        self._bot.stop_record()
        self._btn_rec_start.config(state="normal")
        self._btn_rec_stop.config(state="disabled")

    # ── 回放 ──────────────────────────────────────────
    def _get_window_lefts(self):
        try:
            return [int(v.get()) for v in self._x_vars]
        except ValueError:
            messagebox.showerror("错误", "窗口坐标必须填数字")
            return None

    def _on_play(self):
        lefts = self._get_window_lefts()
        if lefts is None:
            return
        self._stop_event.clear()
        self._btn_play.config(state="disabled")
        self._btn_stop.config(state="normal")

        def _run():
            self._bot.replay(
                window_lefts=lefts,
                ref_left=lefts[0],
                skip_first=self._skip_var.get(),
                stop_event=self._stop_event,
            )
            self.after(0, lambda: self._btn_play.config(state="normal"))
            self.after(0, lambda: self._btn_stop.config(state="disabled"))

        threading.Thread(target=_run, daemon=True).start()

    def _on_stop(self):
        self._stop_event.set()
        self._btn_stop.config(state="disabled")
        self._btn_play.config(state="normal")


# ════════════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    App().mainloop()
