"""
Walt Desktop Launcher
=====================
This script runs AS SYSTEM (via Windows Task Scheduler) and uses WTSQueryUserToken +
CreateProcessAsUserW to launch a process in the interactive desktop session of the
logged-in user. This is required for GUI apps (pyautogui, tkinter, etc.) that must
appear on the user's screen.

Usage:
    python walt_launcher.py <command and args>

Example:
    python walt_launcher.py pythonw "D:/Trabalho/auth/alwayson.py"

Writes result to C:/Users/walt/walt_launcher_result.txt
"""
import ctypes
import ctypes.wintypes as W
import sys

kernel32 = ctypes.windll.kernel32
wtsapi32 = ctypes.windll.wtsapi32
advapi32 = ctypes.windll.advapi32
userenv  = ctypes.windll.userenv


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb",            W.DWORD),
        ("lpReserved",    W.LPWSTR),
        ("lpDesktop",     W.LPWSTR),
        ("lpTitle",       W.LPWSTR),
        ("dwX",           W.DWORD),
        ("dwY",           W.DWORD),
        ("dwXSize",       W.DWORD),
        ("dwYSize",       W.DWORD),
        ("dwXCountChars", W.DWORD),
        ("dwYCountChars", W.DWORD),
        ("dwFillAttribute", W.DWORD),
        ("dwFlags",       W.DWORD),
        ("wShowWindow",   W.WORD),
        ("cbReserved2",   W.WORD),
        ("lpReserved2",   ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput",     W.HANDLE),
        ("hStdOutput",    W.HANDLE),
        ("hStdError",     W.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess",    W.HANDLE),
        ("hThread",     W.HANDLE),
        ("dwProcessId", W.DWORD),
        ("dwThreadId",  W.DWORD),
    ]


LOG_PATH = "C:/Users/walt/walt_launcher_result.txt"
CREATE_UNICODE_ENVIRONMENT = 0x00000400
MAXIMUM_ALLOWED = 0x02000000


def launch_in_desktop_session(cmd_line: str) -> tuple[bool, str]:
    """Launch cmd_line in the active interactive desktop session. Returns (ok, message)."""
    session_id = kernel32.WTSGetActiveConsoleSessionId()

    hToken = W.HANDLE()
    if not wtsapi32.WTSQueryUserToken(session_id, ctypes.byref(hToken)):
        return False, f"WTSQueryUserToken failed (error {kernel32.GetLastError()})"

    hDup = W.HANDLE()
    ok = advapi32.DuplicateTokenEx(hToken, MAXIMUM_ALLOWED, None, 2, 1, ctypes.byref(hDup))
    kernel32.CloseHandle(hToken)
    if not ok:
        return False, f"DuplicateTokenEx failed (error {kernel32.GetLastError()})"

    lpEnv = ctypes.c_void_p()
    userenv.CreateEnvironmentBlock(ctypes.byref(lpEnv), hDup, False)

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(STARTUPINFOW)
    si.lpDesktop = "winsta0\\default"
    pi = PROCESS_INFORMATION()

    buf = ctypes.create_unicode_buffer(cmd_line)
    ok = advapi32.CreateProcessAsUserW(
        hDup, None, buf, None, None, False,
        CREATE_UNICODE_ENVIRONMENT,
        lpEnv, None,
        ctypes.byref(si), ctypes.byref(pi),
    )

    if lpEnv.value:
        userenv.DestroyEnvironmentBlock(lpEnv)
    kernel32.CloseHandle(hDup)

    if ok:
        pid = pi.dwProcessId
        kernel32.CloseHandle(pi.hProcess)
        kernel32.CloseHandle(pi.hThread)
        return True, f"PID={pid}"
    return False, f"CreateProcessAsUserW failed (error {kernel32.GetLastError()})"


if __name__ == "__main__":
    cmd_line = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if not cmd_line:
        with open(LOG_PATH, "w") as f:
            f.write("ERROR: no command provided\n")
        sys.exit(1)

    ok, msg = launch_in_desktop_session(cmd_line)
    with open(LOG_PATH, "w") as f:
        f.write(("SUCCESS " if ok else "FAIL ") + msg + "\n")
    sys.exit(0 if ok else 1)
