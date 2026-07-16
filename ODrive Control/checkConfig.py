import sys
import odrive

try:
    from odrive.enums import *
except ImportError:
    print("Không import được odrive.enums")
    sys.exit(1)


SERIAL_NUMBER = "206D344F4230"


def safe_read(label, getter):
    try:
        value = getter()
        print(f"{label:<36}: {value}")
        return value
    except Exception as exc:
        print(f"{label:<36}: <không đọc được: {exc}>")
        return None


print("Đang kết nối ODrive...")

odrv0 = odrive.find_any(
    serial_number=SERIAL_NUMBER,
    timeout=20
)

if odrv0 is None:
    print("Không tìm thấy ODrive.")
    sys.exit(1)

print("Đã kết nối.\n")

# Dừng cả hai motor trước khi đọc cấu hình.
for axis in (odrv0.axis0, odrv0.axis1):
    try:
        axis.requested_state = AXIS_STATE_IDLE
    except Exception as exc:
        print("Không thể đưa axis về IDLE:", exc)

for index, axis in enumerate((odrv0.axis0, odrv0.axis1)):
    print("=" * 65)
    print(f"AXIS {index}")
    print("=" * 65)

    print("\n[Trạng thái axis]")
    safe_read("current_state", lambda: axis.current_state)
    safe_read("requested_state", lambda: axis.requested_state)
    safe_read("axis.error", lambda: hex(axis.error))

    print("\n[Startup configuration]")
    safe_read(
        "startup_motor_calibration",
        lambda: axis.config.startup_motor_calibration
    )
    safe_read(
        "startup_encoder_index_search",
        lambda: axis.config.startup_encoder_index_search
    )
    safe_read(
        "startup_encoder_offset_calibration",
        lambda: axis.config.startup_encoder_offset_calibration
    )
    safe_read(
        "startup_closed_loop_control",
        lambda: axis.config.startup_closed_loop_control
    )

    print("\n[Controller]")
    safe_read(
        "control_mode",
        lambda: axis.controller.config.control_mode
    )
    safe_read(
        "input_mode",
        lambda: axis.controller.config.input_mode
    )
    safe_read(
        "input_pos",
        lambda: axis.controller.input_pos
    )
    safe_read(
        "input_vel",
        lambda: axis.controller.input_vel
    )
    safe_read(
        "input_torque",
        lambda: axis.controller.input_torque
    )
    safe_read(
        "vel_setpoint",
        lambda: axis.controller.vel_setpoint
    )
    safe_read(
        "pos_setpoint",
        lambda: axis.controller.pos_setpoint
    )

    print("\n[Controller limits]")
    safe_read(
        "vel_limit",
        lambda: axis.controller.config.vel_limit
    )
    safe_read(
        "vel_gain",
        lambda: axis.controller.config.vel_gain
    )
    safe_read(
        "pos_gain",
        lambda: axis.controller.config.pos_gain
    )
    safe_read(
        "vel_integrator_gain",
        lambda: axis.controller.config.vel_integrator_gain
    )

    print("\n[Encoder]")
    safe_read("encoder.is_ready", lambda: axis.encoder.is_ready)
    safe_read("encoder.error", lambda: hex(axis.encoder.error))
    safe_read("pos_estimate", lambda: axis.encoder.pos_estimate)
    safe_read("vel_estimate", lambda: axis.encoder.vel_estimate)
    safe_read(
        "encoder.mode",
        lambda: axis.encoder.config.mode
    )
    safe_read(
        "encoder.use_index",
        lambda: axis.encoder.config.use_index
    )
    safe_read(
        "encoder.cpr",
        lambda: axis.encoder.config.cpr
    )

    print("\n[Motor]")
    safe_read("motor.is_calibrated", lambda: axis.motor.is_calibrated)
    safe_read("motor.error", lambda: hex(axis.motor.error))
    safe_read(
        "current_lim",
        lambda: axis.motor.config.current_lim
    )
    safe_read(
        "torque_constant",
        lambda: axis.motor.config.torque_constant
    )

    print("\n[Watchdog]")
    safe_read(
        "enable_watchdog",
        lambda: axis.config.enable_watchdog
    )
    safe_read(
        "watchdog_timeout",
        lambda: axis.config.watchdog_timeout
    )

print("\nĐã đọc xong. Hai axis vẫn đang ở IDLE.")