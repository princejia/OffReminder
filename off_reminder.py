# -*- coding: utf-8 -*-
"""
下班提醒小程序
- 早上 8:30 由系统任务计划启动，弹窗输入上班时间
- 输入后自动注册一次性任务计划，下班前 2 分钟再次启动并提醒
- 主界面可随时查看上班时间、下班时间、剩余时间
"""

import json
import os
import sys
import subprocess
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta

WORK_HOURS = 9                          # 工作时长（小时）
EARLY_LEAVE_MINUTES = 20                # 提前下班分钟数
REMIND_BEFORE_MINUTES = 2               # 下班前几分钟弹提醒
PROMPT_TIME = (8, 30)                   # 早上提示时间 (时, 分)
PRESET_START_TIMES = ["8:20", "8:25", "8:30"]
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work_record.json")

TASK_MORNING = "OffReminder_Morning"    # 每日早上 8:30 任务名
TASK_UNLOCK  = "OffReminder_Unlock"     # 解锁工作站任务名
TASK_OFF     = "OffReminder_OffTime"    # 一次性下班提醒任务名
HOLIDAYS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holidays.json")

# 节假日数据源（NateScarlet/holiday-cn，每年国务院公告后会更新）
HOLIDAYS_URL_TEMPLATE = "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json"
# 镜像备用（jsDelivr CDN，国内访问更快）
HOLIDAYS_URL_MIRROR = "https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/{year}.json"


