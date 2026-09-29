"""User-bound Windows DPAPI storage; never persist a password or plaintext token."""
import base64
import ctypes
from ctypes import wintypes
import os


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(value: bytes, protect: bool) -> bytes:
    if os.name != 'nt':
        raise RuntimeError('当前平台未启用安全凭据存储；请取消保持登录')
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if protect:
        function = crypt32.CryptProtectData
        function.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        okay = function(ctypes.byref(source), 'Lens Atlas login', None, None, None, 1, ctypes.byref(result))
    else:
        function = crypt32.CryptUnprotectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        okay = function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
    if not okay:
        raise OSError(ctypes.get_last_error(), 'Windows 安全凭据存储不可用')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel32.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


class CredentialStore:
    def __init__(self, db):
        self.db = db

    def save(self, cid, token):
        self.db.set_setting('credential:' + cid, base64.b64encode(_crypt(token.encode(), True)).decode())

    def load(self, cid):
        value = self.db.setting('credential:' + cid)
        if not value:
            return None
        try:
            return _crypt(base64.b64decode(value), False).decode()
        except (OSError, ValueError, RuntimeError):
            return None

    def forget(self, cid):
        self.db.execute('DELETE FROM settings WHERE key=?', ('credential:' + cid,))
