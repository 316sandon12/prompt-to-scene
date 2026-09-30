"""Provider credentials stay in the OS credential store, never in project metadata."""

import ctypes
import os
import subprocess
import sys


def _windows():
    from ctypes import wintypes as w

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", w.DWORD),
            ("Type", w.DWORD),
            ("TargetName", w.LPWSTR),
            ("Comment", w.LPWSTR),
            ("LastWritten", w.FILETIME),
            ("CredentialBlobSize", w.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", w.DWORD),
            ("AttributeCount", w.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", w.LPWSTR),
            ("UserName", w.LPWSTR),
        ]

    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredReadW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        w.DWORD,
        ctypes.POINTER(ctypes.POINTER(Credential)),
    ]
    api.CredWriteW.argtypes = [ctypes.POINTER(Credential), w.DWORD]
    api.CredFree.argtypes = [ctypes.c_void_p]
    return api, Credential


def get(provider):
    value = os.environ.get("MESHY_API_KEY" if provider == "meshy" else "PTS_LOCAL_API_KEY")
    if value:
        return value
    name = "PromptToScene." + provider
    if sys.platform == "darwin":
        result = subprocess.run(
            ["security", "find-generic-password", "-s", name, "-a", "prompt-to-scene", "-w"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    if sys.platform == "win32":
        api, kind = _windows()
        pointer = ctypes.POINTER(kind)()
        if not api.CredReadW(name, 1, 0, ctypes.byref(pointer)):
            return None
        try:
            return ctypes.string_at(
                pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize
            ).decode("utf-16-le")
        finally:
            api.CredFree(pointer)
    return None


def put(provider, value):
    if (
        provider not in {"meshy", "local"}
        or not isinstance(value, str)
        or not 1 <= len(value) <= 4096
    ):
        raise ValueError("Invalid provider credential")
    name = "PromptToScene." + provider
    if sys.platform == "darwin":
        result = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-s",
                name,
                "-a",
                "prompt-to-scene",
                "-w",
                value,
            ],
            capture_output=True,
        )
        if result.returncode:
            raise RuntimeError("Could not save the credential in macOS Keychain")
    elif sys.platform == "win32":
        api, kind = _windows()
        data = value.encode("utf-16-le")
        blob = (ctypes.c_byte * len(data)).from_buffer_copy(data)
        record = kind(
            Type=1,
            TargetName=name,
            CredentialBlobSize=len(data),
            CredentialBlob=blob,
            Persist=2,
            UserName="prompt-to-scene",
        )
        if not api.CredWriteW(ctypes.byref(record), 0):
            raise RuntimeError("Could not save the credential in Windows Credential Manager")
    else:
        raise ValueError("Set MESHY_API_KEY or PTS_LOCAL_API_KEY on this platform")
