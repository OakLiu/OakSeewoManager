# OakSeewoManager

全屏远程监视屏蔽工具。基于 Windows `SetWindowDisplayAffinity(WDA_MONITOR)` API，创建透明覆盖层使远程监视/录屏软件只能捕获到黑屏。

## 功能

- **全屏保护** — 整个屏幕在远程监视中变为黑色
- **窗口保护** — 仅保护选中的指定窗口（下层窗口也会被保护，部分窗口暂时无法保护）
- **模拟监控画面** — 实时 BitBlt 屏幕捕获预览（可开关，可调刷新间隔 0.5s–5s）
- **密码保护** — 可开关
- **亮/暗主题** — 跟随系统设置
- **自定关闭行为** — GUI 关闭后可选择是否保持保护

## 使用

```bash
python OakSeewoManager.py
```

首次运行 -> 设置密码 -> 登录后在设置页选择保护模式。

### 命令行参数

| 参数 | 功能 |
|------|------|
| `--overlay` | 启动覆盖层服务（子进程，由 GUI 自动调用） |
| `--picker` | 启动窗口选择器（子进程，由 GUI 自动调用） |
| `--test-window` | 创建测试窗口供注入调试 |

### 打包为 EXE

```bash
build_exe.bat
```

输出到 `OSM_exe\OakSeewoManager.exe`

## 技术原理

```
透明覆盖层 (WS_EX_LAYERED, alpha=1)
  + SetWindowDisplayAffinity(WDA_MONITOR)
  +-- 捕获 API (BitBlt/DDA) 看到纯黑
  +-- 本地显示完全正常
```

窗口模式通过注入 shellcode 到目标进程，从目标进程内部设置 WDA_MONITOR。

## 系统要求

- Windows 8+（推荐 Windows 10 2004+）
- Python 3.13+
- pywebview 5.x

## 技术栈

- Python 3.13 + ctypes (Win32 API)
- pywebview (GUI)
- PyInstaller (EXE 打包)

## 项目结构

```
OakSeewoManager/
  OakSeewoManager.py      # 主程序
  OakSeewoManager.bat     # 双击启动
  build_exe.bat        # EXE 打包脚本
  Oak.ico              # 程序图标
  OSM_exe.zip          # 预打包 EXE
  .gitignore
  README.md
```

## GitHub

https://github.com/OakLiu/OakSeewoManager
