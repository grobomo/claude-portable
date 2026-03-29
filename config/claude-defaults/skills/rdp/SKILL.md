# RDP Skill -- Silent Remote Desktop Connection

Connect to Windows VMs via RDP with ZERO prompts, ZERO verification dialogs, ZERO user interaction.

## Connect RDP -- The ONLY Way That Works

There are TWO blocking prompts. Both must be defeated.

### Prompt 1: "Publisher can't be identified" (unsigned .rdp file warning)

**Fix: Don't use .rdp files.** Launch `mstsc /v:IP` directly via PowerShell (NOT bash -- bash mangles the args).

### Prompt 2: Lock screen password prompt (server-side)

**Fix: Auto-logon + reboot** OR **type password via win32com SendKeys** (escape `!` as `{!}`).

### Server-side setup (run ONCE via az vm run-command)

```powershell
# Disable NLA + SecurityLayer=0 so mstsc connects without CredSSP
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" -Name "UserAuthentication" -Value 0 -Type DWord
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" -Name "SecurityLayer" -Value 0 -Type DWord
Restart-Service TermService -Force

# Auto-logon (takes effect after reboot -- creates desktop session automatically)
$regPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Set-ItemProperty -Path $regPath -Name "AutoAdminLogon" -Value "1"
Set-ItemProperty -Path $regPath -Name "DefaultUserName" -Value "<USERNAME>"
Set-ItemProperty -Path $regPath -Name "DefaultPassword" -Value "<PASSWORD>"
Set-ItemProperty -Path $regPath -Name "ForceAutoLogon" -Value "1"

# Disable lock screen
New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization" -Name "NoLockScreen" -Value 1 -Type DWord
```

After setting auto-logon, **reboot the VM** (`az vm restart`). RDP will still show the lock screen on first connect but subsequent connects to the existing session won't.

### Client-side pre-trust (run BEFORE mstsc launch)

```powershell
$ip = '<TARGET_IP>'
# Suppress cert identity warning
New-Item -Path "HKCU:\Software\Microsoft\Terminal Server Client\Servers\$ip" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Terminal Server Client\Servers\$ip" -Name 'CertHash' -Value ([byte[]](0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0)) -Type Binary
Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Terminal Server Client' -Name 'AuthenticationLevelOverride' -Value 0 -Type DWord
```

### Full connect sequence

```bash
TARGET_IP=$(az vm list-ip-addresses -g <RG> -n <VM> --query "[0].virtualMachine.network.publicIpAddresses[0].ipAddress" -o tsv)

# Kill stale sessions
powershell -Command "Get-Process mstsc -ErrorAction SilentlyContinue | Stop-Process -Force"

# Store creds + pre-trust cert + launch (all via PowerShell to avoid bash arg mangling)
cmdkey /add:TERMSRV/$TARGET_IP /user:<USERNAME> /pass:<PASSWORD>

powershell -Command "
  New-Item -Path 'HKCU:\Software\Microsoft\Terminal Server Client\Servers\$TARGET_IP' -Force | Out-Null
  Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Terminal Server Client\Servers\$TARGET_IP' -Name 'CertHash' -Value ([byte[]](0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0)) -Type Binary
  Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Terminal Server Client' -Name 'AuthenticationLevelOverride' -Value 0 -Type DWord
  Start-Process mstsc -ArgumentList '/v:$TARGET_IP','/w:1280','/h:800'
"
```

### Type password into lock screen (if auto-logon not set up)

```python
# AFTER mstsc is connected and showing lock screen:
import ctypes, ctypes.wintypes as wt, time, win32com.client
user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

# Find RDP window
hwnd = None
def cb(h, _):
    global hwnd
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, buf, 256)
    if '<TARGET_IP>' in buf.value and user32.IsWindowVisible(h):
        hwnd = h; return False
    return True
user32.EnumWindows(WNDENUMPROC(cb), 0)

if hwnd:
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    shell = win32com.client.Dispatch('WScript.Shell')
    # CRITICAL: escape ! as {!} -- SendKeys treats ! as Alt key
    shell.SendKeys('YourPassword{!}{ENTER}')
```

