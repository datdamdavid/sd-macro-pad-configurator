# SDINNOVATION / SDCX Macro Pad Configurator 🎛️

A modern, standalone offline configuration tool and graphical GUI for the cheap RGB multi-key macro pads sold under names like **SDINNOVATION SIDE-KEYBOARD**, **SDCX**, **Huali**, and **SD-TECH** on AliExpress, Temu, and Amazon (USB ID `6d7f:dcfe` and sibling models).

Unlike the cloud-based web tool (`sdcx-tech.com`), this tool runs **100% offline**, provides an interactive **visual graphical hardware keyboard display**, supports dual rotary encoders, macro step creation, RGB per-key effects, and writes configurations directly to the hardware's onboard flash memory.

---

## ✨ Features

- **Interactive Hardware Visualization**: Graphical 9-keypad chassis with responsive mechanical keycaps and dual knurled rotary encoders. Click any key or dial to immediately configure it.
- **Color-Coded Status Badges**:
  - 🟧 **MACRO**: Trigger saved macros (loop, hold, fixed repeats)
  - 🟦 **MEDIA**: Volume Up/Down, Mute, Play/Pause, Next/Prev, Brightness
  - 🟪 **KEY**: Keyboard shortcuts (`Ctrl+C`, `Alt+Tab`, `Win+D`, `F1`–`F24`, etc.)
  - 🟪 **MOUSE**: Left/Right/Middle clicks and scroll actions
  - ⬛ **OFF**: Disabled keys
- **Zero-Friction Shortcut Recorder**: Just click the shortcut input box and press any key combo on your keyboard.
- **Idiot-Proof Macro Builder**:
  - No cryptic syntax. Create macros step-by-step: *Type Text*, *Press Keys*, *Wait*, *Mouse Click*, *Hold/Release*.
  - Live Keystroke Recording: hit **● Record** and type freely.
  - Automatic memory tracking (4096-byte hardware limit).
  - Automatic safety backups saved to `backups/` before each flash commit.
- **Dual Rotary Encoder Support**: Dedicated controls for Dial 1 and Dial 2:
  - ⟲ Turn Left (CCW)
  - ⟳ Turn Right (CW)
  - 🔘 Center Push
- **RGB Lighting Controls**:
  - Preset animations: Solid, Breathing, Light-on-press, Tide, Per-key color mode.
  - Dynamic visual preview of per-key lighting directly on the canvas keys.
- **Profiles**: Switch between 6 onboard hardware profiles.

---

## 🚀 Download & Installation

Pre-built standalone single-file executables are available on the **[Releases](../../releases)** tab.

### 🐧 Linux

#### 1. Download Binary
Download `sdpad-gui-linux` from [Releases](../../releases).

#### 2. Set Udev Permissions (Required once on Linux)
Macro pads use USB HID raw endpoints (`/dev/hidraw*`). To configure the device without running as `root`:

```bash
# Copy the udev rule
sudo cp 99-sdpad.rules /etc/udev/rules.d/

# Reload udev rules and trigger
sudo udevadm control --reload && sudo udevadm trigger
```
*(If your user is not in `plugdev` or `input`, you can add yourself with `sudo usermod -aG plugdev $USER`).*

#### 3. Run
```bash
chmod +x sdpad-gui-linux
./sdpad-gui-linux
```

---

### 🪟 Windows

1. Download `sdpad-gui.exe` from [Releases](../../releases).
2. Plug in your macro pad.
3. Double-click `sdpad-gui.exe` to run. No drivers or website needed!

---

## 🛠️ Running from Source (Python)

If you prefer to run directly from source:

### Requirements
- Python 3.9+
- Tkinter (standard with Python on Windows/macOS; on Debian/Ubuntu: `sudo apt install python3-tk`)
- `hidapi` (optional on Linux as it can use `/dev/hidraw`, required on Windows):
  ```bash
  pip install hidapi
  ```

### Launch GUI
```bash
python3 sdpad_gui.py
```

### Command-Line CLI (`sdpad.py`)
A fast standalone CLI is also included for headless setups, shell scripts, or quick inspection:
```bash
# View connected pad hardware info
python3 sdpad.py info

# List current key & dial mappings
python3 sdpad.py keys

# Map Key 1 to Ctrl+Shift+Esc
python3 sdpad.py set 0 ctrl+shift+esc

# Map Dial 1 Turn Right to Volume Up
python3 sdpad.py set 17 media:volup

# Set lighting to solid color #00FF99
python3 sdpad.py light solid --colour "#00ff99"
```

---

## 📦 Building Standalone Binaries Locally

To build standalone single-file executables on your own machine using PyInstaller:

```bash
pip install pyinstaller hidapi
pyinstaller --noconfirm --onefile --windowed --name "sdpad-gui" sdpad_gui.py
```
The resulting executable will be in the `dist/` directory.

---

## 🔒 Hardware Persistence & Safety Notes

- **Settings live directly on the pad**: Once configured, you can unplug the device and take it to any PC, Mac, or gaming console without needing this software installed.
- **Safety First**: Every change writes to the microcontroller's onboard flash memory. The app automatically verifies replies from the device and creates local timestamped backups in `backups/` whenever macros are written.

---

## 📜 License
MIT License.