def _load_holidays_raw():
    """读取整个 holidays.json，返回 dict（含 skip/force/years）。"""
    if not os.path.exists(HOLIDAYS_FILE):
        return {}
    try:
        with open(HOLIDAYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_holidays_raw(data):
    with open(HOLIDAYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_holidays():
    """返回 (skip_set, force_set)，元素为 'YYYY-MM-DD'。"""
    data = _load_holidays_raw()
    return set(data.get("skip", [])), set(data.get("force", []))


def is_workday(d=None):
    """是否为法定工作日：周一到周五 减去节假日 加上调休补班。"""
    d = d or datetime.now().date()
    key = d.strftime("%Y-%m-%d")
    skip, force = _load_holidays()
    if key in force:
        return True
    if key in skip:
        return False
    return d.weekday() < 5  # 0=周一 ... 4=周五


def _fetch_year(year, timeout=8):
    """从远端拉取某年节假日 JSON。返回 days 列表或抛异常。"""
    import urllib.request
    last_err = None
    for url in (HOLIDAYS_URL_TEMPLATE.format(year=year),
                HOLIDAYS_URL_MIRROR.format(year=year)):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OffReminder/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            days = payload.get("days") or []
            if days:
                return days
        except Exception as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("no data")


def update_holidays(years=None):
    """拉取并合并指定年份（默认今年和明年）的节假日数据。
    返回 (ok, msg)。
    """
    if years is None:
        y = datetime.now().year
        years = [y, y + 1]

    data = _load_holidays_raw()
    skip = set(data.get("skip", []))
    force = set(data.get("force", []))
    updated_years = set(data.get("updated_years", []))

    # 先把要更新年份里旧的条目清掉，避免取消的节假日残留
    def _strip_year(s, y):
        return {x for x in s if not x.startswith(f"{y}-")}

    fetched = []
    failed = []
    for y in years:
        try:
            days = _fetch_year(y)
        except Exception as e:
            failed.append(f"{y}({e.__class__.__name__})")
            continue
        skip = _strip_year(skip, y)
        force = _strip_year(force, y)
        for d in days:
            date_str = d.get("date")
            if not date_str:
                continue
            if d.get("isOffDay"):
                skip.add(date_str)
            else:
                force.add(date_str)
        updated_years.add(y)
        fetched.append(str(y))

    new_data = {
        "_说明": "skip = 节假日不上班；force = 调休补班。由 update_holidays 自动维护，"
                 "数据源：github.com/NateScarlet/holiday-cn",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_years": sorted(updated_years),
        "skip": sorted(skip),
        "force": sorted(force),
    }
    _save_holidays_raw(new_data)

    if not fetched:
        return False, f"全部失败：{', '.join(failed)}"
    msg = f"已更新 {', '.join(fetched)} 年"
    if failed:
        msg += f"（{', '.join(failed)} 失败）"
    return True, msg


def auto_update_holidays_if_needed():
    """启动时调用：若当前年份未拉取过，则在后台静默更新一次。"""
    data = _load_holidays_raw()
    updated_years = set(data.get("updated_years", []))
    this_year = datetime.now().year
    if this_year in updated_years:
        return
    import threading
    threading.Thread(target=lambda: update_holidays([this_year, this_year + 1]),
                     daemon=True).start()


def _pythonw_path():
    """优先使用 pythonw.exe（无黑窗），找不到则用 python.exe。"""
    exe = sys.executable
    cand = exe.replace("python.exe", "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def _script_path():
    return os.path.abspath(__file__)


def register_off_task(off_time):
    """注册一次性任务计划：在 off_time - REMIND_BEFORE_MINUTES 分钟时启动程序提醒。"""
    trigger = off_time - timedelta(minutes=REMIND_BEFORE_MINUTES)
    if trigger <= datetime.now():
        return False, "触发时间已过，未注册"

    pythonw = _pythonw_path()
    script = _script_path()
    # 用 PowerShell Register-ScheduledTask（不依赖系统日期格式）
    at = trigger.strftime("%Y-%m-%dT%H:%M:%S")
    ps = (
        f'$a = New-ScheduledTaskAction -Execute "{pythonw}" '
        f'-Argument \'"{script}" --remind\'; '
        f'$t = New-ScheduledTaskTrigger -Once -At "{at}"; '
        f'$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries '
        f'-DontStopIfGoingOnBatteries; '
        f'Register-ScheduledTask -TaskName "{TASK_OFF}" -Action $a -Trigger $t '
        f'-Settings $s -Force | Out-Null'
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return True, f"将于 {trigger.strftime('%H:%M')} 启动提醒"
        return False, (r.stderr or r.stdout or "未知错误").strip().splitlines()[-1]
    except Exception as e:
        return False, str(e)


class StartTimeDialog(tk.Toplevel):
    """上班时间选择对话框：预设按钮 + 手动输入"""

    def __init__(self, parent, default=""):
        super().__init__(parent)
        self.title("输入上班时间")
        self.resizable(False, False)
        self.result = None
        self.transient(parent)
        self.grab_set()

        tk.Label(self, text="请选择或输入上班时间：", font=("Microsoft YaHei", 11)).pack(padx=20, pady=(15, 8))

        btn_frame = tk.Frame(self)
        btn_frame.pack(padx=20, pady=4)
        for i, t in enumerate(PRESET_START_TIMES):
            tk.Button(btn_frame, text=t, width=8,
                      command=lambda v=t: self._pick(v)).grid(row=0, column=i, padx=4)

        tk.Label(self, text="或手动输入 (HH:MM)：", font=("Microsoft YaHei", 10)).pack(pady=(12, 4))
        self.entry = tk.Entry(self, font=("Microsoft YaHei", 11), justify="center", width=12)
        self.entry.insert(0, default)
        self.entry.pack()
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda e: self._ok())

        bottom = tk.Frame(self)
        bottom.pack(pady=12)
        tk.Button(bottom, text="确定", width=8, command=self._ok).grid(row=0, column=0, padx=6)
        tk.Button(bottom, text="取消", width=8, command=self._cancel).grid(row=0, column=1, padx=6)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        # 居中到父窗口
        try:
            px = parent.winfo_rootx() + parent.winfo_width() // 2 - self.winfo_width() // 2
            py = parent.winfo_rooty() + parent.winfo_height() // 2 - self.winfo_height() // 2
            self.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        except Exception:
            pass
        self.wait_window(self)

    def _pick(self, value):
        self.result = value
        self.destroy()

    def _ok(self):
        v = self.entry.get().strip()
        if not v:
            messagebox.showwarning("提示", "请输入时间", parent=self)
            return
        self.result = v
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


def load_record():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_record(record):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


class OffReminderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("下班提醒")
        self.root.geometry("360x260")
        self.root.resizable(False, False)

        self.start_time = None  # datetime
        self.off_time = None    # datetime
        self.notified = False
        self.prompted_today = False

        # 界面
        self.lbl_title = tk.Label(root, text="下班提醒", font=("Microsoft YaHei", 16, "bold"))
        self.lbl_title.pack(pady=8)

        self.lbl_start = tk.Label(root, text="上班时间：未设置", font=("Microsoft YaHei", 11))
        self.lbl_start.pack(pady=4)

        self.lbl_off = tk.Label(root, text="下班时间：—", font=("Microsoft YaHei", 11))
        self.lbl_off.pack(pady=4)

        self.lbl_remain = tk.Label(root, text="剩余时间：—", font=("Microsoft YaHei", 12, "bold"), fg="#0066cc")
        self.lbl_remain.pack(pady=8)

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="设置上班时间", width=12, command=self.set_start_time).grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="清除", width=6, command=self.clear_record).grid(row=0, column=1, padx=5)
        tk.Button(btn_frame, text="更新节假日", width=10, command=self.update_holidays_action).grid(row=0, column=2, padx=5)

        self.lbl_now = tk.Label(root, text="", font=("Microsoft YaHei", 9), fg="gray")
        self.lbl_now.pack(side="bottom", pady=4)

        # 加载今天已有记录
        self.load_today()

        # 启动定时器
        self.tick()

    # --------------- 数据 ---------------
    def today_key(self):
        return datetime.now().strftime("%Y-%m-%d")

    def load_today(self):
        record = load_record()
        today = record.get(self.today_key())
        if today and today.get("start"):
            try:
                self.start_time = datetime.strptime(today["start"], "%Y-%m-%d %H:%M:%S")
                self.off_time = self.start_time + timedelta(hours=WORK_HOURS, minutes=-EARLY_LEAVE_MINUTES)
                self.prompted_today = True
                self.notified = bool(today.get("notified", False))
            except Exception:
                self.start_time = None

    def save_today(self):
        record = load_record()
        record[self.today_key()] = {
            "start": self.start_time.strftime("%Y-%m-%d %H:%M:%S") if self.start_time else "",
            "notified": self.notified,
        }
        save_record(record)

    # --------------- 操作 ---------------
    def set_start_time(self):
        default = datetime.now().strftime("%H:%M")
        dlg = StartTimeDialog(self.root, default=default)
        s = dlg.result
        if not s:
            return
        s = s.strip()
        try:
            hh, mm = s.split(":")
            now = datetime.now()
            start = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            self.start_time = start
            self.off_time = start + timedelta(hours=WORK_HOURS, minutes=-EARLY_LEAVE_MINUTES)
            self.notified = False
            self.prompted_today = True
            self.save_today()
            self.refresh_labels()
            ok, msg = register_off_task(self.off_time)
            extra = f"\n\n下班提醒任务：{msg}" if ok else f"\n\n⚠ 任务计划注册失败：{msg}"
            messagebox.showinfo(
                "已设置",
                f"上班时间：{start.strftime('%H:%M')}\n"
                f"下班时间：{self.off_time.strftime('%H:%M')}\n"
                f"（满 {WORK_HOURS} 小时，提前 {EARLY_LEAVE_MINUTES} 分钟）" + extra
            )
        except Exception:
            messagebox.showerror("格式错误", "请按 HH:MM 格式输入，例如 08:30")

    def clear_record(self):
        if not messagebox.askyesno("确认", "确定要清除今天的记录吗？"):
            return
        record = load_record()
        record.pop(self.today_key(), None)
        save_record(record)
        self.start_time = None
        self.off_time = None
        self.notified = False
        self.prompted_today = False
        self.refresh_labels()

    def update_holidays_action(self):
        """手动触发节假日更新。"""
        self.lbl_now.config(text="正在更新节假日…")
        self.root.update_idletasks()
        ok, msg = update_holidays()
        if ok:
            messagebox.showinfo("节假日更新", msg)
        else:
            messagebox.showerror("节假日更新失败", msg + "\n\n请检查网络，或手动编辑 holidays.json")

    # --------------- 显示与定时 ---------------
    def refresh_labels(self):
        if self.start_time:
            self.lbl_start.config(text=f"上班时间：{self.start_time.strftime('%H:%M')}")
            self.lbl_off.config(text=f"下班时间：{self.off_time.strftime('%H:%M')}（满{WORK_HOURS}小时提前{EARLY_LEAVE_MINUTES}分）")
            remain = self.off_time - datetime.now()
            if remain.total_seconds() <= 0:
                self.lbl_remain.config(text="已到下班时间！", fg="#cc0000")
            else:
                total = int(remain.total_seconds())
                h, rem = divmod(total, 3600)
                m, s = divmod(rem, 60)
                self.lbl_remain.config(text=f"剩余时间：{h:02d}:{m:02d}:{s:02d}", fg="#0066cc")
        else:
            self.lbl_start.config(text="上班时间：未设置")
            self.lbl_off.config(text="下班时间：—")
            self.lbl_remain.config(text="剩余时间：—", fg="#0066cc")
        self.lbl_now.config(text=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def tick(self):
        now = datetime.now()

        # 早上 8:30 提示输入上班时间（若今天还没设置过）
        if (not self.prompted_today
                and now.hour == PROMPT_TIME[0]
                and now.minute >= PROMPT_TIME[1]
                and now.hour < 12):
            self.prompted_today = True  # 先标记，避免循环弹
            self.root.after(100, self.prompt_start_time)

        # 满 9 小时提醒
        if self.off_time and not self.notified and now >= self.off_time:
            self.notified = True
            self.save_today()
            self.root.after(100, self.notify_off)

        self.refresh_labels()
        self.root.after(1000, self.tick)

    def prompt_start_time(self, close_after=False):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.attributes("-topmost", False)
        self.set_start_time()
        if close_after:
            # 任务计划拉起场景：关闭成功提示后自动关闭输入窗口
            self.root.destroy()

    def notify_off(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        try:
            self.root.bell()
        except Exception:
            pass
        messagebox.showinfo(
            "下班提醒",
            f"可以下班啦！（已工作 {WORK_HOURS} 小时 - {EARLY_LEAVE_MINUTES} 分钟）"
        )
        self.root.attributes("-topmost", False)


def main():
    args = set(sys.argv[1:])

    # CLI: 单独调用更新
    if "--update-holidays" in args:
        ok, msg = update_holidays()
        print(("OK: " if ok else "FAIL: ") + msg)
        return

    # 被任务计划拉起时，非法定工作日直接退出，不骚扰
    if ("--morning" in args or "--remind" in args or "--unlock" in args) and not is_workday():
        return

    # 解锁触发：今天已记录过上班时间则静默退出，否则把当前时间作为默认值弹窗
    if "--unlock" in args:
        record = load_record()
        today_key = datetime.now().strftime("%Y-%m-%d")
        if record.get(today_key, {}).get("start"):
            return

    # 启动后台自动检查节假日数据
    auto_update_holidays_if_needed()

    root = tk.Tk()
    app = OffReminderApp(root)

    if "--remind" in args:
        # 被任务计划拉起：在下班点提醒后退出
        def _do_remind():
            if app.off_time and not app.notified:
                # 如果还没到点，等到点再弹；tick 会自动处理
                pass
            else:
                app.notify_off()
                app.notified = True
                app.save_today()
        root.after(500, _do_remind)
    elif "--morning" in args:
        # 被任务计划拉起：直接弹出输入框，设置完成后自动关闭窗口
        if not app.start_time:
            root.after(300, lambda: app.prompt_start_time(close_after=True))
    elif "--unlock" in args:
        # 解锁工作站触发：弹出输入框（默认值即当前时间），设置完成后自动关闭窗口
        if not app.start_time:
            root.after(300, lambda: app.prompt_start_time(close_after=True))

    root.mainloop()


if __name__ == "__main__":
    main()
