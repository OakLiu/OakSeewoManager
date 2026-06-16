# ScreenGuard — 项目概述与技术难关

## 项目目标

创建全屏透明覆盖层，利用 Windows `SetWindowDisplayAffinity(WDA_MONITOR)` API，使远程监视/录屏软件捕获到的画面变为全黑，但本地用户完全看不见这个覆盖层（alpha=1/255）。同时支持「窗口保护模式」——只保护选中的特定窗口，其他窗口在监视画面中正常可见。

## 当前架构

```
screen_guard.py (GUI, pywebview)
  └── 启动子进程 screen_guard.py --overlay (覆盖层服务)
        ├── 全屏模式: 创建一个 WS_EX_LAYERED 全屏透明窗口 + WDA_MONITOR ✅ 已实现
        └── 窗口模式: 为目标窗口创建子窗口覆盖层 + WDA_MONITOR ❌ 未实现
```

- 使用 pywebview 5.x 作为 GUI 框架
- 覆盖层在独立子进程中运行（`CREATE_NO_WINDOW`），GUI 关闭后仍可存活
- 通信方式: PID 文件 + 配置文件（config.json）
- 密码保护: SHA256 + config.json

## 已实现的功能

- 全屏保护 ✅（已验证有效，预览画面全黑）
- 密码进入/关闭
- 亮色/暗色/跟随系统 主题
- 模拟远程监视画面（实时 BitBlt 屏幕捕获预览）
- 关闭程序时可选是否保持保护
- 窗口选择器（鼠标单击或空格键选择目标窗口）

## 当前技术难关

### 核心问题: `SetWindowDisplayAffinity` 无法对非自身进程的窗口生效

**问题描述:**

`SetWindowDisplayAffinity(hwnd, WDA_MONITOR)` 是 Windows API，作用是让指定窗口在远程监视/屏幕捕获中显示为黑色（不影响本地显示）。

但这个 API 的**限制**是：「调用进程必须拥有该窗口」。也就是说，我们不能对资源管理器、微信、浏览器等**其他进程**的窗口直接调用此 API。

当我们为其他进程的窗口创建**独立的透明覆盖层**（WS_EX_LAYERED + WS_POPUP）并设置 WDA_MONITOR 时，这个覆盖层在捕获中也未能正确显示为黑色。问题表现：
- 全屏模式（一个覆盖整个桌面的窗口）: ✅ WDA_MONITOR 正常生效
- 覆盖层作为子窗口嵌入目标窗口（WS_CHILD）: ❌ 目标窗口在捕获中仍然正常可见
- 覆盖层作为独立窗口定位在目标窗口上方（WS_POPUP + WS_EX_TOPMOST）: ⚠️ 对本进程的窗口有效，对其他进程无效

**已确认的常量值：**
```
WDA_MONITOR = 0x00000001  ← 曾误写为 0x02 导致错误 87，已修正
WDA_EXCLUDEFROMCAPTURE = 0x00000011
```

### 尝试过的方案

| 方案 | 结果 |
|------|------|
| 全屏 WS_EX_LAYERED 透明覆盖层 + WDA_MONITOR | ✅ 全屏模式有效 |
| 定位在目标窗口上方的独立 POPUP 窗口 + WDA_MONITOR | ❌ 仅对本进程窗口有效，其他进程无效 |
| 作为子窗口嵌入目标 WS_CHILD + WDA_MONITOR | ❌ 无效 |
| 直接对目标窗口调用 SetWindowDisplayAffinity | ❌ 返回 error 5 (ACCESS_DENIED，因为非本进程) |
| WS_EX_TRANSPARENT + alpha=0 完全透明 | ❌ DWM 跳过合成，捕获不到 |
| WS_EX_LAYERED + alpha=1 + WDA_MONITOR | 全屏 ✅，非本进程窗口 ❌ |
| 用 EnumDisplayMonitors 逐个显示器创建 | ❌ 窗口类重复注册问题（已修复） |

### 需要帮助的方向

1. **如何对其他进程的窗口应用 WDA_MONITOR 保护？**
   - DLL 注入方案：创建 DLL 注入到目标进程，在目标进程内调用 SetWindowDisplayAffinity
   - 需要知道如何用 Python + ctypes 实现简单的 shellcode/DLL 注入
   - 或者是否有其他 API 能达到同样效果？

2. **是否有替代 WDA_MONITOR 的技术路线？**
   - DirectComposition overlay？
   - DWM 相关 API？
   - Windows.Graphics.Capture 拦截？

3. **为什么全屏覆盖层有效但独立定位的覆盖层无效？**
   - 全屏: 一个窗口覆盖整个虚拟桌面 → WDA_MONITOR 生效
   - 定位: 同样 WS_EX_LAYERED + alpha=1 + WDA_MONITOR，只是尺寸和位置不同 → 不生效
   - 是否是 DWM 对非全屏分层窗口的合成处理有差异？

### 环境信息

- Windows 11 24H2 (Build 26100)
- Python 3.13.3
- pywebview 5.4
- 非管理员运行
- 目标防护的监视软件: 希沃管家 (Seewo) 等课堂管理软件

## 文件结构

```
D:\Oak\Desktop\OakSeewoManager\
├── screen_guard.py        # 主程序 (GUI + 覆盖层服务 + 窗口选择器)
├── screen_guard.bat       # 双击启动
├── build_exe.bat          # PyInstaller 打包脚本
├── config.json            # 配置文件（密码、主题、目标窗口等）
├── backup\                # 版本备份
└── OSME\                  # 打包输出目录
```
