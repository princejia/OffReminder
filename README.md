# 下班提醒

桌面小工具：每天早上 8:40 自动弹窗让你选/输入上班时间，下班前 2 分钟自动启动并弹窗提醒。无需常驻后台。

## 文件

- [off_reminder.py](off_reminder.py) — 主程序
- [启动.bat](启动.bat) — 双击直接打开主界面
- [安装计划任务.bat](安装计划任务.bat) — 注册/卸载 Windows 任务计划
- [install_schedule.ps1](install_schedule.ps1) — 实际注册脚本
- [holidays.json](holidays.json) — 法定节假日 / 调休补班配置（每年更新）

## 一次性安装

1. 双击 [安装计划任务.bat](安装计划任务.bat)
   - 会注册每天 **08:40** 的任务计划，到点自动启动程序并弹出上班时间输入框
2. 输入上班时间后，程序会**自动**再注册一个一次性任务：在「上班时间 + 9 小时 − 20 分钟 − 2 分钟」启动并弹窗提醒下班
3. 关程序也没关系，到点会重新自动拉起

卸载：命令行执行 `安装计划任务.bat uninstall`

## 工作流程

```
08:40  系统调度 ── 启动程序 ── 弹窗选择/输入上班时间
                             │
                             └─ 自动注册一次性任务（下班前 2 分钟）
                                       │
下班-2分钟  系统调度 ── 启动程序 ── 弹窗 + 响铃 提醒下班
```

## 配置

修改 [off_reminder.py](off_reminder.py) 顶部常量即可：

| 常量 | 含义 | 默认 |
|---|---|---|
| `WORK_HOURS` | 工作时长 | 9 |
| `EARLY_LEAVE_MINUTES` | 提前下班分钟 | 20 |
| `REMIND_BEFORE_MINUTES` | 下班前几分钟提醒 | 2 |
| `PROMPT_TIME` | 早上提示时间（程序内倒计时用） | (8, 40) |
| `PRESET_START_TIMES` | 预设上班时间按钮 | 8:20 / 8:25 / 8:30 |

> 改了早上时间后需重跑 [安装计划任务.bat](安装计划任务.bat)（任务计划写死 08:40），或在「任务计划程序」里手工调整 `OffReminder_Morning` 触发器。

## 命令行参数

- `python off_reminder.py` — 普通启动（含界面 + 实时倒计时）
- `python off_reminder.py --morning` — 任务计划用，启动后自动弹输入框
- `python off_reminder.py --remind` — 任务计划用，启动后到点弹下班提醒

## 法定工作日

- 程序在 `--morning` 和 `--remind` 模式下会判断「今天是否法定工作日」，**周末或节假日直接静默退出**，不会打扰你
- 判断规则：周一~周五 − [holidays.json](holidays.json) 中的 `skip` + `force`
  - `skip`：法定节假日（即使周中也不算工作日）
  - `force`：调休补班日（即使周末也算工作日）

### 节假日数据自动更新

数据源：[NateScarlet/holiday-cn](https://github.com/NateScarlet/holiday-cn)（开源维护，国务院公告发布后会同步）

更新方式（任选其一）：
- **主界面点「更新节假日」按钮**（手动）
- **首次启动当年程序时自动后台更新**（无网时静默失败，不影响使用）
- **任务计划「OffReminder_UpdateHolidays」**：[安装计划任务.bat](安装计划任务.bat) 已注册，每周一 09:00 静默更新
- **命令行**：`python off_reminder.py --update-holidays`

> 离线/无网环境也能用，[holidays.json](holidays.json) 里已预置 2026 年数据；之后任意一次联网都会自动补齐

## 验证

打开「任务计划程序」（Win+R 输入 `taskschd.msc`），可在「任务计划程序库」里看到：
- `OffReminder_Morning` — 每天 08:40
- `OffReminder_OffTime` — 一次性，注册后可见
