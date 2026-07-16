import odrive

print("Đang tìm ODrive...")
odrv0 = odrive.find_any(timeout = 10)
print("Đã kết nối!")

for i, axis in enumerate([odrv0.axis0, odrv0.axis1]):
    print(f"\nAxis {i}")
    print("Motor pre_calibrated :", axis.motor.config.pre_calibrated)
    print("Motor calibrated     :", axis.motor.is_calibrated)
    print("Encoder pre_calibrated:", axis.encoder.config.pre_calibrated)
    print("Encoder ready        :", axis.encoder.is_ready)
    print("Axis error           :", hex(axis.error))

print(odrv0.axis0.current_state)
print(odrv0.axis1.current_state)