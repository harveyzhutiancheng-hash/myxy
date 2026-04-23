# -*- coding: utf-8 -*-
"""
梦幻西游 五开日常助手 v2
功能：日常录制回放 / 自动补血 / 自动复活
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json, time, random, os, sys
import numpy as np

def _check_deps():
    import subprocess
    pkgs = ["pyautogui","keyboard","pynput","mss","opencv-python"]
    for p in pkgs:
        try: __import__(p.replace("-","_").split("-")[0])
        except ImportError:
            subprocess.run([sys.executable,"-m","pip","install",p], check=True)

try:
    import pyautogui, keyboard, mss, cv2
    from pynput import mouse as pmouse
    pyautogui.FAILSAFE = True
except ImportError:
    _check_deps()
    import pyautogui, keyboard, mss, cv2
    from pynput import mouse as pmouse
    pyautogui.FAILSAFE = True

BASE = os.path.dirname(sys.executable) if getattr(sys,"frozen",False) else os.path.dirname(__file__)
RECORD_FILE = os.path.join(BASE, "actions.json")


# ════════════════════════════════════════════════════
#  工具函数
# ════════════════════════════════════════════════════

_sct = mss.mss()

def grab(region):
    img = _sct.grab(region)
    return cv2.cvtColor(np.array(img), cv2.COLOR_BGRA2BGR)

def click_at(x, y):
    pyautogui.moveTo(x + random.randint(-3,3), y + random.randint(-3,3),
                     duration=random.uniform(0.05,0.15))
    pyautogui.click()


# ════════════════════════════════════════════════════
#  血条检测
# ════════════════════════════════════════════════════

def detect_hp_percent(region):
    """
    检测指定区域的血条百分比
    原理：扫描血条区域，统计红色像素占比
    region: {"left":x,"top":y,"width":w,"height":h} 血条所在屏幕区域
    返回 0.0~1.0
    """
    img = grab(region)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # 红色范围（梦幻血条一般是红色）
    mask1 = cv2.inRange(hsv, np.array([0,100,80]),  np.array([10,255,255]))
    mask2 = cv2.inRange(hsv, np.array([160,100,80]),np.array([180,255,255]))
    red_px = cv2.countNonZero(mask1 | mask2)
    total  = img.shape[0] * img.shape[1]
    return red_px / total if total > 0 else 0.0


# ════════════════════════════════════════════════════
#  死亡检测
# ════════════════════════════════════════════════════

def detect_dead(region):
    """
    检测角色是否死亡
    原理：死亡后画面变灰，检测灰度像素占比是否超过阈值
    """
    img  = grab(region)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bgr  = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    diff = cv2.absdiff(img, bgr)
    gray_px  = np.sum(diff < 20)
    total_px = diff.size
    return (gray_px / total_px) > 0.85   # 85% 以上像素接近灰色 → 判定死亡


# ════════════════════════════════════════════════════
#  录制 / 回放
# ════════════════════════════════════════════════════

class Recorder:
    def __init__(self, log):
        self.log = log
        self.actions = []
        self._recording = False
        self._listener = None

    def start(self):
        self._recording = True
        self.actions = []
        self._t = time.time()
        self.log("录制开始，请在第一个窗口操作…（完成后点停止）")
        def on_click(x, y, btn, pressed):
            if not pressed or not self._recording: return
            if btn != pmouse.Button.left: return
            delay = round(time.time() - self._t, 3)
            self._t = time.time()
            self.actions.append({"x":x,"y":y,"delay":delay})
            self.log(f"  ✓ ({x},{y})  间隔{delay:.2f}s")
        self._listener = pmouse.Listener(on_click=on_click)
        self._listener.start()

    def stop(self):
        self._recording = False
        if self._listener: self._listener.stop()
        with open(RECORD_FILE,"w",encoding="utf-8") as f:
            json.dump(self.actions, f, indent=2)
        self.log(f"录制完成，共 {len(self.actions)} 步")

    def replay(self, window_lefts, ref_left, skip_first, stop_ev):
        if not os.path.exists(RECORD_FILE):
            self.log("❌ 未找到录制文件，请先录制"); return
        with open(RECORD_FILE,encoding="utf-8") as f:
            acts = json.load(f)
        targets = window_lefts[1:] if skip_first else window_lefts
        self.log(f"开始回放，共 {len(targets)} 个窗口")
        for win_left in targets:
            if stop_ev.is_set(): self.log("⏹ 已停止"); return
            self.log(f"\n── 窗口 x={win_left}")
            time.sleep(0.8)
            for act in acts:
                if stop_ev.is_set(): self.log("⏹ 已停止"); return
                ax = win_left + (act["x"] - ref_left)
                click_at(ax, act["y"])
                time.sleep(max(act["delay"] + random.uniform(0.05,0.15), 0.08))
            self.log("  ✓ 完成")
        self.log("\n✅ 全部回放完毕")


# ════════════════════════════════════════════════════
#  自动补血监控
# ════════════════════════════════════════════════════

class AutoHeal:
    """
    监控每个角色的血条区域，低于阈值时按技能键
    血条区域 = 每个窗口内血条的相对坐标
    """
    def __init__(self, log):
        self.log  = log
        self._stop = threading.Event()

    def start(self, window_lefts, hp_rel, threshold, hotkey, interval):
        """
        window_lefts : 各窗口左边界列表
        hp_rel       : 血条相对于窗口左上角的区域 {"x","y","w","h"}
        threshold    : 触发补血的血量百分比（如 0.5 = 50%）
        hotkey       : 补血技能快捷键（如 "F1"）
        interval     : 检测间隔秒数
        """
        self._stop.clear()
        def _run():
            self.log("🩸 自动补血已启动")
            while not self._stop.is_set():
                for i, wl in enumerate(window_lefts):
                    region = {
                        "left":  wl + hp_rel["x"],
                        "top":   hp_rel["y"],
                        "width": hp_rel["w"],
                        "height":hp_rel["h"],
                    }
                    try:
                        hp = detect_hp_percent(region)
                        if hp < threshold:
                            self.log(f"  ⚠ 窗口{i+1} 血量{hp*100:.0f}% 触发补血")
                            # 点击该窗口中心确保焦点
                            cx = wl + hp_rel["x"] + hp_rel["w"]//2
                            cy = hp_rel["y"] + hp_rel["h"]//2
                            pyautogui.click(cx, cy)
                            time.sleep(0.1)
                            pyautogui.hotkey(hotkey)
                            time.sleep(0.5)
                    except Exception as e:
                        self.log(f"  补血检测异常: {e}")
                self._stop.wait(interval)
            self.log("🩸 自动补血已停止")
        threading.Thread(target=_run, daemon=True).start()

    def stop(self):
        self._stop.set()


# ════════════════════════════════════════════════════
#  自动复活监控
# ════════════════════════════════════════════════════

class AutoRevive:
    """
    监控各角色死亡状态，检测到死亡时：
    切换到指定复活角色窗口 → 按复活技能键 / 使用复活道具
    """
    def __init__(self, log):
        self.log   = log
        self._stop = threading.Event()

    def start(self, window_lefts, detect_rel, reviver_idx, revive_hotkey, item_hotkey, interval):
        """
        window_lefts  : 各窗口左边界列表
        detect_rel    : 死亡检测区域（相对窗口左上角）{"x","y","w","h"}
        reviver_idx   : 负责复活的角色索引（0~4）
        revive_hotkey : 复活技能快捷键（如 "F5"），None 则用道具
        item_hotkey   : 复活道具快捷键（如 "F6"），None 则不用
        interval      : 检测间隔秒数
        """
        self._stop.clear()
        def _run():
            self.log("💀 自动复活已启动")
            reviver_left = window_lefts[reviver_idx]
            while not self._stop.is_set():
                for i, wl in enumerate(window_lefts):
                    if i == reviver_idx: continue   # 复活者自己跳过
                    region = {
                        "left":  wl + detect_rel["x"],
                        "top":   detect_rel["y"],
                        "width": detect_rel["w"],
                        "height":detect_rel["h"],
                    }
                    try:
                        if detect_dead(region):
                            self.log(f"  💀 窗口{i+1} 检测到死亡，切换复活者复活")
                            # 1. 先点击死亡角色确认选中
                            dead_cx = wl + detect_rel["x"] + detect_rel["w"]//2
                            dead_cy = detect_rel["y"] + detect_rel["h"]//2
                            pyautogui.click(dead_cx, dead_cy)
                            time.sleep(0.3)
                            # 2. 切换到复活者窗口
                            rev_cx = reviver_left + detect_rel["x"] + detect_rel["w"]//2
                            rev_cy = detect_rel["y"] + detect_rel["h"]//2
                            pyautogui.click(rev_cx, rev_cy)
                            time.sleep(0.2)
                            # 3. 使用复活技能
                            if revive_hotkey:
                                pyautogui.hotkey(revive_hotkey)
                                self.log(f"    → 使用复活技能 {revive_hotkey}")
                                time.sleep(1.5)
                            # 4. 如果还死着，使用复活道具
                            if item_hotkey and detect_dead(region):
                                pyautogui.hotkey(item_hotkey)
                                self.log(f"    → 使用复活道具 {item_hotkey}")
                                time.sleep(1.0)
                    except Exception as e:
                        self.log(f"  复活检测异常: {e}")
                self._stop.wait(interval)
            self.log("💀 自动复活已停止")
        threading.Thread(target=_run, daemon=True).start()

    def stop(self):
        self._stop.set()


# ════════════════════════════════════════════════════
#  GUI
# ════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("梦幻西游 五开助手 v2")
        self.resizable(False, False)
        self._stop_replay = threading.Event()
        self._recorder    = Recorder(self._log)
        self._healer      = AutoHeal(self._log)
        self._reviver     = AutoRevive(self._log)
        self._build_ui()
        self._center()

    def _center(self):
        self.update_idletasks()
        w,h = self.winfo_width(), self.winfo_height()
        sw,sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")

    # ── 界面构建 ──────────────────────────────────────

    def _build_ui(self):
        PAD = {"padx":10,"pady":5}

        tk.Label(self, text="梦幻西游  五开助手",
                 font=("微软雅黑",14,"bold"), fg="#c04000").pack(pady=(12,2))
        tk.Label(self, text="日常录制回放  /  自动补血  /  自动复活",
                 font=("微软雅黑",9), fg="#666").pack()
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=6)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=4)

        nb.add(self._tab_windows(), text="  窗口配置  ")
        nb.add(self._tab_daily(),   text="  日常任务  ")
        nb.add(self._tab_heal(),    text="  自动补血  ")
        nb.add(self._tab_revive(),  text="  自动复活  ")

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=(4,0))

        self._log_box = scrolledtext.ScrolledText(
            self, height=8, font=("Consolas",9),
            bg="#1e1e1e", fg="#d4d4d4", state="disabled", wrap="word")
        self._log_box.pack(fill="both", expand=True, padx=10, pady=(4,8))

        tk.Label(self, text="鼠标移到屏幕左上角紧急停止",
                 font=("微软雅黑",8), fg="#999").pack(pady=(0,6))

    # ── Tab 1: 窗口配置 ───────────────────────────────

    def _tab_windows(self):
        f = tk.Frame(self)
        tk.Label(f, text="五个窗口的左边界 X 坐标（从左到右）",
                 font=("微软雅黑",9), fg="#555").pack(pady=(10,4))

        self._x_vars = []
        row = tk.Frame(f); row.pack()
        for i, d in enumerate([0,384,768,1152,1536]):
            tk.Label(row, text=f"窗口{i+1}", font=("微软雅黑",9)).grid(row=0,column=i*2,padx=(8,2))
            v = tk.StringVar(value=str(d))
            tk.Entry(row, textvariable=v, width=6, justify="center").grid(row=0,column=i*2+1,padx=(0,8))
            self._x_vars.append(v)

        tk.Button(f, text="📍 查看当前鼠标坐标", command=self._show_cursor,
                  font=("微软雅黑",9)).pack(pady=8)

        tk.Label(f, text="窗口高度（像素）", font=("微软雅黑",9), fg="#555").pack()
        self._win_h = tk.StringVar(value="768")
        tk.Entry(f, textvariable=self._win_h, width=8, justify="center").pack(pady=2)

        return f

    # ── Tab 2: 日常任务 ───────────────────────────────

    def _tab_daily(self):
        f = tk.Frame(self)

        fr = ttk.LabelFrame(f, text="  录制操作（在第一个窗口手动做一遍）  ")
        fr.pack(fill="x", padx=10, pady=8)
        row = tk.Frame(fr); row.pack(pady=8)
        self._btn_rec = tk.Button(row, text="▶ 开始录制", width=13,
            bg="#e8f4e8", font=("微软雅黑",10,"bold"), command=self._on_rec_start)
        self._btn_rec.pack(side="left", padx=6)
        self._btn_rec_stop = tk.Button(row, text="⏹ 停止录制", width=13,
            bg="#fde8e8", font=("微软雅黑",10,"bold"),
            state="disabled", command=self._on_rec_stop)
        self._btn_rec_stop.pack(side="left", padx=6)

        fp = ttk.LabelFrame(f, text="  回放到其余窗口  ")
        fp.pack(fill="x", padx=10, pady=4)
        self._skip_var = tk.BooleanVar(value=True)
        tk.Checkbutton(fp, text="跳过第一个窗口（已手动操作过）",
                       variable=self._skip_var,
                       font=("微软雅黑",9)).pack(anchor="w", padx=10, pady=(6,2))
        row2 = tk.Frame(fp); row2.pack(pady=(4,8))
        self._btn_play = tk.Button(row2, text="▶ 开始回放", width=13,
            bg="#e8eef8", font=("微软雅黑",10,"bold"), command=self._on_play)
        self._btn_play.pack(side="left", padx=6)
        self._btn_play_stop = tk.Button(row2, text="⏹ 停止", width=10,
            font=("微软雅黑",10), state="disabled", command=self._on_play_stop)
        self._btn_play_stop.pack(side="left", padx=6)

        return f

    # ── Tab 3: 自动补血 ───────────────────────────────

    def _tab_heal(self):
        f = tk.Frame(f := tk.Frame(self)) or f

        info = tk.Frame(f); info.pack(fill="x", padx=10, pady=(10,4))
        tk.Label(info, text="血条区域（相对各窗口左上角的坐标）",
                 font=("微软雅黑",9,"bold")).pack(anchor="w")
        tk.Label(info, text="先用"查看坐标"工具，把鼠标移到血条左边/右边记下数值",
                 font=("微软雅黑",8), fg="#666").pack(anchor="w")

        grid = tk.Frame(f); grid.pack(padx=10, pady=4)
        labels = ["血条 X","血条 Y","宽度 W","高度 H"]
        defaults = ["10","748","120","8"]
        self._hp_vars = []
        for i,(lbl,val) in enumerate(zip(labels,defaults)):
            tk.Label(grid, text=lbl, font=("微软雅黑",9)).grid(row=0,column=i*2,padx=(8,2))
            v = tk.StringVar(value=val)
            tk.Entry(grid, textvariable=v, width=6, justify="center").grid(row=0,column=i*2+1)
            self._hp_vars.append(v)

        row2 = tk.Frame(f); row2.pack(padx=10, pady=4)
        tk.Label(row2, text="触发阈值（%）", font=("微软雅黑",9)).pack(side="left")
        self._hp_thresh = tk.StringVar(value="50")
        tk.Entry(row2, textvariable=self._hp_thresh, width=5, justify="center").pack(side="left",padx=4)
        tk.Label(row2, text="  补血技能键", font=("微软雅黑",9)).pack(side="left")
        self._hp_key = tk.StringVar(value="F1")
        tk.Entry(row2, textvariable=self._hp_key, width=5, justify="center").pack(side="left",padx=4)
        tk.Label(row2, text="  检测间隔(s)", font=("微软雅黑",9)).pack(side="left")
        self._hp_interval = tk.StringVar(value="2")
        tk.Entry(row2, textvariable=self._hp_interval, width=4, justify="center").pack(side="left",padx=4)

        row3 = tk.Frame(f); row3.pack(pady=8)
        self._btn_heal_start = tk.Button(row3, text="▶ 启动自动补血", width=15,
            bg="#e8f4e8", font=("微软雅黑",10,"bold"), command=self._on_heal_start)
        self._btn_heal_start.pack(side="left", padx=6)
        self._btn_heal_stop = tk.Button(row3, text="⏹ 停止", width=8,
            font=("微软雅黑",10), state="disabled", command=self._on_heal_stop)
        self._btn_heal_stop.pack(side="left", padx=6)

        return f

    # ── Tab 4: 自动复活 ───────────────────────────────

    def _tab_revive(self):
        f = tk.Frame(self)

        info = tk.Frame(f); info.pack(fill="x", padx=10, pady=(10,4))
        tk.Label(info, text="死亡检测区域（相对各窗口左上角）",
                 font=("微软雅黑",9,"bold")).pack(anchor="w")
        tk.Label(info, text="建议填整个游戏画面区域，死亡后画面变灰即触发",
                 font=("微软雅黑",8), fg="#666").pack(anchor="w")

        grid = tk.Frame(f); grid.pack(padx=10, pady=4)
        labels = ["区域 X","区域 Y","宽度 W","高度 H"]
        defaults = ["0","0","384","768"]
        self._dead_vars = []
        for i,(lbl,val) in enumerate(zip(labels,defaults)):
            tk.Label(grid, text=lbl, font=("微软雅黑",9)).grid(row=0,column=i*2,padx=(8,2))
            v = tk.StringVar(value=val)
            tk.Entry(grid, textvariable=v, width=6, justify="center").grid(row=0,column=i*2+1)
            self._dead_vars.append(v)

        row2 = tk.Frame(f); row2.pack(padx=10, pady=4)
        tk.Label(row2, text="复活者是第几号角色", font=("微软雅黑",9)).pack(side="left")
        self._reviver_idx = tk.StringVar(value="1")
        ttk.Combobox(row2, textvariable=self._reviver_idx,
                     values=["1","2","3","4","5"], width=3).pack(side="left",padx=4)

        row3 = tk.Frame(f); row3.pack(padx=10, pady=2)
        tk.Label(row3, text="复活技能键", font=("微软雅黑",9)).pack(side="left")
        self._rev_skill = tk.StringVar(value="F5")
        tk.Entry(row3, textvariable=self._rev_skill, width=5, justify="center").pack(side="left",padx=4)
        tk.Label(row3, text="  复活道具键（没有留空）", font=("微软雅黑",9)).pack(side="left")
        self._rev_item = tk.StringVar(value="")
        tk.Entry(row3, textvariable=self._rev_item, width=5, justify="center").pack(side="left",padx=4)

        row4 = tk.Frame(f); row4.pack(padx=10, pady=2)
        tk.Label(row4, text="检测间隔(s)", font=("微软雅黑",9)).pack(side="left")
        self._rev_interval = tk.StringVar(value="3")
        tk.Entry(row4, textvariable=self._rev_interval, width=4, justify="center").pack(side="left",padx=4)

        row5 = tk.Frame(f); row5.pack(pady=8)
        self._btn_rev_start = tk.Button(row5, text="▶ 启动自动复活", width=15,
            bg="#e8f4e8", font=("微软雅黑",10,"bold"), command=self._on_rev_start)
        self._btn_rev_start.pack(side="left", padx=6)
        self._btn_rev_stop = tk.Button(row5, text="⏹ 停止", width=8,
            font=("微软雅黑",10), state="disabled", command=self._on_rev_stop)
        self._btn_rev_stop.pack(side="left", padx=6)

        return f

    # ── 日志 ──────────────────────────────────────────

    def _log(self, msg):
        def _do():
            self._log_box.config(state="normal")
            self._log_box.insert("end", msg+"\n")
            self._log_box.see("end")
            self._log_box.config(state="disabled")
        self.after(0, _do)

    # ── 坐标工具 ──────────────────────────────────────

    def _show_cursor(self):
        win = tk.Toplevel(self)
        win.title("鼠标坐标")
        win.resizable(False, False)
        lbl = tk.Label(win, text="x=0  y=0", font=("Consolas",16), width=22)
        lbl.pack(padx=20, pady=20)
        tk.Label(win, text="移动鼠标到目标位置，记下坐标",
                 font=("微软雅黑",9), fg="#666").pack(pady=(0,10))
        def _upd():
            if not win.winfo_exists(): return
            x,y = pyautogui.position()
            lbl.config(text=f"x = {x:5d}    y = {y:5d}")
            win.after(100, _upd)
        _upd()

    def _get_lefts(self):
        try: return [int(v.get()) for v in self._x_vars]
        except: messagebox.showerror("错误","坐标请填数字"); return None

    # ── 录制回放事件 ──────────────────────────────────

    def _on_rec_start(self):
        self._btn_rec.config(state="disabled")
        self._btn_rec_stop.config(state="normal")
        self._recorder.start()

    def _on_rec_stop(self):
        self._recorder.stop()
        self._btn_rec.config(state="normal")
        self._btn_rec_stop.config(state="disabled")

    def _on_play(self):
        lefts = self._get_lefts()
        if not lefts: return
        self._stop_replay.clear()
        self._btn_play.config(state="disabled")
        self._btn_play_stop.config(state="normal")
        def _run():
            self._recorder.replay(lefts, lefts[0], self._skip_var.get(), self._stop_replay)
            self.after(0, lambda: self._btn_play.config(state="normal"))
            self.after(0, lambda: self._btn_play_stop.config(state="disabled"))
        threading.Thread(target=_run, daemon=True).start()

    def _on_play_stop(self):
        self._stop_replay.set()
        self._btn_play_stop.config(state="disabled")
        self._btn_play.config(state="normal")

    # ── 补血事件 ──────────────────────────────────────

    def _on_heal_start(self):
        lefts = self._get_lefts()
        if not lefts: return
        try:
            hp_rel = {
                "x": int(self._hp_vars[0].get()),
                "y": int(self._hp_vars[1].get()),
                "w": int(self._hp_vars[2].get()),
                "h": int(self._hp_vars[3].get()),
            }
            thresh   = float(self._hp_thresh.get()) / 100
            hotkey   = self._hp_key.get().strip()
            interval = float(self._hp_interval.get())
        except:
            messagebox.showerror("错误","请检查补血配置，均需填数字"); return
        self._healer.start(lefts, hp_rel, thresh, hotkey, interval)
        self._btn_heal_start.config(state="disabled")
        self._btn_heal_stop.config(state="normal")

    def _on_heal_stop(self):
        self._healer.stop()
        self._btn_heal_start.config(state="normal")
        self._btn_heal_stop.config(state="disabled")

    # ── 复活事件 ──────────────────────────────────────

    def _on_rev_start(self):
        lefts = self._get_lefts()
        if not lefts: return
        try:
            dead_rel = {
                "x": int(self._dead_vars[0].get()),
                "y": int(self._dead_vars[1].get()),
                "w": int(self._dead_vars[2].get()),
                "h": int(self._dead_vars[3].get()),
            }
            rev_idx  = int(self._reviver_idx.get()) - 1
            rev_skill= self._rev_skill.get().strip() or None
            rev_item = self._rev_item.get().strip() or None
            interval = float(self._rev_interval.get())
        except:
            messagebox.showerror("错误","请检查复活配置"); return
        self._reviver.start(lefts, dead_rel, rev_idx, rev_skill, rev_item, interval)
        self._btn_rev_start.config(state="disabled")
        self._btn_rev_stop.config(state="normal")

    def _on_rev_stop(self):
        self._reviver.stop()
        self._btn_rev_start.config(state="normal")
        self._btn_rev_stop.config(state="disabled")


if __name__ == "__main__":
    App().mainloop()
