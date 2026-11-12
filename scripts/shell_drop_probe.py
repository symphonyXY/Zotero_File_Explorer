"""Exercise the native Shell IDropTarget in a second process.

The Qt clipboard owner must keep pumping its event loop to render delayed formats.
No mouse injection, Explorer automation or source-file changes are performed here.
"""

import ctypes
import sys
import uuid
from ctypes import wintypes


class GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]

    def __init__(self, text):
        super().__init__((ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(text).bytes_le))


def method(pointer, index, restype, argtypes, *args):
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])(pointer, *args)


def main(target):
    ole = ctypes.OleDLL("ole32")
    shell = ctypes.OleDLL("shell32")
    ole.OleInitialize(None)
    print("ole initialized", flush=True)
    ole.OleGetClipboard.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    shell.SHCreateItemFromParsingName.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    data, item, drop_target = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        assert ole.OleGetClipboard(ctypes.byref(data)) == 0
        print("clipboard acquired", flush=True)
        assert (
            shell.SHCreateItemFromParsingName(
                target, None, ctypes.byref(GUID("43826d1e-e718-42ee-bc55-a1e261c37bfe")), ctypes.byref(item)
            )
            == 0
        )
        print("shell item acquired", flush=True)
        assert (
            method(
                item,
                3,
                ctypes.c_long,
                [
                    ctypes.c_void_p,
                    ctypes.POINTER(GUID),
                    ctypes.POINTER(GUID),
                    ctypes.POINTER(ctypes.c_void_p),
                ],
                None,
                ctypes.byref(GUID("3981e225-f559-11d3-8e3a-00c04f6837d5")),
                ctypes.byref(GUID("00000122-0000-0000-c000-000000000046")),
                ctypes.byref(drop_target),
            )
            == 0
        )
        print("drop target acquired", flush=True)
        effect = wintypes.DWORD(1)
        types = [ctypes.c_void_p, wintypes.DWORD, wintypes.POINT, ctypes.POINTER(wintypes.DWORD)]
        # DragEnter/DragOver describe a held LEFT button; Drop describes its release.
        # Omitting MK_LBUTTON makes the filesystem target enter a drop-choice menu,
        # which blocks TrackPopupMenu and cannot complete in this non-gesture probe.
        held_keys, released_keys = 0x0001 | 0x0008, 0x0008  # MK_LBUTTON | MK_CONTROL
        assert (
            method(drop_target, 3, ctypes.c_long, types, data, held_keys,
                   wintypes.POINT(0, 0), ctypes.byref(effect))
            == 0
        )
        assert effect.value == 1
        print("drag enter accepted", flush=True)
        assert (
            method(
                drop_target,
                4,
                ctypes.c_long,
                [wintypes.DWORD, wintypes.POINT, ctypes.POINTER(wintypes.DWORD)],
                held_keys,
                wintypes.POINT(0, 0),
                ctypes.byref(effect),
            )
            == 0
        )
        print("drag over accepted", flush=True)
        effect.value = 1
        assert (
            method(drop_target, 6, ctypes.c_long, types, data, released_keys,
                   wintypes.POINT(0, 0), ctypes.byref(effect))
            == 0
        )
        assert effect.value == 1
        print("Native Shell drop completed with DROPEFFECT_COPY", flush=True)
    finally:
        for pointer in [drop_target, item, data]:
            if pointer:
                method(pointer, 2, ctypes.c_ulong, [])
        ole.OleUninitialize()


if __name__ == "__main__":
    main(sys.argv[1])
