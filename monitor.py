# -*- coding: utf-8 -*-
"""
任务栏消息监控 - GUI版
兼容 Python 3.6.8
"""
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import mss
import requests
import numpy as np
from PIL import Image
import pyautogui

# ================= 配置 =================
NTFY_URL = ""  # 填入你自己的推送地址，例如 https://ntfy.sh/你的私人频道名
SIZE = 24
INTERVAL = 0.5
COOLDOWN = 60
BLINK_THRESHOLD = 8
BASELINE_SAMPLES = 10
BASELINE_WAIT = 3

# ================= 推送 =================
def send(msg, url):
    try:
        requests.post(url, data=msg.encode("utf-8"), timeout=5)
    except Exception as e:
        print("推送失败: {}".format(e))

# ================= 截图工具 =================
def grab_region(region):
    with mss.mss() as sct:
        monitor = {
            "left":   region[0],
            "top":    region[1],
            "width":  region[2] - region[0],
            "height": region[3] - region[1],
        }
        img = sct.grab(monitor)
        return np.array(Image.frombytes("RGB", img.size, img.rgb))

def get_brightness(arr, target_x, region_left):
    offset = target_x - region_left
    crop = arr[:, max(0, offset - SIZE): offset + SIZE]
    if crop.size == 0:
        return 0.0
    return float(np.mean(crop))

