#!/usr/bin/env python3
"""
ScreenGuard v3.0 — 全屏远程监视屏蔽 (pywebview 内嵌窗口版)
===========================================================

基于 SetWindowDisplayAffinity(WDA_MONITOR) 创建全屏透明覆盖层，
使远程监视/录屏软件只能捕获到黑屏。

使用方式:
  双击 screen_guard.bat 启动
  首次运行 -> 设置密码
  后续运行 -> 输入密码进入控制面板
  关闭窗口 -> 保护继续后台运行 (控制台 Ctrl+C 完全退出)
"""

import ctypes
from ctypes import wintypes
import time
import json
import hashlib
import os
import sys
import subprocess
import struct
import base64

# =========================================================================
# Windows API 类型 (必须在 WNDCLASSEXW 之前)
# =========================================================================

if ctypes.sizeof(ctypes.c_void_p) == 8:
    LONG_PTR = ctypes.c_longlong
else:
    LONG_PTR = ctypes.c_long

WNDPROC = ctypes.WINFUNCTYPE(
    LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)

# =========================================================================
# Python 3.13 兼容: 手动定义 WNDCLASSEXW
# =========================================================================

if not hasattr(wintypes, 'WNDCLASSEXW'):
    class _WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ('cbSize',        wintypes.UINT),
            ('style',         wintypes.UINT),
            ('lpfnWndProc',   WNDPROC),
            ('cbClsExtra',    ctypes.c_int),
            ('cbWndExtra',    ctypes.c_int),
            ('hInstance',     wintypes.HINSTANCE),
            ('hIcon',         wintypes.HANDLE),
            ('hCursor',       wintypes.HANDLE),
            ('hbrBackground', wintypes.HANDLE),
            ('lpszMenuName',  wintypes.LPCWSTR),
            ('lpszClassName', wintypes.LPCWSTR),
            ('hIconSm',       wintypes.HANDLE),
        ]
    wintypes.WNDCLASSEXW = _WNDCLASSEXW

# =========================================================================
# Windows API 函数类型绑定
# =========================================================================

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Set/Get Window Display Affinity
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
user32.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowDisplayAffinity.restype = wintypes.BOOL

# Layered Window
user32.SetLayeredWindowAttributes.argtypes = [
    wintypes.HWND, wintypes.DWORD, wintypes.BYTE, wintypes.DWORD
]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

# CreateWindowExW
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HANDLE, wintypes.HINSTANCE, wintypes.LPVOID
]
user32.CreateWindowExW.restype = wintypes.HWND

# RegisterClassExW / UnregisterClassW
user32.RegisterClassExW.argtypes = [ctypes.POINTER(wintypes.WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
user32.UnregisterClassW.restype = wintypes.BOOL

# DestroyWindow
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL

# PeekMessageW
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG), wintypes.HWND,
    wintypes.UINT, wintypes.UINT, wintypes.UINT
]
user32.PeekMessageW.restype = wintypes.BOOL

# PostMessage / PostThreadMessage
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

# PostQuitMessage
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None

# GetSystemMetrics
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

# DefWindowProcW
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LONG_PTR

# window info
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
if not hasattr(wintypes, 'POINT'):
    class POINT(ctypes.Structure):
        _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]
    wintypes.POINT = POINT
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.SetCursor.argtypes = [wintypes.HANDLE]
user32.SetCursor.restype = wintypes.HANDLE
user32.LoadCursorW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ScreenToClient.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL

gdi32 = ctypes.windll.gdi32
user32.DrawFocusRect = ctypes.windll.user32.DrawFocusRect
user32.DrawFocusRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT)]
user32.DrawFocusRect.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetBkMode.restype = ctypes.c_int
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.DWORD]
gdi32.SetTextColor.restype = wintypes.DWORD
user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HANDLE]
user32.FillRect.restype = ctypes.c_int

# HDC type for argtypes
wintypes.HDC = ctypes.c_void_p

# PAINTSTRUCT
if not hasattr(wintypes, 'PAINTSTRUCT'):
    class _PAINTSTRUCT(ctypes.Structure):
        _fields_ = [
            ('hdc', wintypes.HDC),
            ('fErase', ctypes.c_int),
            ('rcPaint', wintypes.RECT),
            ('fRestore', ctypes.c_int),
            ('fIncUpdate', ctypes.c_int),
            ('rgbReserved', ctypes.c_byte * 32),
        ]
    wintypes.PAINTSTRUCT = _PAINTSTRUCT

user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.PAINTSTRUCT)]
user32.BeginPaint.restype = wintypes.HDC
user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.PAINTSTRUCT)]
user32.EndPaint.restype = wintypes.BOOL
user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT]
user32.DrawTextW.restype = ctypes.c_int
gdi32.TextOutW.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
gdi32.TextOutW.restype = wintypes.BOOL
gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
gdi32.CreateSolidBrush.restype = wintypes.HANDLE
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HANDLE
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
gdi32.SelectObject.restype = wintypes.HANDLE
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.StretchBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.StretchBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HANDLE, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
gdi32.GetDIBits.restype = ctypes.c_int
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT), wintypes.BOOL]
user32.InvalidateRect.restype = wintypes.BOOL
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HANDLE
user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LONG_PTR

user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p, wintypes.LPARAM]
user32.EnumDisplayMonitors.restype = wintypes.BOOL

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('pt', wintypes.POINT),
        ('mouseData', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_void_p),
    ]

# MARGINS 结构 (Python 3.13 wintypes 不含此类型)
if not hasattr(wintypes, 'MARGINS'):
    class _MARGINS(ctypes.Structure):
        _fields_ = [('cxLeftWidth', ctypes.c_int), ('cxRightWidth', ctypes.c_int),
                    ('cyTopHeight', ctypes.c_int), ('cyBottomHeight', ctypes.c_int)]
    wintypes.MARGINS = _MARGINS

dwmapi = ctypes.windll.dwmapi
dwmapi.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.c_void_p]
dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long

# kernel32 & shell32
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.VirtualAllocEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
kernel32.VirtualAllocEx.restype = wintypes.LPVOID
kernel32.WriteProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.WriteProcessMemory.restype = wintypes.BOOL
kernel32.CreateRemoteThread.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
kernel32.CreateRemoteThread.restype = wintypes.HANDLE
kernel32.VirtualFreeEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD]
kernel32.VirtualFreeEx.restype = wintypes.BOOL
kernel32.GetExitCodeThread.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetExitCodeThread.restype = wintypes.BOOL
kernel32.GetProcAddress.argtypes = [wintypes.HANDLE, ctypes.c_char_p]
kernel32.GetProcAddress.restype = ctypes.c_void_p
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HANDLE
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateProcess.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

# =========================================================================
# 常量
# =========================================================================

WS_EX_LAYERED     = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW  = 0x00000080
WS_EX_TOPMOST     = 0x00000008
WS_EX_NOACTIVATE  = 0x08000000

WS_POPUP  = 0x80000000
WS_CHILD  = 0x40000000
WS_VISIBLE = 0x10000000

WDA_NONE               = 0x00000000
WDA_MONITOR            = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011
LWA_ALPHA = 0x00000002

SM_XVIRTUALSCREEN  = 76
SM_YVIRTUALSCREEN  = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_CMONITORS       = 80

WM_DESTROY      = 0x0002
WM_QUIT         = 0x0012
WM_PAINT        = 0x000F
WM_SETCURSOR    = 0x0020
WM_NCHITTEST    = 0x0084
WM_MOUSEMOVE    = 0x0200
WM_LBUTTONDOWN  = 0x0201
WM_LBUTTONUP    = 0x0202
HTTRANSPARENT   = -1
DT_CENTER        = 0x0001
DT_VCENTER       = 0x0004
DT_SINGLELINE    = 0x0020
PM_REMOVE = 1

# =========================================================================
# 配置管理
# =========================================================================

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
PID_FILE = os.path.join(BASE_DIR, '.overlay_pid')
ERR_FILE = os.path.join(BASE_DIR, '.overlay_err')

PICKER_FILE = os.path.join(BASE_DIR, '.picker_result')

