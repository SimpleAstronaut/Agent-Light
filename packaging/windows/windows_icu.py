import ctypes
import os
if os.name == 'nt':
    # Load the Windows API provider before any Qt DLL, even if user PATH contains ICU.
    ctypes.WinDLL(os.path.join(os.environ['SystemRoot'], 'System32', 'icuuc.dll'))
