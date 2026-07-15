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