def _read_pid():
    try:
        with open(PID_FILE, 'r') as f:
            return int(f.read().strip())
    except (IOError, ValueError, FileNotFoundError):
        return None

def _write_pid():
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

def _delete_pid_file():
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass
    except PermissionError:
        import time
        time.sleep(0.2)
        try:
            os.remove(PID_FILE)
        except:
            pass

def _process_exists(pid):
    if pid is None:
        return False
    handle = kernel32.OpenProcess(0x0400, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False

_WINDOW_STAT_PROPS = {0: 'class_name', 260: 'ex_style', 8: 'style'}
def _get_window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value

def _get_window_title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value

def _get_window_pid(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value

def _get_window_path(hwnd):
    pid = _get_window_pid(hwnd)
    if not pid:
        return ''
    try:
        h = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
        if not h:
            return ''
        buf = ctypes.create_unicode_buffer(1024)
        kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(wintypes.DWORD(1024)))
        kernel32.CloseHandle(h)
        return buf.value
    except:
        return ''

def _scan_windows_by_target(target):
    """枚举窗口，返回匹配 target 的 HWND 列表"""
    result = []
    tg_class = (target.get('class', '') or '').strip()
    tg_path = (target.get('path', '') or '').lower().strip()
    if not tg_class and not tg_path:
        return result  # 无匹配条件，返回空
    ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
    @ENUMPROC
    def enum_proc(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return 1
        if tg_class and _get_window_class(hwnd) != tg_class:
            return 1
        if tg_path:
            p = _get_window_path(hwnd).lower()
            if tg_path not in p and p not in tg_path:
                return 1
        result.append(hwnd)
        return 1
    user32.EnumWindows(enum_proc, 0)
    return result

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_config(data):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except IOError:
        return False

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# =========================================================================
# 覆盖层管理器 (后台线程)
# =========================================================================

class OverlayManager:
    """通过独立子进程管理全屏透明覆盖层"""

    def __init__(self):
        self._process = None

    def create_overlay(self):
        if self.is_active():
            return True
        _delete_pid_file()
        try:
            os.remove(ERR_FILE)
        except FileNotFoundError:
            pass
        if getattr(sys, 'frozen', False):
            overlay_args = [sys.executable, '--overlay']
        else:
            overlay_args = [sys.executable, os.path.abspath(__file__), '--overlay']
        try:
            self._process = subprocess.Popen(
                overlay_args,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
        except Exception as e:
            print(f"[OverlayManager] 启动子进程失败: {e}")
            self._process = None
            return False
        # 等待最多 12 秒 (注入可能耗时)
        for _ in range(120):
            if _read_pid() is not None:
                try:
                    out = self._process.stdout.read() if self._process and self._process.stdout else b''
                    if out: print(out.decode('utf-8', errors='replace'), end='')
                except: pass
                return True
            if os.path.exists(ERR_FILE):
                try:
                    with open(ERR_FILE, 'r') as f:
                        print(f"[覆盖层] 子进程错误: {f.read()}")
                except: pass
                if self._process and self._process.poll() is not None:
                    return False
            time.sleep(0.1)
        # 超时: 进程可能还在初始化, 乐观返回 True
        return _read_pid() is not None

    def destroy_overlay(self):
        if not self.is_active():
            return True
        pid = _read_pid()
        _delete_pid_file()
        if pid is not None and _process_exists(pid):
            for _ in range(3):
                if not _process_exists(pid):
                    break
                time.sleep(0.1)
            if _process_exists(pid):
                h = kernel32.OpenProcess(0x0001, False, pid)
                if h:
                    kernel32.TerminateProcess(h, 0)
                    kernel32.CloseHandle(h)
        self._process = None
        return True

    def is_active(self):
        pid = _read_pid()
        if pid is None:
            return False
        alive = _process_exists(pid)
        if not alive:
            _delete_pid_file()
        return alive


def _inj_log(msg):
    with open(os.path.join(BASE_DIR, '.inject.log'), 'a', encoding='utf-8') as f:
        f.write(f"{msg}\n")

def _inject_wda(target_hwnds):
    """对目标窗口所属进程注入 shellcode 设置 WDA_MONITOR"""
    addr = ctypes.cast(user32.SetWindowDisplayAffinity, ctypes.c_void_p).value
    if not addr:
        _inj_log("FAIL: cannot find SetWindowDisplayAffinity address")
        return False

    # 所有目标均用注入（即使自身进程的窗口，子进程也无权直接调用）
    exit_addr = ctypes.cast(kernel32.ExitThread, ctypes.c_void_p).value or 0
    success = True
    for hwnd_val in target_hwnds:
        pid = _get_window_pid(hwnd_val)
        _safe_print(f"  injecting PID {pid} HWND={hwnd_val}")
        _inj_log(f"inject PID={pid} HWND={hwnd_val}")

        # Shellcode: rax = SetWindowDisplayAffinity(hwnd, 1); ExitThread(rax)
        sc = b'\x48\xB9' + struct.pack('<Q', hwnd_val)  # mov rcx, hwnd (arg1)
        sc += b'\xBA\x01\x00\x00\x00'                    # mov edx, 1  (arg2: WDA_MONITOR)
        sc += b'\x48\xB8' + struct.pack('<Q', addr)      # mov rax, wda_func
        sc += b'\xFF\xD0'                                 # call rax → eax = result
        if exit_addr:
            sc += b'\x8B\xC8'                             # mov ecx, eax (exit code = WDA result)
            sc += b'\x48\xB8' + struct.pack('<Q', exit_addr)
            sc += b'\xFF\xD0'                             # call ExitThread(ecx)
        else:
            sc += b'\xC3'                                 # ret (fallback)

        hProc = kernel32.OpenProcess(0x1F0FFF, False, pid)
        if not hProc:
            _safe_print(f"  OpenProcess({pid}) FAILED (need admin)")
            _inj_log(f"OpenProcess FAILED PID={pid}")
            success = False
            continue

        mem = kernel32.VirtualAllocEx(hProc, None, len(sc), 0x1000, 0x40)
        if not mem:
            _safe_print(f"  VirtualAllocEx FAILED")
            _inj_log(f"VirtualAllocEx FAILED PID={pid}")
            kernel32.CloseHandle(hProc)
            success = False
            continue

        written = ctypes.c_size_t()
        kernel32.WriteProcessMemory(hProc, mem, sc, len(sc), ctypes.byref(written))
        tid = wintypes.DWORD()
        hThread = kernel32.CreateRemoteThread(hProc, None, 0, mem, None, 0, ctypes.byref(tid))
        if not hThread:
            _safe_print(f"  CreateRemoteThread FAILED")
            _inj_log(f"CreateRemoteThread FAILED PID={pid}")
            kernel32.VirtualFreeEx(hProc, mem, 0, 0x8000)
            kernel32.CloseHandle(hProc)
            success = False
            continue

        ret_wait = kernel32.WaitForSingleObject(hThread, 10000)
        exit_code = wintypes.DWORD()
        kernel32.GetExitCodeThread(hThread, ctypes.byref(exit_code))
        _safe_print(f"  thread: wait={ret_wait}, exit_code={exit_code.value}")
        _inj_log(f"inject PID={pid} wait={ret_wait} exit={exit_code.value}")
        if exit_code.value in (0, 1):
            # 验证 WDA_MONITOR 是否设置成功
            aff = wintypes.DWORD()
            ver = user32.GetWindowDisplayAffinity(hwnd_val, ctypes.byref(aff))
            if ver and aff.value == WDA_MONITOR:
                _safe_print(f"  [OK] PID {pid} HWND {hwnd_val} WDA_MONITOR set")
            elif ver:
                _safe_print(f"  [CHECK] PID {pid} affinity={aff.value} (not WDA_MONITOR)")
            else:
                _safe_print(f"  [CHECK] PID {pid} GetWindowDisplayAffinity failed")
        elif exit_code.value == 259:
            _safe_print(f"  [TIMEOUT] PID {pid} thread still running")
            success = False
        else:
            _safe_print(f"  [FAIL] PID {pid} thread error (exit=0x{exit_code.value:08x})")
            success = False

        kernel32.CloseHandle(hThread)
        kernel32.VirtualFreeEx(hProc, mem, 0, 0x8000)
        kernel32.CloseHandle(hProc)
    return success


_overlay_hwnds = []  # 所有覆盖层窗口 (fullscreen 模式可能有多个)

def _test_window_main():
    """创建测试窗口供注入测试使用"""
    cls = "SGTestWindow"
    hinst = kernel32.GetModuleHandleW(None)
    wc = wintypes.WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(wintypes.WNDCLASSEXW)
    wc.style = 0
    wc.lpfnWndProc = WNDPROC(lambda h,m,w,l: 0 if m==2 else user32.DefWindowProcW(h,m,w,l))
    wc.hInstance = hinst
    wc.hbrBackground = gdi32.CreateSolidBrush(0x00ff6600)  # 蓝色背景
    wc.lpszClassName = cls
    wc.lpszMenuName = None
    atom = user32.RegisterClassExW(ctypes.byref(wc))
    if not atom:
        return 1
    sw = user32.GetSystemMetrics(0); sh = user32.GetSystemMetrics(1)
    hwnd = user32.CreateWindowExW(0, cls, "SG TEST", 0x00CA0000 | 0x10000000,
        sw//2-200, sh//2-150, 400, 300, None, None, hinst, None)
    if not hwnd:
        user32.UnregisterClassW(cls, hinst)
        return 1
    # 显示测试信息
    hdc = user32.GetDC(hwnd)
    gdi32.SetBkMode(hdc, 1); gdi32.SetTextColor(hdc, 0x00ffffff)
    texts = ["SG Test Window", "Select this window via picker", "Then test injection", "Press any key to close"]
    for i, t in enumerate(texts):
        gdi32.TextOutW(hdc, 20, 30 + i * 30, t, len(t))
    user32.ReleaseDC(hwnd, hdc)
    _safe_print(f"[TestWindow] HWND={hwnd} — select this window in the picker")
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    user32.DestroyWindow(hwnd)
    user32.UnregisterClassW(cls, hinst)
    return 0

def _create_overlay_window(class_name, hinstance):
    """创建全屏覆盖层窗口 (类已在调用方注册)"""
    global _overlay_hwnds
    _overlay_hwnds = []
    ex = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    hwnd = user32.CreateWindowExW(ex, class_name, "SG",
        WS_POPUP | WS_VISIBLE, vx, vy, vw, vh, None, None, hinstance, None)
    if not hwnd:
        return None, None, None
    user32.SetLayeredWindowAttributes(hwnd, 0, 1, LWA_ALPHA)
    if user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR):
        _overlay_hwnds.append(hwnd)
        _safe_print("[覆盖层] 已创建 (WDA_MONITOR)")
        return hwnd, class_name, hinstance
    if user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
        _overlay_hwnds.append(hwnd)
        _safe_print("[覆盖层] 已创建 (WDA_EXCLUDE)")
        return hwnd, class_name, hinstance
    user32.DestroyWindow(hwnd)
    _safe_print("[覆盖层] 创建失败")
    return None, None, None


def _overlay_wndproc(hwnd, msg, wparam, lparam):
    """覆盖层窗口过程 (在 --overlay 子进程中)"""
    if msg == WM_DESTROY:
        return 0
    if msg == WM_NCHITTEST:
        return HTTRANSPARENT
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _overlay_service_main():
    """覆盖层服务主函数 — 在独立子进程中运行"""
    global _overlay_hwnds
    try:
        _delete_pid_file()
        _write_pid()
        _ov_service()
    except Exception as e:
        import traceback
        with open(ERR_FILE, 'w', encoding='utf-8') as f:
            f.write(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
        _delete_pid_file()
    return 0

_OV_LOG = os.path.join(BASE_DIR, '.overlay_debug.log')
def _ov_log(msg):
    with open(_OV_LOG, 'a', encoding='utf-8') as f:
        f.write(f"{msg}\n")

# Forward declaration for _create_overlay_window

def _safe_print(msg):
    try:
        print(msg, flush=True)
    except (OSError, UnicodeEncodeError):
        try:
            ascii_msg = msg.encode('ascii', errors='replace').decode('ascii')
            print(ascii_msg, flush=True)
        except:
            pass

def _ov_service():
    global _overlay_hwnds
    _ov_log("=== overlay service started ===")
    _safe_print(f"[debug] config_path={CONFIG_PATH}, pid_file={PID_FILE}")
    config = load_config()
    target_mode = config.get('target_mode', 'fullscreen')
    targets = config.get('target_windows', [])
    _ov_log(f"target_mode={target_mode}, targets_count={len(targets)}")
    class_name = "ScreenGuardOverlay"
    hinstance = kernel32.GetModuleHandleW(None)
    wc = wintypes.WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(wintypes.WNDCLASSEXW)
    wc.style = 0
    cb = WNDPROC(_overlay_wndproc)
    wc.lpfnWndProc = cb
    wc.hInstance = hinstance
    wc.hbrBackground = None
    wc.lpszClassName = class_name
    wc.lpszMenuName = None
    atom = user32.RegisterClassExW(ctypes.byref(wc))
    if not atom:
        _ov_log("RegisterClassExW failed!")
        return 1

    _safe_print(f"[debug] target_mode='{target_mode}', targets={len(targets)}")
    overlays = []
    if target_mode == 'window' and targets:
        all_targets = []
        for tg in targets:
            hwnds = _scan_windows_by_target(tg)
            _ov_log(f"target '{tg.get('title','')}': found {len(hwnds)} windows")
            all_targets.extend(hwnds)
        if all_targets:
            _safe_print(f"  found {len(all_targets)} target(s), creating overlays...")
            for hw in all_targets:
                ov = _create_per_window_overlay(hw, class_name, hinstance)
                if ov:
                    overlays.append((ov, hw))
            _safe_print(f"  created {len(overlays)} overlay(s)")
        else:
            _ov_log("no matching windows found")
            _safe_print("  no matching windows")
    else:
        _ov_log("creating full-screen overlay...")
        hwnd, _, _ = _create_overlay_window(class_name, hinstance)
        _ov_log(f"full-screen overlay: {hwnd}")
        if hwnd is None:
            _ov_log("FAILED: hwnd is None")
            return 1

    msg = wintypes.MSG()
    tick = 0
    while _read_pid() is not None:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            if msg.message == WM_QUIT:
                _delete_pid_file()
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        # 每 2.5 秒更新窗口位置
        tick += 1
        if overlays and tick % 25 == 0:
            new_list = []
            for ov, target in overlays:
                visible = False
                if target and user32.IsWindow(target):
                    if user32.IsWindowVisible(target):
                        # 检查目标是否被其他窗口遮挡
                        rect = wintypes.RECT()
                        user32.GetWindowRect(target, ctypes.byref(rect))
                        cx = (rect.left + rect.right) // 2
                        cy = (rect.top + rect.bottom) // 2
                        pt = wintypes.POINT(cx, cy)
                        top = user32.WindowFromPoint(pt)
                        visible = (top == target)
                    if visible:
                        user32.SetWindowPos(ov, 0, rect.left, rect.top,
                            rect.right - rect.left, rect.bottom - rect.top, 0x0010)
                        user32.ShowWindow(ov, 1)
                        new_list.append((ov, target))
                    else:
                        user32.ShowWindow(ov, 0)  # 被遮挡时隐藏
                        new_list.append((ov, target))
                else:
                    user32.DestroyWindow(ov)
            overlays[:] = new_list
        time.sleep(0.05)

    for ov, _ in overlays:
        user32.DestroyWindow(ov)
    for h in _overlay_hwnds:
        user32.DestroyWindow(h)
    _overlay_hwnds = []
    if atom:
        user32.UnregisterClassW(class_name, hinstance)
    return 0


def _create_per_window_overlay(hwnd_target, class_name, hinstance):
    """在目标窗口上方创建定位覆盖层（无 TOPMOST，Z 序紧随目标窗口）"""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd_target, ctypes.byref(rect))
    w = rect.right - rect.left
    h_ = rect.bottom - rect.top
    if w <= 0 or h_ <= 0:
        return None
    ex = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    hwnd = user32.CreateWindowExW(
        ex, class_name, "SG", WS_POPUP | WS_VISIBLE,
        rect.left, rect.top, w, h_, None, None, hinstance, None)
    if not hwnd:
        return None
    user32.SetLayeredWindowAttributes(hwnd, 0, 1, LWA_ALPHA)
    if not user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR):
        if not user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
            user32.DestroyWindow(hwnd)
            return None
    return hwnd

def _picker_service_main():
    """窗口选择器 — 灰色半透明全屏遮罩，单击选中窗口"""
    try:
        return _picker_impl()
    except Exception as e:
        import traceback
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        with open(os.path.join(BASE_DIR, '.overlay_err'), 'w', encoding='utf-8') as f:
            f.write(err)
        return 1

def _picker_impl():
    hinstance = kernel32.GetModuleHandleW(None)
    cls = "SGPickerGray"
    wc = wintypes.WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(wintypes.WNDCLASSEXW)
    wc.style = 0
    wc.lpfnWndProc = WNDPROC(_picker_wndproc)
    wc.hInstance = hinstance
    wc.hbrBackground = None
    wc.lpszClassName = cls
    wc.lpszMenuName = None
    atom = user32.RegisterClassExW(ctypes.byref(wc))
    if not atom:
        return 1

    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    # 分层窗口 + 灰色半透明 (alpha=200)
    ex = WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE
    hwnd = user32.CreateWindowExW(ex, cls, "SG",
        WS_POPUP | WS_VISIBLE, vx, vy, vw, vh, None, None, hinstance, None)
    if not hwnd:
        user32.UnregisterClassW(cls, hinstance)
        return 1
    user32.SetLayeredWindowAttributes(hwnd, 0, 200, 2)

    cross = user32.LoadCursorW(None, ctypes.c_void_p(32516))
    if cross:
        user32.SetCursor(cross)

    msg = wintypes.MSG(); running = [True]; btn_down = [False]
    while running[0]:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            if msg.message == WM_QUIT:
                running[0] = False; break
            if msg.message == WM_LBUTTONDOWN:
                btn_down[0] = True
            if msg.message == WM_LBUTTONUP and btn_down[0]:
                btn_down[0] = False
                pt = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                user32.ShowWindow(hwnd, 0)
                time.sleep(0.03)
                target = user32.WindowFromPoint(pt)
                if target:
                    root = user32.GetAncestor(target, 2)
                    actual = root if root else target
                    info = {"hwnd": actual, "class": _get_window_class(actual),
                            "title": _get_window_title(actual), "path": _get_window_path(actual)}
                    with open(PICKER_FILE, "w") as f:
                        json.dump(info, f)
                running[0] = False; break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)

    user32.DestroyWindow(hwnd)
    user32.UnregisterClassW(cls, hinstance)
    return 0

def _picker_wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_DESTROY:
        return 0
    if msg == WM_PAINT:
        ps = wintypes.PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        if hdc:
            rect = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            gdi32.SetBkMode(hdc, 1)
            gdi32.SetTextColor(hdc, 0x00cccccc)
            text = '点击任意窗口将其添加为保护目标'
            user32.DrawTextW(hdc, text, -1, ctypes.byref(rect),
                DT_CENTER | DT_VCENTER | DT_SINGLELINE)
            user32.EndPaint(hwnd, ctypes.byref(ps))
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)




