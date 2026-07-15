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
