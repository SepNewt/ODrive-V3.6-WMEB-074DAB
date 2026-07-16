# ODrive-V3.6-WMEB-074DAB

The ODrive v3.6 motor controller uses the STM32F405RG microcontroller from STMicroelectronics.

### Development log

## 08/07/2026 - Backing Up ODrive datas

# Goals:

Recover communication with the ODrive v3.6.
Investigate why RUN mode is not detected while DFU mode is functional.
Preserve the current configuration before attempting recovery.
# What I did:

Verified that the board successfully enters DFU mode.

Connected to the board using STM32CubeProgrammer.

Created two backups:

backup_08072026.bin (flash memory)
OB_backup.json (Option Bytes)
Investigated possible firmware recovery methods.

Explored the idea of inspecting and modifying the firmware binary using Ghidra. After evaluation, this approach appears unnecessarily complex and is not recommended unless all conventional recovery methods fail.

# Next steps:

Research practical methods to recover RUN mode while preserving the current configuration.
Investigate whether the configuration can be exported as a .json file without entering RUN mode.
If no practical recovery method is found within a reasonable amount of time, stop further investigation and proceed with:
    Performing a full chip erase.
    Flashing a clean ODrive firmware.
    Reconfiguring and recalibrating the board if necessary.

## 15/07/2026 - RUN Mode Recovery

# Goals:

Restore RUN mode while preserving the existing ODrive configuration and calibration.

# What I did:

Recovered and exported the latest valid configuration record from Flash.

Confirmed that sectors 10–11 contain configuration and calibration data.

Compared the installed firmware with the official ODrive v3.6 56V firmware.

Found 248 corrupted bytes in sector 0, mainly in the interrupt vector table. Sectors 1–5 matched the official firmware.

Created and flashed a repair image for sector 0 only.

Verified the repair without modifying the configuration sectors, Option Bytes, or OTP memory.

# Results:

UART TX changed from `0 V` to approximately `3.3 V`, confirming that firmware startup and UART initialization were restored.

DFU mode remains functional.

USB RUN mode is still not detected, and `odrivetool` reports `LIBUSB_ERROR_NOT_FOUND`.

# Next steps:

Retest UART communication.

Check Windows Device Manager and USB driver binding in RUN mode.

Investigate USB initialization, descriptors, cable, and host port.

After communication is restored, disable automatic axis startup before reconnecting the motors.

## 16/07/2026 — RUN Mode and Motor Control

### Goal

Restore ODrive communication in RUN mode and prepare Python motor control.

### Completed

- Fixed the conflicting Windows OEM USB driver.
- Windows now detects: ODrive 3.6 Native Interface
- Created the compatible environment:
  - `odrive051`
  - `odrive 0.5.1.post0`
- Connected successfully to ODrive:
  - Serial: `206D344F4230`
  - Hardware: `3.6-56V`
  - Firmware: `0.5.1-dev`
- Verified both Native USB/Fibre and USB ASCII communication.
- Confirmed that the previous configuration and calibration data were preserved.
- Read bus voltage, uptime, axis errors, motor status and encoder status.
- Prepared Python code for:
  - connection and calibration checks;
  - USB keepalive/reconnect;
  - two-motor velocity control;
  - torque-control testing;
  - watchdog feeding and safe return to `IDLE`.

### Current status

- DFU mode: working.
- RUN mode: working.
- Native USB: working.
- Configuration/calibration: preserved.
- Python motor control: working.

### Next steps

- Make a WebServer to wirelessly control the motors via WiFi or wireless.