# =========================================================================
# JS ↔ Python 桥接 API
# =========================================================================

class WebApi:
    def __init__(self, overlay_mgr, config):
        self.overlay = overlay_mgr
        self.config = config

    def check_password(self, password):
        stored = self.config.get('password_hash', '')
        if not stored:
            return {'ok': False, 'msg': '未设置密码'}
        if hash_password(password) == stored:
            return {'ok': True}
        return {'ok': False, 'msg': '密码错误'}

    def set_password(self, password):
        if len(password) < 4:
            return {'ok': False, 'msg': '密码至少 4 位'}
        self.config['password_hash'] = hash_password(password)
        if save_config(self.config):
            return {'ok': True}
        return {'ok': False, 'msg': '写入配置失败'}

    def change_password(self, old_pw, new_pw):
        if hash_password(old_pw) != self.config.get('password_hash', ''):
            return {'ok': False, 'msg': '原密码错误'}
        if len(new_pw) < 4:
            return {'ok': False, 'msg': '新密码至少 4 位'}
        self.config['password_hash'] = hash_password(new_pw)
        if save_config(self.config):
            return {'ok': True}
        return {'ok': False, 'msg': '写入配置失败'}

    def has_password(self):
        return 'password_hash' in self.config

    def start_protection(self):
        if self.overlay.is_active():
            return {'ok': True, 'msg': '已处于保护状态'}
        if self.config.get('target_mode') == 'window' and not self.config.get('target_windows'):
            return {'ok': False, 'msg': '请在设置中先选择目标窗口'}
        ok = self.overlay.create_overlay()
        if ok:
            return {'ok': True}
        return {'ok': False, 'msg': '创建覆盖层失败'}

    def stop_protection(self):
        if not self.overlay.is_active():
            return {'ok': True, 'msg': '保护未启动'}
        self.overlay.destroy_overlay()
        return {'ok': True}

    def get_status(self):
        return {
            'protected': self.overlay.is_active(),
            'has_password': self.has_password(),
            'require_password': self.config.get('require_password', True),
            'theme': self.config.get('theme_mode', 'dark'),
            'version': '3.0',
        }

    def get_require_password(self):
        return {'required': self.config.get('require_password', True)}

    def set_require_password(self, current_pw, new_value):
        new_value = bool(new_value)
        if new_value:
            # 关->开: 设置新密码
            if len(current_pw) < 4:
                return {'ok': False, 'msg': '密码至少 4 位'}
            self.config['password_hash'] = hash_password(current_pw)
        else:
            # 开->关: 验证旧密码
            stored = self.config.get('password_hash', '')
            if stored and hash_password(current_pw) != stored:
                return {'ok': False, 'msg': '密码错误'}
            self.config.pop('password_hash', None)
        self.config['require_password'] = new_value
        save_config(self.config)
        return {'ok': True}

    def get_preview(self):
        """截取屏幕并返回 base64 图片 (用于实时预览)"""
        try:
            sw = user32.GetSystemMetrics(0)  # SM_CXSCREEN
            sh = user32.GetSystemMetrics(1)  # SM_CYSCREEN
            # 缩小到 1/3 尺寸
            cw, ch = sw // 3, sh // 3
            hdc_src = user32.GetDC(None)
            hdc_dst = gdi32.CreateCompatibleDC(hdc_src)
            hbmp = gdi32.CreateCompatibleBitmap(hdc_src, cw, ch)
            gdi32.SelectObject(hdc_dst, hbmp)
            gdi32.StretchBlt(hdc_dst, 0, 0, cw, ch, hdc_src, 0, 0, sw, sh, 0x00CC0020)
            # 读像素数据
            bmp_info = ctypes.create_string_buffer(40)  # BITMAPINFOHEADER
            ctypes.memset(bmp_info, 0, 40)
            struct.pack_into('<IiiHHIIiiII', bmp_info, 0,
                40, cw, ch, 1, 32, 0, cw*ch*4, 0, 0, 0, 0)
            pixels = (ctypes.c_ubyte * (cw * ch * 4))()
            gdi32.GetDIBits(hdc_dst, hbmp, 0, ch, pixels, bmp_info, 0)
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(hdc_dst)
            user32.ReleaseDC(None, hdc_src)
            # BMP 文件头 + DIB 数据
            bmp_header = struct.pack('<HIHHI', 0x4D42, 14 + 40 + cw*ch*4, 0, 0, 14 + 40)
            raw = bmp_header + bytes(bmp_info) + bytes(pixels)
            return {'ok': True, 'img': 'data:image/bmp;base64,' + base64.b64encode(raw).decode()}
        except Exception as ex:
            return {'ok': False, 'msg': str(ex)}

    def get_theme(self):
        return {'mode': self.config.get('theme_mode', 'dark')}

    def set_theme(self, mode):
        if mode not in ('light', 'dark', 'system'):
            return {'ok': False}
        self.config['theme_mode'] = mode
        save_config(self.config)
        return {'ok': True}

    def get_system_theme(self):
        """读取 Windows 系统主题 (亮色/暗色)"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            val = winreg.QueryValueEx(key, "SystemUsesLightTheme")[0]
            winreg.CloseKey(key)
            return {'mode': 'light' if val else 'dark'}
        except Exception:
            return {'mode': 'dark'}

    def get_behavior(self):
        return {'close_with_gui': self.config.get('close_with_gui', False)}

    def set_behavior(self, key, val):
        if key != 'close_with_gui':
            return {'ok': False}
        self.config['close_with_gui'] = bool(val)
        save_config(self.config)
        return {'ok': True}

    # ── 目标窗口管理 ──

    def get_target_mode(self):
        return {'mode': self.config.get('target_mode', 'fullscreen')}

    def set_target_mode(self, mode):
        if mode not in ('fullscreen', 'window'):
            return {'ok': False}
        self.config['target_mode'] = mode
        if mode == 'window' and not self.config.get('target_windows'):
            # 自动添加当前前台窗口
            fg = user32.GetForegroundWindow()
            if fg:
                fg = user32.GetAncestor(fg, 2) or fg
                tg = {
                    'class': _get_window_class(fg),
                    'path': _get_window_path(fg),
                    'title': _get_window_title(fg),
                }
                if tg['class'] or tg['path']:
                    self.config['target_windows'] = [tg]
        save_config(self.config)
        return {'ok': True}

    def get_targets(self):
        return {'targets': self.config.get('target_windows', [])}

    def add_target(self):
        """启动窗口选择器，等待用户点击目标窗口"""
        import subprocess
        try:
            os.remove(PICKER_FILE)
        except FileNotFoundError:
            pass
        if getattr(sys, 'frozen', False):
            picker_args = [sys.executable, '--picker']
        else:
            picker_args = [sys.executable, os.path.abspath(__file__), '--picker']
        subprocess.Popen(
            picker_args,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        # 等待选择器结果（最多 15 秒）
        for _ in range(300):
            if os.path.exists(PICKER_FILE):
                try:
                    with open(PICKER_FILE, 'r') as f:
                        info = json.load(f)
                    os.remove(PICKER_FILE)
                    if info.get('hwnd'):
                        cls = info.get('class', '') or ''
                        path = info.get('path', '') or ''
                        if not cls and not path:
                            return {'ok': False, 'msg': '无法识别该窗口'}
                        tg = {'class': cls, 'path': path, 'title': info.get('title', '')}
                        targets = self.config.get('target_windows', [])
                        if not any(t.get('class') == tg['class'] and t.get('path') == tg['path'] for t in targets):
                            targets.append(tg)
                            self.config['target_windows'] = targets
                            save_config(self.config)
                        return {'ok': True, 'target': tg}
                    return {'ok': False, 'msg': '选择已取消'}
                except (json.JSONDecodeError, IOError):
                    pass
            time.sleep(0.05)
        return {'ok': False, 'msg': '选择超时'}

    def remove_target(self, index):
        targets = self.config.get('target_windows', [])
        if 0 <= index < len(targets):
            targets.pop(index)
            self.config['target_windows'] = targets
            save_config(self.config)
            return {'ok': True}
        return {'ok': False}

    def _exit(self):
        import webview
        if webview.windows:
            webview.windows[0].destroy()


# =========================================================================
# 内嵌 HTML
# =========================================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<title>ScreenGuard</title>
<style>
:root{--bg-a:#1a1a2e;--bg-b:#16213e;--bg-c:#0f3460;--bg-d:#1a1a2e;--bd:#1a4a7a;--tx-a:#e0e0e0;--tx-b:#888;--tx-c:#fff;--ac:#e94560;--ac-h:#d63851;--ok:#2ecc71;--ng:#e74c3c}
[data-theme="light"]{--bg-a:#f5f5f7;--bg-b:#fff;--bg-c:#e8e8ed;--bg-d:#fff;--bd:#d1d1d6;--tx-a:#1d1d1f;--tx-b:#888;--tx-c:#000;--ac:#007aff;--ac-h:#0066d6;--ok:#34c759;--ng:#ff3b30}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;background:var(--bg-a);color:var(--tx-a)}
.fullpage{display:none;align-items:center;justify-content:center;height:100vh;position:absolute;inset:0;z-index:10;background:var(--bg-a)}
.fullpage.active{display:flex}
.fp-card{background:var(--bg-b);border-radius:12px;padding:32px 28px;box-shadow:0 4px 20px rgba(0,0,0,.15);text-align:center;width:340px}
.fp-card h1{font-size:22px;font-weight:300;color:var(--tx-c);margin-bottom:4px}
.fp-card .sub{font-size:12px;color:var(--tx-b);margin-bottom:20px}
.app-layout{display:none;height:100vh;width:100vw}
.app-layout.active{display:flex}
.app-layout .sidebar{width:130px;flex-shrink:0;height:100vh;display:flex;flex-direction:column;padding:10px 0;border-right:1px solid var(--bd);background:var(--bg-c)}
.sidebar-logo{margin-bottom:16px;display:flex;align-items:center;justify-content:center;gap:6px;color:var(--tx-c)}
.sidebar-logo svg{width:20px;height:20px}
.sidebar-logo span{font-size:13px;font-weight:600}
.sidebar-nav{display:flex;flex-direction:column;gap:2px;flex:1;padding:0 6px}
.nav-item{width:100%;height:36px;border-radius:6px;display:flex;align-items:center;gap:8px;cursor:pointer;transition:all .15s;border:none;background:transparent;color:var(--tx-b);font-size:12px;padding:0 10px;font-family:inherit}
.nav-item:hover{background:var(--bd);color:var(--tx-a)}
.nav-item.active{background:var(--ac);color:#fff}
.nav-item svg{width:16px;height:16px;flex-shrink:0}
.nav-item .nl{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.app-layout .content{flex:1;min-height:0;display:flex;flex-direction:column;background:var(--bg-b);overflow-y:auto}
.ch{flex-shrink:0;padding:14px 22px 6px;border-bottom:1px solid var(--bd)}
.ch h2{font-size:16px;font-weight:400;color:var(--tx-c)}
.ch p{font-size:11px;color:var(--tx-b);margin-top:1px}
.cb{padding:16px 20px 60px}
.card{background:var(--bg-d);border-radius:10px;padding:16px;margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,.12)}
.ct{font-size:12px;font-weight:500;color:var(--tx-b);margin-bottom:10px;letter-spacing:.3px;text-transform:uppercase}
.sr{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.sd{width:10px;height:10px;border-radius:50%;display:inline-block}
.sd.on{background:var(--ok);box-shadow:0 0 8px var(--ok)}
.sd.off{background:#555}
.sl{font-size:13px;color:var(--tx-a)}
.btn{padding:9px 18px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s;letter-spacing:.3px;font-family:inherit}
.btn-pri{background:var(--ac);color:#fff;width:100%}
.btn-pri:hover{background:var(--ac-h)}
.btn-ok{background:var(--ok);color:#fff;width:100%}
.btn-ok:hover{background:#27ae60}
.btn-ng{background:var(--ng);color:#fff;width:100%}
.btn-ng:hover{background:#c0392b}
.btn-sm{width:auto;padding:7px 14px;display:inline-flex;align-items:center;gap:6px}
.ig{margin-bottom:12px}
.ig label{display:block;font-size:11px;color:var(--tx-b);margin-bottom:3px}
.ig input{width:100%;padding:8px 10px;background:var(--bg-c);border:1px solid var(--bd);border-radius:8px;color:var(--tx-a);font-size:13px;outline:none}
.ig input:focus{border-color:var(--ac)}
.msg{font-size:11px;margin-top:3px;min-height:16px}
.msg.err{color:var(--ng)}
.msg.ok{color:var(--ok)}
.toggle-btn{width:40px;height:22px;border-radius:11px;border:none;cursor:pointer;position:relative;background:#555;padding:0;flex-shrink:0;transition:.25s}
.toggle-btn::after{content:'';position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:#fff;transition:.25s;box-shadow:0 1px 3px rgba(0,0,0,.2)}
.toggle-btn.on{background:var(--ac)}
.toggle-btn.on::after{transform:translateX(18px)}
.theme-row{display:flex;align-items:center;gap:8px;padding:4px 0}
.theme-row-label{font-size:13px;color:var(--tx-a);flex:1}
.mode-btn{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;border-radius:6px;border:1px solid var(--bd);background:transparent;color:var(--tx-b);font-size:12px;cursor:pointer;transition:all .15s}
.mode-btn:hover{border-color:var(--ac);color:var(--tx-a)}
.mode-btn.active{background:var(--ac);color:#fff;border-color:var(--ac)}
.ai{font-size:12px;color:var(--tx-b);line-height:1.8}
.ai strong{color:var(--tx-a)}
.content{scrollbar-width:thin;scrollbar-color:var(--bd) transparent}
::-webkit-scrollbar{width:6px}
.content::-webkit-scrollbar-track{background:transparent}
.content::-webkit-scrollbar-thumb{background:var(--bd);border-radius:3px}
.content::-webkit-scrollbar-thumb:hover{background:var(--ac)}
</style>
</head>
<body>

<div id="page-login" class="fullpage">
  <div class="fp-card">
    <h1>ScreenGuard</h1>
    <p class="sub">全屏远程监视屏蔽</p>
    <div class="ig">
      <label>密码</label>
      <input type="password" id="login-pw" placeholder="请输入密码" onkeydown="if(event.key==='Enter')doLogin()">
    </div>
    <button class="btn btn-pri" onclick="doLogin()">登 录</button>
    <div id="login-err" class="msg err"></div>
  </div>
</div>

<div id="page-setup" class="fullpage">
  <div class="fp-card">
    <h1>ScreenGuard</h1>
    <p class="sub">首次使用，请设置密码</p>
    <div class="ig">
      <label>设置密码</label>
      <input type="password" id="setup-pw" placeholder="至少 4 位" onkeydown="if(event.key==='Enter')doSetup()">
    </div>
    <div class="ig">
      <label>确认密码</label>
      <input type="password" id="setup-pw2" placeholder="再次输入" onkeydown="if(event.key==='Enter')doSetup()">
    </div>
    <button class="btn btn-ok" onclick="doSetup()">确认设置</button>
    <div id="setup-err" class="msg err"></div>
    <div id="setup-ok" class="msg ok"></div>
  </div>
</div>

<div id="app-layout" class="app-layout">
  <aside class="sidebar">
    <div class="sidebar-logo">
      <svg viewBox="0 0 24 24" fill="none" stroke="var(--ac)" stroke-width="2">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      </svg>
      <span>Guard</span>
    </div>
    <nav class="sidebar-nav">
      <button class="nav-item active" data-view="protection" onclick="switchView('protection')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        <span class="nl">保护</span>
      </button>
      <button class="nav-item" data-view="settings" onclick="switchView('settings')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
        <span class="nl">设置</span>
      </button>
      <button class="nav-item" data-view="about" onclick="switchView('settings')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="16" x2="12" y2="12"/>
          <line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>
        <span class="nl">关于</span>
      </button>
    </nav>
    <div class="sidebar-ft">v3.0</div>
  </aside>

  <div class="content">
    <!-- 保护 -->
    <div id="view-protection" class="view-page">
      <div class="ch">
        <h2>屏幕保护</h2>
        <p id="mode-desc">启动后远程监视只能看到黑屏</p>
      </div>
      <div class="cb">
        <div class="card">
          <div class="ct">保护状态</div>
          <div class="sr">
            <span id="sd" class="sd off"></span>
            <span id="st" class="sl">未启动</span>
          </div>
          <button id="btn-tg" class="btn btn-ok" onclick="doToggle()">启动保护</button>
          <div id="main-msg" class="msg err"></div>
        </div>
        <div class="card">
          <div class="ct">保护模式</div>
          <div class="theme-row" style="flex-wrap:wrap">
            <button class="mode-btn" data-mode="fullscreen" onclick="doSetTargetMode('fullscreen')">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
              </svg>
              全屏
            </button>
            <button class="mode-btn" data-mode="window" onclick="doSetTargetMode('window')">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="3" width="20" height="18" rx="2" ry="2"/>
                <line x1="2" y1="9" x2="22" y2="9"/>
              </svg>
              窗口
            </button>
          </div>
          <div id="target-list" style="margin-top:8px"></div>
          <div id="picker-msg" class="msg" style="margin-top:4px"></div>
        </div>
        <p id="mode-info" style="font-size:12px;color:var(--tx-b);line-height:1.7;padding:0 18px 18px"></p>
        <div class="card">
          <div class="ct">关闭行为</div>
          <div class="theme-row">
            <span class="theme-row-label">关闭程序时同时关闭遮罩</span>
            <button id="btn-close-behavior" class="toggle-btn" onclick="doToggleCloseBehavior()"></button>
          </div>
        </div>
        <div class="card" style="text-align:center">
          <div class="ct">远程监视画面模拟</div>
          <div id="preview-box" style="background:#000;border-radius:6px;overflow:hidden;margin:0 auto;
            max-width:100%;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center">
            <span style="color:#555;font-size:12px">正在加载预览...</span>
          </div>
          <div style="margin-top:6px;font-size:10px;color:var(--tx-b)">每 2 秒刷新 · 仅供参考</div>
        </div>
      </div>
    </div>

    <!-- 设置 -->
    <div id="view-settings" class="view-page" style="display:none">
      <div class="ch">
        <h2>设置</h2>
        <p>主题与密码管理</p>
      </div>
      <div class="cb">
        <div class="card">
          <div class="ct">主题</div>
          <div class="theme-row" style="flex-wrap:wrap">
            <button class="mode-btn" data-mode="light" onclick="doSetTheme('light')">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/>
                <line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/>
                <line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
              </svg>
              亮色
            </button>
            <button class="mode-btn" data-mode="dark" onclick="doSetTheme('dark')">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
              </svg>
              暗色
            </button>
            <button class="mode-btn" data-mode="system" onclick="doSetTheme('system')">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                <line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
              </svg>
              系统
            </button>
          </div>
        </div>
        <div class="card">
          <div class="ct">登录密码</div>
          <div class="theme-row">
            <span class="theme-row-label">进入程序时需要输入密码</span>
            <button id="btn-req-pw" class="toggle-btn" onclick="doToggleReqPw()"></button>
          </div>
          <div id="reqpw-err" class="msg err"></div>
          <div id="reqpw-pw-area" style="display:none;margin-top:8px">
            <div class="ig"><label>输入当前密码以修改此设置</label>
              <input type="password" id="reqpw-cur" placeholder="当前密码" onkeydown="if(event.key==='Enter')confirmReqPw()"></div>
            <button class="btn btn-pri btn-sm" onclick="confirmReqPw()" style="width:auto">确认</button>
          </div>
        </div>
        <div class="card" id="card-changepw">
          <div class="ct">修改密码</div>
          <div class="ig">
            <label>原密码</label>
            <input type="password" id="cpw-old" placeholder="原密码" onkeydown="if(event.key==='Enter')doChangePw()">
          </div>
          <div class="ig">
            <label>新密码</label>
            <input type="password" id="cpw-new" placeholder="至少 4 位" onkeydown="if(event.key==='Enter')doChangePw()">
          </div>
          <div class="ig">
            <label>确认新密码</label>
            <input type="password" id="cpw-new2" placeholder="再次输入" onkeydown="if(event.key==='Enter')doChangePw()">
          </div>
          <button class="btn btn-pri btn-sm" onclick="doChangePw()">确认修改</button>
          <div id="cpw-err" class="msg err"></div>
          <div id="cpw-ok" class="msg ok"></div>
        </div>
      </div>
    </div>

    <!-- 设置结尾: 关于 -->
        <div class="card">
          <div class="ai" style="text-align:center;padding:8px 0">
            <strong>ScreenGuard</strong> v3.0<br>
            基于 SetWindowDisplayAffinity API<br><br>
            Windows 8+ · Python 3 + pywebview<br>
            仅供合法隐私保护用途。
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<div id="modal-overlay" style="display:none;position:fixed;inset:0;z-index:999;
  background:rgba(0,0,0,.55);align-items:center;justify-content:center">
  <div style="background:var(--bg-b);border-radius:10px;padding:24px 28px;width:320px;
    box-shadow:0 8px 30px rgba(0,0,0,.4);text-align:center">
    <p id="modal-msg" style="color:var(--tx-a);font-size:14px;line-height:1.6;margin-bottom:18px"></p>
    <div style="display:flex;gap:10px;justify-content:center">
      <button id="modal-yes" class="btn btn-pri btn-sm" style="width:auto;min-width:70px">确定</button>
      <button id="modal-no" class="btn btn-sm" style="width:auto;min-width:70px;background:var(--bg-c);color:var(--tx-a)">取消</button>
    </div>
  </div>
</div>
<script>
var HAS_PASSWORD = __HAS_PASSWORD__;
var REQ_PASSWORD = __REQUIRE_PASSWORD__;
var protected = false;
var themeMode = 'dark';
var _initDone = false;

function _goHome(fromLogin){
  if(!fromLogin && HAS_PASSWORD && REQ_PASSWORD){showPage('page-login'); return;}
  if(!HAS_PASSWORD && REQ_PASSWORD){showPage('page-setup'); return;}
  hide('page-login');hide('page-setup');show('app-layout');
  switchView('protection');
  window.pywebview.api.get_status().then(function(s){
    if(s.protected){protected=true;updateStatus()}
    applyReqPw(REQ_PASSWORD);
  });
  window.pywebview.api.get_target_mode().then(function(r){
    _targetMode=r.mode;updateModeInfo();doSetTargetMode(r.mode);
  });
}

function _tryInit(){
  if(_initDone)return;
  try {
    window.pywebview.api.get_theme().then(function(t){
      applyTheme(t.mode); _initDone = true;
      window.pywebview.api.get_behavior().then(function(b){applyCloseBehavior(b.close_with_gui)});
      _goHome();
    }).catch(function(){setTimeout(_tryInit,50)});
  } catch(e){setTimeout(_tryInit,50)}
}
_tryInit();
setTimeout(function(){if(!_initDone)_goHome()},3000);

function show(id){document.getElementById(id).classList.add('active')}
function hide(id){document.getElementById(id).classList.remove('active')}

function showPage(id){document.querySelectorAll('.fullpage').forEach(function(p){p.classList.remove('active')});show(id)}

// ── 远程监视画面模拟 ──
var _previewPoll = null;
var _previewBox = null;
function startPreview(){
  var box=document.getElementById('preview-box');
  if(!box)return;
  _previewBox=box;
  if(_previewPoll)clearInterval(_previewPoll);
  _previewPoll=setInterval(updatePreview,2000);
  updatePreview();
}
function stopPreview(){
  if(_previewPoll){clearInterval(_previewPoll);_previewPoll=null}
}
function updatePreview(){
  window.pywebview.api.get_preview().then(function(r){
    if(r.ok && _previewBox){
      _previewBox.innerHTML='<img src="'+r.img+'" style="width:100%;height:100%;display:block">';
    }else if(_previewBox){
      _previewBox.innerHTML='<span style="color:#888;font-size:11px">预览不可用</span>';
    }
  });
}

function switchView(name){
  document.querySelectorAll('.nav-item').forEach(function(b){
    b.classList.toggle('active',b.dataset.view===name)});
  document.querySelectorAll('.view-page').forEach(function(p){p.style.display='none'});
  var el=document.getElementById('view-'+name);
  if(el)el.style.display='block';
  if(name==='protection'){
    if(_targetMode==='window')loadTargets();
    startPreview();
  }else{stopPreview()}
}

// ── 主题 (亮色/暗色/跟随系统) ──
var _sysPoll = null;

function _applyCSS(mode){
  document.documentElement.setAttribute('data-theme',mode);
}

function applyTheme(mode){
  themeMode = mode;
  document.querySelectorAll('.mode-btn').forEach(function(b){
    b.classList.toggle('active',b.dataset.mode===mode)});
  if(mode === 'system'){
    _resolveSystem();
    if(_sysPoll)clearInterval(_sysPoll);
    _sysPoll = setInterval(_resolveSystem, 3000);
  } else {
    if(_sysPoll){clearInterval(_sysPoll);_sysPoll=null}
    _applyCSS(mode);
  }
}

function _resolveSystem(){
  try {
    window.pywebview.api.get_system_theme().then(function(r){
      _applyCSS(r.mode);
    }).catch(function(){});
  } catch(e){}
}

function doSetTheme(mode){
  applyTheme(mode);
  window.pywebview.api.set_theme(mode);
}

function doLogin(){
  var pw=document.getElementById('login-pw').value;
  if(!pw){document.getElementById('login-err').textContent='请输入密码';return}
  document.getElementById('login-err').textContent='';
  window.pywebview.api.check_password(pw).then(function(r){
    if(r.ok){_goHome(true)}
    else{
      document.getElementById('login-err').textContent=r.msg;
    }
  });
}

function doSetup(){
  var pw=document.getElementById('setup-pw').value;
  var pw2=document.getElementById('setup-pw2').value;
  document.getElementById('setup-err').textContent='';
  document.getElementById('setup-ok').textContent='';
  if(pw.length<4){document.getElementById('setup-err').textContent='密码至少 4 位';return}
  if(pw!==pw2){document.getElementById('setup-err').textContent='两次密码不一致';return}
  window.pywebview.api.set_password(pw).then(function(r){
    if(r.ok){
      document.getElementById('setup-ok').textContent='密码设置成功!';REQ_PASSWORD=true;
      HAS_PASSWORD=true;
      setTimeout(function(){hide('page-setup');_goHome()},800);
    }else{document.getElementById('setup-err').textContent=r.msg}
  });
}

function _modeLabel(){return _targetMode==='window'?'窗口':'全屏'}

function updateStatus(){
  var label=_modeLabel();
  if(protected){
    document.getElementById('sd').className='sd on';
    document.getElementById('st').textContent='保护中 — 远程监视看到黑屏';
    document.getElementById('btn-tg').className='btn btn-ng';
    document.getElementById('btn-tg').textContent='停止'+label+'保护';
  }else{
    document.getElementById('sd').className='sd off';
    document.getElementById('st').textContent='未启动';
    document.getElementById('btn-tg').className='btn btn-ok';
    document.getElementById('btn-tg').textContent='启动'+label+'保护';
  }
  document.getElementById('main-msg').textContent='';
}

function doToggle(){
  if(protected){
    protected=false;updateStatus();
    window.pywebview.api.stop_protection().then(function(r){
      if(!r.ok){protected=true;updateStatus();
        document.getElementById('main-msg').textContent=r.msg||'停止失败'}
    });
  }else{
    protected=true;updateStatus();
    window.pywebview.api.start_protection().then(function(r){
      if(!r.ok){protected=false;updateStatus();
        document.getElementById('main-msg').textContent=r.msg||'启动失败'}
    });
  }
}

function doChangePw(){
  var old=document.getElementById('cpw-old').value;
  var pw=document.getElementById('cpw-new').value;
  var pw2=document.getElementById('cpw-new2').value;
  document.getElementById('cpw-err').textContent='';
  document.getElementById('cpw-ok').textContent='';
  if(!old){document.getElementById('cpw-err').textContent='请输入原密码';return}
  if(pw.length<4){document.getElementById('cpw-err').textContent='新密码至少 4 位';return}
  if(pw!==pw2){document.getElementById('cpw-err').textContent='两次密码不一致';return}
  window.pywebview.api.change_password(old,pw).then(function(r){
    if(r.ok){document.getElementById('cpw-ok').textContent='密码修改成功!'}
    else{document.getElementById('cpw-err').textContent=r.msg}
  });
}

// ── 关闭行为 ──
function applyCloseBehavior(val){
  var btn=document.getElementById('btn-close-behavior');
  if(btn)btn.classList.toggle('on',val);
}
function doToggleCloseBehavior(){
  var now=document.getElementById('btn-close-behavior').classList.contains('on');
  window.pywebview.api.set_behavior('close_with_gui',!now).then(function(r){
    if(r.ok){applyCloseBehavior(!now)}
  });
}

// ── 登录密码开关 ──
function applyReqPw(val){
  var btn=document.getElementById('btn-req-pw');
  if(btn)btn.classList.toggle('on',val);
  document.getElementById('reqpw-pw-area').style.display='none';
  document.getElementById('reqpw-err').textContent='';
  var cp=document.getElementById('card-changepw');
  if(cp)cp.style.display=val?'block':'none';
}
function doToggleReqPw(){
  var now=document.getElementById('btn-req-pw').classList.contains('on');
  // 无论开/关都弹出密码输入
  document.getElementById('reqpw-pw-area').style.display='block';
  document.getElementById('reqpw-cur').value='';
  document.getElementById('reqpw-cur').placeholder=now?'输入当前密码以关闭登录密码':'设置新密码(至少4位)';
  document.getElementById('reqpw-cur').focus();
}
function confirmReqPw(){
  var pw=document.getElementById('reqpw-cur').value;
  var now=document.getElementById('btn-req-pw').classList.contains('on');
  if(now){
    // 开->关: 验证旧密码
    window.pywebview.api.set_require_password(pw,false).then(function(r){
      if(r.ok){applyReqPw(false);REQ_PASSWORD=false;}
      else{document.getElementById('reqpw-err').textContent=r.msg}
    });
  }else{
    // 关->开: 设置新密码
    window.pywebview.api.set_require_password(pw,true).then(function(r){
      if(r.ok){applyReqPw(true);REQ_PASSWORD=true;HAS_PASSWORD=true;}
      else{document.getElementById('reqpw-err').textContent=r.msg}
    });
  }
}

// ── 目标窗口管理 ──
var _targetMode = 'fullscreen';

function _modal(msg, cb){
  document.getElementById('modal-msg').textContent=msg;
  document.getElementById('modal-overlay').style.display='flex';
  document.getElementById('modal-yes').onclick=function(){
    document.getElementById('modal-overlay').style.display='none';cb(true)};
  document.getElementById('modal-no').onclick=function(){
    document.getElementById('modal-overlay').style.display='none';cb(false)};
}
function doSetTargetMode(mode){
  if(protected && mode!==_targetMode){
    _modal('切换保护模式会短暂关闭当前保护，是否继续？',function(ok){
      if(!ok)return;
      window.pywebview.api.stop_protection().then(function(r){
        if(r.ok){protected=false;_applyTargetMode(mode);_startAfterSwitch();}
      });
    });
  }else{_applyTargetMode(mode)}
}
function _applyTargetMode(mode){
  _targetMode=mode;
  document.querySelectorAll('.mode-btn[data-mode="fullscreen"],.mode-btn[data-mode="window"]').forEach(function(b){
    b.classList.toggle('active',b.dataset.mode===mode)});
  var tl=document.getElementById('target-list');
  var pm=document.getElementById('picker-msg');
  if(mode==='window'){tl.style.display='block';loadTargets()}
  else{tl.style.display='none';if(pm)pm.textContent=''}
  window.pywebview.api.set_target_mode(mode);
  updateModeInfo();updateStatus();
}
function _startAfterSwitch(){
  window.pywebview.api.start_protection().then(function(r){
    if(r.ok){protected=true;updateStatus()}
    else{document.getElementById('main-msg').textContent=r.msg}
  });
}

function loadTargets(){
  window.pywebview.api.get_targets().then(function(r){
    renderTargets(r.targets);
  });
}

function renderTargets(targets){
  var el=document.getElementById('target-list');
  if(!el)return;
  var html='';
  if(targets.length===0){
    html='<div style="font-size:11px;color:var(--tx-b);margin-bottom:6px">尚未添加目标窗口</div>';
  }else{
    for(var i=0;i<targets.length;i++){
      var t=targets[i];
      var proc=t.path?t.path.split(/[/\\\\]/).pop():'';
      var label=(t.title||'')+(proc?' <span style="color:var(--tx-b);font-size:11px">'+proc+'</span>':'');
      html+='<div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid var(--bd)">'+
        '<span style="color:var(--tx-a);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">'+label+'</span>'+
        '<button onclick="removeTarget('+i+')" style="background:none;border:none;color:var(--ng);cursor:pointer;font-size:14px;padding:0 4px;flex-shrink:0">&times;</button>'+
        '</div>';
    }
  }
  html+='<button class="btn btn-sm btn-pri" onclick="startPicker()" style="margin-top:6px;width:100%">+ 选择窗口</button>';
  el.innerHTML=html;
}

function escapeHtml(s){
  if(!s)return'';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function startPicker(){
  var pm=document.getElementById('picker-msg');
  if(pm)pm.textContent='点击任意窗口来选择...';
  window.pywebview.api.add_target().then(function(r){
    if(pm){
      if(r.ok){
        pm.className='msg ok';
        pm.textContent='已选择: '+(r.target.title||r.target.class||'');
        loadTargets();
      }else{
        pm.className='msg err';
        pm.textContent=r.msg||'选择失败';
      }
    }
  });
}

function removeTarget(idx){
  window.pywebview.api.remove_target(idx).then(function(r){
    if(r.ok)loadTargets();
  });
}

function updateModeInfo(){
  var el=document.getElementById('mode-info');
  var desc=document.getElementById('mode-desc');
  if(!el)return;
  if(_targetMode==='window'){
    el.textContent='仅保护指定窗口 — 其他区域正常显示';
    if(desc)desc.textContent='启动后指定窗口在远程监视中变为黑屏';
  }else{
    el.textContent='全屏覆盖 — 整个屏幕在远程监视中变为黑屏';
    if(desc)desc.textContent='启动后远程监视只能看到黑屏';
  }
}
</script>
</body>
</html>"""