# ================= GUI =================
class MonitorApp(object):
    def __init__(self, root):
        self.root = root
        self.root.title("任务栏消息监控")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")

        self.targets = []
        self.state = {}
        self.running = False
        self.monitor_thread = None
        self.overlay = None  # 悬浮提示窗口

        # 每行: {"frame": tk.Frame, "name_var": StringVar, "status_var": StringVar}
        self.icon_rows = []

        self._build_ui()
        self._add_icon_row()  # 默认一行

    # ------------------------------------------------------------------
    def _build_ui(self):
        BG     = "#1a1a2e"
        BG2    = "#0f3460"
        BG3    = "#0a0a1a"
        ACCENT = "#00d4ff"
        FG     = "#e0e0e0"
        FG_DIM = "#aaaaaa"
        GREEN  = "#00b894"
        RED    = "#d63031"
        BLUE   = "#0077b6"

        self._colors = dict(BG=BG, BG2=BG2, BG3=BG3, ACCENT=ACCENT,
                            FG=FG, FG_DIM=FG_DIM, GREEN=GREEN,
                            RED=RED, BLUE=BLUE)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame",     background=BG)
        style.configure("TLabel",     background=BG, foreground=FG,
                        font=("Microsoft YaHei UI", 10))
        style.configure("H.TLabel",   background=BG, foreground=ACCENT,
                        font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("Dim.TLabel", background=BG, foreground=FG_DIM,
                        font=("Microsoft YaHei UI", 9))

        def sep(parent, row):
            ttk.Separator(parent, orient="horizontal").grid(
                row=row, column=0, columnspan=4,
                sticky="ew", padx=14, pady=5)

        # 标题
        ttk.Label(self.root, text="[ 任务栏消息监控 ]", style="H.TLabel").grid(
            row=0, column=0, columnspan=4, padx=20, pady=(16, 4))

        sep(self.root, 1)

        # 推送地址
        ttk.Label(self.root, text="推送地址:").grid(
            row=2, column=0, padx=(14, 4), pady=5, sticky="e")
        self.ntfy_var = tk.StringVar(value=NTFY_URL)
        ntfy_entry = tk.Entry(self.root, textvariable=self.ntfy_var, width=32,
                 bg=BG2, fg=FG, insertbackground="white",
                 relief="flat", font=("Microsoft YaHei UI", 10),
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground="#333366")
        ntfy_entry.grid(
            row=2, column=1, columnspan=3, padx=(0, 14), pady=5, sticky="ew")

        sep(self.root, 3)

        # 列标题
        ttk.Label(self.root, text="图标名称",
                  font=("Microsoft YaHei UI", 9), foreground=FG_DIM,
                  background=BG).grid(
            row=4, column=0, padx=(14, 4), pady=(2, 0), sticky="w")
        ttk.Label(self.root, text="状态",
                  font=("Microsoft YaHei UI", 9), foreground=FG_DIM,
                  background=BG).grid(
            row=4, column=1, padx=4, pady=(2, 0), sticky="w")

        # 动态图标行容器
        self.rows_frame = tk.Frame(self.root, bg=BG)
        self.rows_frame.grid(row=5, column=0, columnspan=4,
                             padx=14, pady=4, sticky="ew")

        # 添加图标按钮
        tk.Button(self.root, text="+ 添加图标",
                  command=self._add_icon_row,
                  bg=BLUE, fg="white",
                  activebackground="#0096c7", activeforeground="white",
                  relief="flat",
                  font=("Microsoft YaHei UI", 9, "bold"),
                  padx=8, pady=4).grid(
            row=6, column=0, padx=14, pady=4, sticky="w")

        sep(self.root, 7)

        # 控制按钮
        bf = tk.Frame(self.root, bg=BG)
        bf.grid(row=8, column=0, columnspan=4, padx=14, pady=8)

        self.start_btn = tk.Button(bf, text=">> 开始监控",
                                   command=self.start_monitor,
                                   bg=GREEN, fg="white",
                                   activebackground=GREEN, activeforeground="white",
                                   relief="flat",
                                   font=("Microsoft YaHei UI", 11, "bold"),
                                   padx=16, pady=7, state="disabled")
        self.start_btn.pack(side="left", padx=6)

        self.stop_btn = tk.Button(bf, text="|| 停止监控",
                                  command=self.stop_monitor,
                                  bg=RED, fg="white",
                                  activebackground=RED, activeforeground="white",
                                  relief="flat",
                                  font=("Microsoft YaHei UI", 11, "bold"),
                                  padx=16, pady=7, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        sep(self.root, 9)

        # 日志
        ttk.Label(self.root, text="实时状态:").grid(
            row=10, column=0, columnspan=4, padx=14, pady=(4, 2), sticky="w")

        lf2 = tk.Frame(self.root, bg=BG3)
        lf2.grid(row=11, column=0, columnspan=4,
                 padx=14, pady=(0, 14), sticky="ew")
        self.log_text = tk.Text(lf2, height=8, width=52,
                                bg=BG3, fg="#88ff88",
                                insertbackground="white",
                                relief="flat",
                                font=("Consolas", 9),
                                state="disabled", wrap="word",
                                highlightthickness=0)
        self.log_text.pack(side="left", fill="both", expand=True)
        lsb = tk.Scrollbar(lf2, orient="vertical", command=self.log_text.yview)
        lsb.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=lsb.set)

        self.root.grid_columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    def _add_icon_row(self):
        C = self._colors
        idx = len(self.icon_rows) + 1

        row_frame = tk.Frame(self.rows_frame, bg=C["BG"])
        row_frame.pack(fill="x", pady=3)

        # 序号
        tk.Label(row_frame, text="{}. ".format(idx),
                 bg=C["BG"], fg=C["FG_DIM"],
                 font=("Microsoft YaHei UI", 10)).pack(side="left")

        # 名称输入框
        name_var = tk.StringVar(value="图标{}".format(idx))
        tk.Entry(row_frame, textvariable=name_var, width=12,
                 bg=C["BG2"], fg=C["FG"], insertbackground="white",
                 relief="flat", font=("Microsoft YaHei UI", 10),
                 highlightthickness=1, highlightcolor=C["ACCENT"],
                 highlightbackground="#333366").pack(side="left", padx=(2, 6))

        # 状态显示
        status_var = tk.StringVar(value="未记录")
        status_lbl = tk.Label(row_frame, textvariable=status_var,
                 bg=C["BG"], fg=C["FG_DIM"],
                 font=("Microsoft YaHei UI", 9), width=22,
                 anchor="w")
        status_lbl.pack(side="left", padx=(0, 6))

        # 记录坐标按钮
        rec_btn = tk.Button(row_frame, text="记录坐标",
                            bg=C["BLUE"], fg="white",
                            activebackground="#0096c7", activeforeground="white",
                            relief="flat",
                            font=("Microsoft YaHei UI", 9),
                            padx=6, pady=2)
        rec_btn.pack(side="left", padx=(0, 4))

        # 删除按钮
        del_btn = tk.Button(row_frame, text="X",
                            bg="#333355", fg="#ff6688",
                            activebackground="#441133", activeforeground="white",
                            relief="flat",
                            font=("Microsoft YaHei UI", 9, "bold"),
                            padx=5, pady=2)
        del_btn.pack(side="left")

        row_info = {
            "frame":      row_frame,
            "name_var":   name_var,
            "status_var": status_var,
            "status_lbl": status_lbl,
            "rec_btn":    rec_btn,
            "x":          None,
            "y":          None,
        }
        self.icon_rows.append(row_info)

        # 绑定命令（用 index 捕获）
        row_idx = len(self.icon_rows) - 1
        rec_btn.config(command=lambda i=row_idx: self._schedule_capture(i))
        del_btn.config(command=lambda i=row_idx: self._delete_row(i))

    def _delete_row(self, idx):
        if self.running:
            messagebox.showwarning("提示", "监控运行中，请先停止")
            return
        row = self.icon_rows[idx]
        if row["frame"] is None:
            return
        row["frame"].destroy()
        row["frame"] = None
        # 检查是否还有有效记录
        self._refresh_start_btn()

    # ------------------------------------------------------------------
    def _make_overlay(self):
        """创建一个跟随鼠标、始终置顶的悬浮倒计时提示窗口"""
        ov = tk.Toplevel(self.root)
        ov.overrideredirect(True)   # 无边框
        ov.attributes("-topmost", True)
        try:
            ov.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        canvas = tk.Canvas(ov, width=150, height=60, bg="#111133",
                            highlightthickness=2, highlightbackground="#00d4ff")
        canvas.pack()
        text_id = canvas.create_text(75, 22, text="", fill="#00d4ff",
                                      font=("Microsoft YaHei UI", 12, "bold"))
        num_id = canvas.create_text(75, 44, text="", fill="#ffffff",
                                     font=("Microsoft YaHei UI", 16, "bold"))
        ov.canvas = canvas
        ov.text_id = text_id
        ov.num_id = num_id
        return ov

    def _position_overlay_near_cursor(self, ov):
        try:
            x, y = pyautogui.position()
        except Exception:
            x, y = 100, 100
        ov_w, ov_h = 150, 60
        gap = 16
        # 放在鼠标正上方（任务栏图标通常在屏幕底部，上方不容易被挡住）
        pos_x = x - ov_w // 2
        pos_y = y - ov_h - gap
        # 靠近屏幕顶部时兜底改放下方，避免超出屏幕
        if pos_y < 0:
            pos_y = y + gap
        ov.geometry("{}x{}+{}+{}".format(ov_w, ov_h, pos_x, pos_y))

    def _update_overlay_pos_loop(self, ov, idx):
        """让提示框持续跟随鼠标移动，直到该行记录完成"""
        if ov is None or not ov.winfo_exists():
            return
        row = self.icon_rows[idx]
        if row["rec_btn"]["state"] == "disabled" and ov.winfo_exists():
            try:
                self._position_overlay_near_cursor(ov)
            except tk.TclError:
                return
            self.root.after(50, lambda: self._update_overlay_pos_loop(ov, idx))

    # ------------------------------------------------------------------
    def _schedule_capture(self, idx):
        if self.running:
            messagebox.showwarning("提示", "监控运行中，请先停止再记录")
            return
        row = self.icon_rows[idx]
        name = row["name_var"].get().strip()
        if not name:
            messagebox.showwarning("提示", "请先填写图标名称")
            return
        row["rec_btn"].config(state="disabled")
        row["status_var"].set("请将鼠标移到「{}」图标上...".format(name))
        row["status_lbl"].config(fg=self._colors["ACCENT"])

        # 主窗口最小化，避免挡住任务栏图标；同时弹出悬浮提示跟随鼠标
        self.root.iconify()
        self.overlay = self._make_overlay()
        self.overlay.canvas.itemconfig(
            self.overlay.text_id, text="移到「{}」上".format(name))
        self._position_overlay_near_cursor(self.overlay)
        self.root.after(50, lambda: self._update_overlay_pos_loop(self.overlay, idx))

        self._countdown(idx, name, BASELINE_WAIT)

    def _countdown(self, idx, name, remaining):
        row = self.icon_rows[idx]
        if self.overlay is not None and self.overlay.winfo_exists():
            color = "#ff6688" if remaining <= 1 else "#ffffff"
            self.overlay.canvas.itemconfig(
                self.overlay.num_id, text=str(remaining), fill=color)
        if remaining > 0:
            row["status_var"].set("{} 秒后记录...".format(remaining))
            self._beep()
            self.root.after(1000,
                lambda: self._countdown(idx, name, remaining - 1))
        else:
            x, y = pyautogui.position()
            row["x"] = x
            row["y"] = y
            row["status_var"].set("已记录 -> ({}, {})".format(x, y))
            row["status_lbl"].config(fg=self._colors["GREEN"])
            row["rec_btn"].config(state="normal", text="重新记录")
            self.log("记录坐标: [{}] x={}, y={}".format(name, x, y))
            self._beep(final=True)

            if self.overlay is not None and self.overlay.winfo_exists():
                self.overlay.canvas.itemconfig(
                    self.overlay.text_id, text="已记录！", fill="#00b894")
                self.overlay.canvas.itemconfig(self.overlay.num_id, text="✓")
                self.root.after(700, self._close_overlay)

            self.root.deiconify()
            self.root.lift()
            self._refresh_start_btn()

    def _close_overlay(self):
        if self.overlay is not None and self.overlay.winfo_exists():
            self.overlay.destroy()
        self.overlay = None

    def _beep(self, final=False):
        """用系统提示音给出明确的听觉反馈（Windows）"""
        try:
            import winsound
            if final:
                winsound.Beep(1200, 150)
            else:
                winsound.Beep(700, 80)
        except Exception:
            # 非 Windows 平台或不支持时静默忽略
            self.root.bell()

    def _refresh_start_btn(self):
        valid = [r for r in self.icon_rows
                 if r["frame"] is not None and r["x"] is not None]
        if valid:
            self.start_btn.config(state="normal")
        else:
            self.start_btn.config(state="disabled")

    # ------------------------------------------------------------------
    def start_monitor(self):
        valid = [r for r in self.icon_rows
                 if r["frame"] is not None and r["x"] is not None]
        if not valid:
            messagebox.showwarning("提示", "请先记录至少一个图标坐标")
            return
        self.targets = [
            {"name": r["name_var"].get().strip() or "图标", "x": r["x"], "y": r["y"]}
            for r in valid
        ]
        self.running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.log("正在采集基准亮度，请保持屏幕静置...")
        t = threading.Thread(target=self._monitor_loop)
        t.daemon = True
        t.start()
        self.monitor_thread = t

    def stop_monitor(self):
        self.running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.log("监控已停止")

    def _monitor_loop(self):
        ntfy_url = self.ntfy_var.get().strip() or NTFY_URL

        all_x  = [t["x"] for t in self.targets]
        icon_y = self.targets[0]["y"]
        region = (
            min(all_x) - SIZE,
            icon_y - SIZE,
            max(all_x) + SIZE,
            icon_y + SIZE,
        )

        baselines = {t["name"]: [] for t in self.targets}
        for _ in range(BASELINE_SAMPLES):
            try:
                arr = grab_region(region)
                for t in self.targets:
                    baselines[t["name"]].append(
                        get_brightness(arr, t["x"], region[0]))
            except Exception as e:
                self.log("截图异常: {}".format(e))
            time.sleep(0.3)

        now = time.time()
        self.state = {}
        for t in self.targets:
            nm   = t["name"]
            vals = baselines[nm]
            bl   = float(np.mean(vals)) if vals else 128.0
            self.state[nm] = {
                "baseline":        bl,
                "cooldown_active": False,
                "last_flash":      0,
                "last_nonflash":   now,
            }
            self.log("[{}] 基准亮度: {:.2f}".format(nm, bl))

        self.log("开始监控...")

        while self.running:
            try:
                arr = grab_region(region)
                now = time.time()
                for t in self.targets:
                    nm         = t["name"]
                    brightness = get_brightness(arr, t["x"], region[0])
                    diff       = abs(brightness - self.state[nm]["baseline"])

                    if diff > BLINK_THRESHOLD:
                        self.state[nm]["last_flash"] = now
                        if not self.state[nm]["cooldown_active"]:
                            msg = "{} 有新消息！".format(nm)
                            self.log("[{}] 检测到闪烁 (diff={:.1f}) -> 推送通知".format(nm, diff))
                            th = threading.Thread(target=send, args=(msg, ntfy_url))
                            th.daemon = True
                            th.start()
                            self.state[nm]["cooldown_active"] = True
                    else:
                        self.state[nm]["last_nonflash"] = now
                        if (self.state[nm]["cooldown_active"] and
                                now - self.state[nm]["last_flash"] >= COOLDOWN):
                            self.state[nm]["cooldown_active"] = False
                            self.log("[{}] 冷却结束，恢复监控".format(nm))

            except Exception as e:
                self.log("监控异常: {}".format(e))

            time.sleep(INTERVAL)

    # ------------------------------------------------------------------
    def log(self, msg):
        def _write():
            ts = time.strftime("%H:%M:%S")
            self.log_text.config(state="normal")
            self.log_text.insert("end", "[{}] {}\n".format(ts, msg))
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _write)


# ================= 入口 =================
if __name__ == "__main__":
    root = tk.Tk()
    app = MonitorApp(root)
    root.mainloop()
