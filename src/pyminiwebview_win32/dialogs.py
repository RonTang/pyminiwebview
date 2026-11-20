import ctypes
from ctypes import wintypes

_OFN_OVERWRITEPROMPT = 0x00000002
_OFN_HIDEREADONLY = 0x00000004
_OFN_PATHMUSTEXIST = 0x00000800
_OFN_FILEMUSTEXIST = 0x00001000
_OFN_EXPLORER = 0x00080000


class _OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", wintypes.LPARAM),
        ("lpfnHook", ctypes.c_void_p),
        ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", ctypes.c_void_p),
        ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]


_comdlg32 = ctypes.WinDLL("comdlg32", use_last_error=True)
_comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(_OPENFILENAMEW)]
_comdlg32.GetOpenFileNameW.restype = wintypes.BOOL
_comdlg32.GetSaveFileNameW.argtypes = [ctypes.POINTER(_OPENFILENAMEW)]
_comdlg32.GetSaveFileNameW.restype = wintypes.BOOL
_comdlg32.CommDlgExtendedError.argtypes = []
_comdlg32.CommDlgExtendedError.restype = wintypes.DWORD


def _file_dialog(save, hwnd_owner, title, filters, initial_dir, initial_file):
    if filters is None:
        filters = [("All Files", "*.*")]
    filter_text = "\0".join(
        f"{description}\0{pattern}" for description, pattern in filters
    ) + "\0\0"
    buffer = ctypes.create_unicode_buffer(32768)
    if initial_file:
        buffer.value = initial_file

    ofn = _OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(_OPENFILENAMEW)
    ofn.hwndOwner = hwnd_owner
    ofn.lpstrFilter = filter_text
    ofn.lpstrFile = ctypes.cast(buffer, wintypes.LPWSTR)
    ofn.nMaxFile = len(buffer)
    ofn.lpstrInitialDir = initial_dir
    ofn.lpstrTitle = title
    ofn.Flags = _OFN_EXPLORER | _OFN_PATHMUSTEXIST | _OFN_HIDEREADONLY
    if save:
        ofn.Flags |= _OFN_OVERWRITEPROMPT
        function = _comdlg32.GetSaveFileNameW
    else:
        ofn.Flags |= _OFN_FILEMUSTEXIST
        function = _comdlg32.GetOpenFileNameW

    if function(ctypes.byref(ofn)):
        return buffer.value
    error = _comdlg32.CommDlgExtendedError()
    if error:
        raise ctypes.WinError(error)
    return None


def open_file_dialog(hwnd_owner=None, title="Open File", filters=None,
                     initial_dir=None, initial_file=None):
    """Return the selected existing path, or None when the user cancels.

    ``initial_file`` is limited to 32767 characters by the Win32 buffer.
    """
    return _file_dialog(
        False, hwnd_owner, title, filters, initial_dir, initial_file
    )


def save_file_dialog(hwnd_owner=None, title="Save File", filters=None,
                     initial_dir=None, initial_file=None):
    """Return the selected save path, or None when the user cancels.

    ``initial_file`` is limited to 32767 characters by the Win32 buffer.
    """
    return _file_dialog(
        True, hwnd_owner, title, filters, initial_dir, initial_file
    )