def get_html(has_password, require_password=True):
    html = HTML_TEMPLATE
    html = html.replace('__HAS_PASSWORD__', 'true' if has_password else 'false')
    html = html.replace('__REQUIRE_PASSWORD__', 'true' if require_password else 'false')
    return html


# =========================================================================
# pywebview 窗口
# =========================================================================

def start_gui(overlay_mgr, config):
    api = WebApi(overlay_mgr, config)
    import webview

    html = get_html('password_hash' in config, config.get('require_password', True))
    webview.create_window(
        'ScreenGuard -- 全屏远程监视屏蔽',
        html=html,
        js_api=api,
        width=800,
        height=600,
        min_size=(640, 480),
        resizable=True,
        frameless=False,
    )
    webview.start(gui=None, debug=False)

    return api.overlay.is_active()


# =========================================================================
# 主入口
# =========================================================================

def main():
    print("=" * 48)
    print("  ScreenGuard v3.0 -- 全屏远程监视屏蔽")
    print("=" * 48)
    print()

    try:
        ver = sys.getwindowsversion()
        if ver.major < 6 or (ver.major == 6 and ver.minor < 2):
            print("[-] 需要 Windows 8 或更高版本")
            input("按 Enter 退出...")
            sys.exit(1)
    except AttributeError:
        print("[-] 非 Windows 系统")
        sys.exit(1)

    config = load_config()
    overlay = OverlayManager()

    try:
        protected = start_gui(overlay, config)
    except ImportError:
        print("[-] 需要 pywebview, 请运行: pip install pywebview")
        sys.exit(1)

    close_with_gui = config.get('close_with_gui', False)

    if protected and close_with_gui:
        print("[*] 正在关闭遮罩 (随程序关闭)...")
        overlay.destroy_overlay()
        protected = False

    if protected:
        print("[*] GUI 已关闭, 保护仍在后台运行")
        print("[*] 在设置中可改为\"随程序关闭\"")
        print("[*] 关闭此窗口或 Ctrl+C 完全退出")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] 收到退出信号")
    else:
        print("[*] 保护未激活, 直接退出")

    print("[*] ScreenGuard GUI 已退出")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == '--overlay':
            # sys.argv[2] 是 GUI PID（可选），用于区分自身进程和其他进程
            sys.exit(_overlay_service_main())
        elif sys.argv[1] == '--picker':
            sys.exit(_picker_service_main())
        elif sys.argv[1] == '--test-window':
            sys.exit(_test_window_main())
        else:
            main()
    else:
        main()