## Screenshot RDP (no focus steal)

Uses **PrintWindow API** -- captures the mstsc window buffer even when behind other windows.

```python
python3 -c "
import ctypes, ctypes.wintypes as wt, time
from PIL import Image
user32 = ctypes.windll.user32; gdi32 = ctypes.windll.gdi32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

hwnd = None
def cb(h, _):
    global hwnd
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, buf, 256)
    if '<TARGET_IP>' in buf.value and user32.IsWindowVisible(h):
        hwnd = h; return False
    return True
user32.EnumWindows(WNDENUMPROC(cb), 0)
if not hwnd: print('No RDP'); exit(1)

user32.ShowWindow(hwnd, 9); time.sleep(0.5)
rect = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
w, h = rect.right - rect.left, rect.bottom - rect.top
hwndDC = user32.GetWindowDC(hwnd); mfcDC = gdi32.CreateCompatibleDC(hwndDC)
bmp = gdi32.CreateCompatibleBitmap(hwndDC, w, h); gdi32.SelectObject(mfcDC, bmp)
user32.PrintWindow(hwnd, mfcDC, 2)
class BMI(ctypes.Structure):
    _fields_ = [('biSize',ctypes.c_uint),('biWidth',ctypes.c_int),('biHeight',ctypes.c_int),('biPlanes',ctypes.c_ushort),('biBitCount',ctypes.c_ushort),('biCompression',ctypes.c_uint),('biSizeImage',ctypes.c_uint),('biXPelsPerMeter',ctypes.c_int),('biYPelsPerMeter',ctypes.c_int),('biClrUsed',ctypes.c_uint),('biClrImportant',ctypes.c_uint)]
bmi_h = BMI(); bmi_h.biSize=ctypes.sizeof(BMI); bmi_h.biWidth=w; bmi_h.biHeight=-h; bmi_h.biPlanes=1; bmi_h.biBitCount=32
buf = ctypes.create_string_buffer(w*h*4)
gdi32.GetDIBits(mfcDC, bmp, 0, h, buf, ctypes.byref(bmi_h), 0)
img = Image.frombuffer('RGBA', (w,h), buf, 'raw', 'BGRA', 0, 1)
img.save('<OUTPUT_PATH>.png')
print(f'Saved {w}x{h}')
gdi32.DeleteObject(bmp); gdi32.DeleteDC(mfcDC); user32.ReleaseDC(hwnd, hwndDC)
"
```

## Known Servers

### ddei-tester (Azure testing server)
- RG: `rg-dd-lab-bootstrap`
- Username: `testadmin`
- Password: `TestServer2026!`
- IP: dynamic (`az vm list-ip-addresses`)

## What does NOT work

| Approach | Why it fails |
|----------|-------------|
| `.rdp` file | "Publisher can't be identified" warning -- `LocalDevices` registry does NOT suppress it |
| `cmdkey` + NLA/CredSSP | Needs HKLM CredSSP delegation policy -- blocked by Constrained Language Mode |
| `mstsc /v:IP` args from bash | Bash mangles `/w:1280 /h:800` -- use PowerShell `Start-Process` |
| `SendKeys('password!')` | `!` = Alt key in SendKeys -- must escape as `{!}` |
| Edge headless in session 0 | Fails with exit 1002 (no display) -- both `--headless` and `--headless=new` |
| Auto-logon without reboot | Takes effect only after reboot |
| `ForceAutoLogon` for RDP | RDP with SecurityLayer=0 always shows lock screen regardless |

## Rules

1. NEVER steal focus -- use PrintWindow for screenshots, not ImageGrab
2. NEVER use .rdp files -- always `mstsc /v:IP` via PowerShell
3. NEVER use `sleep` before checking -- poll immediately
4. NEVER use bash to launch mstsc -- always PowerShell `Start-Process`
5. Always kill stale mstsc before reconnecting
6. Always get IP dynamically (IPs change on restart)
