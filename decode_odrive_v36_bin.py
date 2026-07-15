#!/usr/bin/env python3
"""Decode the persistent configuration from an ODrive v3.x flash .bin.

Profile implemented here:
  ODrive v3.6 / firmware fw-v0.5.1 (config_version 0x0001)

The input may be:
  * a full 1 MiB STM32F405 flash dump, or
  * a dump containing one or more 128 KiB NVM sectors aligned to 128 KiB.

Usage:
  python decode_odrive_v36_bin.py backup.bin
  python decode_odrive_v36_bin.py backup.bin -o config.json
  python decode_odrive_v36_bin.py backup.bin --full-cogging-map

The decoder deliberately refuses files whose NVM allocation/CRC/layout does not
match this profile, rather than returning plausible-looking but shifted values.
"""

from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
import math
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# ODrive fw-v0.5.1 NVM format
# ---------------------------------------------------------------------------
NVM_SECTOR_SIZE = 128 * 1024
NVM_ALLOCATION_BYTES = 4096
NVM_FIELD_SIZE = 8
NVM_FIELD_COUNT = NVM_SECTOR_SIZE // NVM_FIELD_SIZE
NVM_FIRST_DATA_FIELD = NVM_ALLOCATION_BYTES // NVM_FIELD_SIZE

NVM_STATE_VALID = 0
NVM_STATE_INVALID = 1
NVM_STATE_ERASED = 3

CONFIG_VERSION = 0x0001
CRC_INITIAL = 0xABCD ^ CONFIG_VERSION
CRC_POLYNOMIAL = 0x3D65

# STM32F405 full-flash offsets used by ODrive fw-v0.5.1.
KNOWN_FLASH_SECTORS = {
    0x0C0000: 10,
    0x0E0000: 11,
}

# ---------------------------------------------------------------------------
# Exact 32-bit ARM C++ object layout used by fw-v0.5.1
# ---------------------------------------------------------------------------
# Use explicit-width scalar types so this script gives the same layout on
# 32-bit and 64-bit host computers. Firmware pointers are stored as uint32.
Bool = C.c_bool
U8 = C.c_uint8
U16 = C.c_uint16
U32 = C.c_uint32
I32 = C.c_int32
F32 = C.c_float
Ptr32 = C.c_uint32


class PWMMapping(C.LittleEndianStructure):
    _fields_ = [
        ("endpoint", U32),
        ("min", F32),
        ("max", F32),
    ]


class BoardConfig(C.LittleEndianStructure):
    _fields_ = [
        ("enable_uart", Bool),
        ("enable_i2c_instead_of_can", Bool),
        ("enable_ascii_protocol_on_usb", Bool),
        ("max_regen_current", F32),
        ("brake_resistance", F32),
        ("dc_bus_undervoltage_trip_level", F32),
        ("dc_bus_overvoltage_trip_level", F32),
        ("enable_dc_bus_overvoltage_ramp", Bool),
        ("dc_bus_overvoltage_ramp_start", F32),
        ("dc_bus_overvoltage_ramp_end", F32),
        ("dc_max_positive_current", F32),
        ("dc_max_negative_current", F32),
        ("pwm_mappings", PWMMapping * 8),
        ("analog_mappings", PWMMapping * 8),
        ("uart_baudrate", U32),
    ]


class CANConfig(C.LittleEndianStructure):
    _fields_ = [
        ("baud_rate", U32),
        ("protocol", U8),
    ]


class EncoderConfig(C.LittleEndianStructure):
    _fields_ = [
        ("mode", U16),
        ("use_index", Bool),
        ("pre_calibrated", Bool),
        ("zero_count_on_find_idx", Bool),
        ("cpr", I32),
        ("offset", I32),
        ("offset_float", F32),
        ("enable_phase_interpolation", Bool),
        ("calib_range", F32),
        ("calib_scan_distance", F32),
        ("calib_scan_omega", F32),
        ("bandwidth", F32),
        ("find_idx_on_lockin_only", Bool),
        ("idx_search_unidirectional", Bool),
        ("ignore_illegal_hall_state", Bool),
        ("abs_spi_cs_gpio_pin", U16),
        ("sincos_gpio_pin_sin", U16),
        ("sincos_gpio_pin_cos", U16),
        ("parent", Ptr32),  # internal runtime pointer; not a user parameter
    ]


class SensorlessEstimatorConfig(C.LittleEndianStructure):
    _fields_ = [
        ("observer_gain", F32),
        ("pll_bandwidth", F32),
        ("pm_flux_linkage", F32),
    ]


class AnticoggingConfig(C.LittleEndianStructure):
    _fields_ = [
        ("index", U32),
        ("cogging_map", F32 * 3600),
        ("pre_calibrated", Bool),
        ("calib_anticogging", Bool),
        ("calib_pos_threshold", F32),
        ("calib_vel_threshold", F32),
        ("cogging_ratio", F32),
        ("anticogging_enabled", Bool),
    ]


class ControllerConfig(C.LittleEndianStructure):
    _fields_ = [
        ("control_mode", U8),
        ("input_mode", U8),
        ("pos_gain", F32),
        ("vel_gain", F32),
        ("vel_integrator_gain", F32),
        ("vel_limit", F32),
        ("vel_limit_tolerance", F32),
        ("vel_ramp_rate", F32),
        ("torque_ramp_rate", F32),
        ("circular_setpoints", Bool),
        ("circular_setpoint_range", F32),
        ("inertia", F32),
        ("input_filter_bandwidth", F32),
        ("homing_speed", F32),
        ("anticogging", AnticoggingConfig),
        ("gain_scheduling_width", F32),
        ("enable_gain_scheduling", Bool),
        ("enable_vel_limit", Bool),
        ("enable_overspeed_error", Bool),
        ("enable_current_mode_vel_limit", Bool),
        ("axis_to_mirror", U8),
        ("mirror_ratio", F32),
        ("load_encoder_axis", U8),
        ("parent", Ptr32),  # internal runtime pointer
    ]


class MotorConfig(C.LittleEndianStructure):
    _fields_ = [
        ("pre_calibrated", Bool),
        ("pole_pairs", I32),
        ("calibration_current", F32),
        ("resistance_calib_max_voltage", F32),
        ("phase_inductance", F32),
        ("phase_resistance", F32),
        ("torque_constant", F32),
        ("direction", I32),
        ("motor_type", U32),
        ("current_lim", F32),
        ("current_lim_margin", F32),
        ("torque_lim", F32),
        ("requested_current_range", F32),
        ("current_control_bandwidth", F32),
        ("inverter_temp_limit_lower", F32),
        ("inverter_temp_limit_upper", F32),
        ("acim_slip_velocity", F32),
        ("acim_gain_min_flux", F32),
        ("acim_autoflux_min_Id", F32),
        ("acim_autoflux_enable", Bool),
        ("acim_autoflux_attack_gain", F32),
        ("acim_autoflux_decay_gain", F32),
        ("parent", Ptr32),  # internal runtime pointer
    ]


class OnboardThermistorConfig(C.LittleEndianStructure):
    _fields_ = [
        ("temp_limit_lower", F32),
        ("temp_limit_upper", F32),
        ("enabled", Bool),
    ]


class OffboardThermistorConfig(C.LittleEndianStructure):
    _fields_ = [
        ("thermistor_poly_coeffs", F32 * 4),
        ("gpio_pin", U16),
        ("temp_limit_lower", F32),
        ("temp_limit_upper", F32),
        ("enabled", Bool),
        ("parent", Ptr32),  # internal runtime pointer
    ]


class TrapTrajConfig(C.LittleEndianStructure):
    _fields_ = [
        ("vel_limit", F32),
        ("accel_limit", F32),
        ("decel_limit", F32),
    ]


class EndstopConfig(C.LittleEndianStructure):
    _fields_ = [
        ("offset", F32),
        ("debounce_ms", U32),
        ("gpio_num", U16),
        ("enabled", Bool),
        ("is_active_high", Bool),
        ("pullup", Bool),
        ("parent", Ptr32),  # internal runtime pointer
    ]


class LockinConfig(C.LittleEndianStructure):
    _fields_ = [
        ("current", F32),
        ("ramp_time", F32),
        ("ramp_distance", F32),
        ("accel", F32),
        ("vel", F32),
        ("finish_distance", F32),
        ("finish_on_vel", Bool),
        ("finish_on_distance", Bool),
        ("finish_on_enc_idx", Bool),
    ]


class AxisConfig(C.LittleEndianStructure):
    _fields_ = [
        ("startup_motor_calibration", Bool),
        ("startup_encoder_index_search", Bool),
        ("startup_encoder_offset_calibration", Bool),
        ("startup_closed_loop_control", Bool),
        ("startup_sensorless_control", Bool),
        ("startup_homing", Bool),
        ("enable_step_dir", Bool),
        ("step_dir_always_on", Bool),
        ("turns_per_step", F32),
        ("watchdog_timeout", F32),
        ("enable_watchdog", Bool),
        ("step_gpio_pin", U16),
        ("dir_gpio_pin", U16),
        ("calibration_lockin", LockinConfig),
        ("sensorless_ramp", LockinConfig),
        ("general_lockin", LockinConfig),
        ("can_node_id", U32),
        ("can_node_id_extended", Bool),
        ("can_heartbeat_rate_ms", U32),
        ("parent", Ptr32),  # internal runtime pointer
    ]


# Serialization order in fw-v0.5.1 main.cpp.
SERIAL_LAYOUT: tuple[tuple[str, type[C.Structure], int], ...] = (
    ("board", BoardConfig, 1),
    ("can", CANConfig, 1),
    ("encoder", EncoderConfig, 2),
    ("sensorless_estimator", SensorlessEstimatorConfig, 2),
    ("controller", ControllerConfig, 2),
    ("motor", MotorConfig, 2),
    ("onboard_thermistor", OnboardThermistorConfig, 2),
    ("offboard_thermistor", OffboardThermistorConfig, 2),
    ("trap_traj", TrapTrajConfig, 2),
    ("min_endstop", EndstopConfig, 2),
    ("max_endstop", EndstopConfig, 2),
    ("axis", AxisConfig, 2),
)

CONFIG_PAYLOAD_SIZE = sum(C.sizeof(cls) * count for _, cls, count in SERIAL_LAYOUT)
CONFIG_CRC_SIZE = 2
CONFIG_STORED_SIZE = ((CONFIG_PAYLOAD_SIZE + CONFIG_CRC_SIZE + 7) // 8) * 8
CONFIG_FIELD_COUNT = CONFIG_STORED_SIZE // NVM_FIELD_SIZE

# Hard safety checks: a host ABI/layout error must fail loudly.
EXPECTED_SIZES = {
    BoardConfig: 236,
    CANConfig: 8,
    EncoderConfig: 56,
    SensorlessEstimatorConfig: 12,
    AnticoggingConfig: 14424,
    ControllerConfig: 14500,
    MotorConfig: 92,
    OnboardThermistorConfig: 12,
    OffboardThermistorConfig: 36,
    TrapTrajConfig: 12,
    EndstopConfig: 20,
    LockinConfig: 28,
    AxisConfig: 124,
}
for _cls, _expected in EXPECTED_SIZES.items():
    if C.sizeof(_cls) != _expected:
        raise RuntimeError(
            f"Host ctypes layout mismatch for {_cls.__name__}: "
            f"got {C.sizeof(_cls)}, expected {_expected}"
        )
if CONFIG_PAYLOAD_SIZE != 30012 or CONFIG_STORED_SIZE != 30016:
    raise RuntimeError("Unexpected fw-v0.5.1 aggregate configuration size")

# ---------------------------------------------------------------------------
# Enum names from the fw-v0.5.1 interface definition
# ---------------------------------------------------------------------------
ENCODER_MODES = {
    0: "Incremental",
    1: "Hall",
    2: "Sincos",
    0x100: "SpiAbsCui",
    0x101: "SpiAbsAms",
    0x102: "SpiAbsAeat",
    0x103: "SpiAbsRls",
}
CONTROL_MODES = {
    0: "VoltageControl",
    1: "TorqueControl",
    2: "VelocityControl",
    3: "PositionControl",
}
INPUT_MODES = {
    0: "Inactive",
    1: "Passthrough",
    2: "VelRamp",
    3: "PosFilter",
    4: "MixChannels",
    5: "TrapTraj",
    6: "TorqueRamp",
    7: "Mirror",
    8: "Tuning",
}
MOTOR_TYPES = {
    0: "HighCurrent",
    2: "Gimbal",
    3: "ACIM",
}
CAN_PROTOCOLS = {
    0: "Simple",
}


@dataclass(frozen=True)
class Snapshot:
    sector_offset: int
    sector_number: int | None
    start_field: int
    field_count: int
    file_offset: int
    active_marker: bool
    crc_valid: bool
    stored_crc: int
    calculated_crc: int
    padding_hex: str


def crc16_odrive(data: bytes, initial: int = CRC_INITIAL) -> int:
    """ODrive Fibre CRC16: polynomial 0x3D65, MSB-first."""
    remainder = initial & 0xFFFF
    for value in data:
        remainder ^= value << 8
        for _ in range(8):
            if remainder & 0x8000:
                remainder = ((remainder << 1) ^ CRC_POLYNOMIAL) & 0xFFFF
            else:
                remainder = (remainder << 1) & 0xFFFF
    return remainder


def allocation_states(sector: bytes) -> list[int]:
    if len(sector) < NVM_SECTOR_SIZE:
        raise ValueError("NVM sector is shorter than 128 KiB")
    table = sector[:NVM_ALLOCATION_BYTES]
    return [
        (table[index // 4] >> (2 * (index % 4))) & 0x03
        for index in range(NVM_FIELD_COUNT)
    ]


def state_runs(states: list[int], start: int = NVM_FIRST_DATA_FIELD) -> Iterable[tuple[int, int, int]]:
    """Yield (start_field, field_count, state) runs."""
    run_start = start
    run_state = states[start]
    for index in range(start + 1, len(states)):
        if states[index] != run_state:
            yield run_start, index - run_start, run_state
            run_start = index
            run_state = states[index]
    yield run_start, len(states) - run_start, run_state


def iter_sector_offsets(data: bytes) -> Iterable[int]:
    """Scan 128 KiB-aligned blocks, supporting full-flash and NVM-only dumps."""
    for offset in range(0, len(data) - NVM_SECTOR_SIZE + 1, NVM_SECTOR_SIZE):
        yield offset


def find_snapshots(data: bytes) -> list[Snapshot]:
    snapshots: list[Snapshot] = []
    for sector_offset in iter_sector_offsets(data):
        sector = data[sector_offset : sector_offset + NVM_SECTOR_SIZE]
        states = allocation_states(sector)

        for start_field, field_count, state in state_runs(states):
            if state != NVM_STATE_VALID or field_count != CONFIG_FIELD_COUNT:
                continue

            file_offset = sector_offset + start_field * NVM_FIELD_SIZE
            block = data[file_offset : file_offset + CONFIG_STORED_SIZE]
            if len(block) != CONFIG_STORED_SIZE:
                continue

            payload = block[:CONFIG_PAYLOAD_SIZE]
            stored_crc_bytes = block[CONFIG_PAYLOAD_SIZE : CONFIG_PAYLOAD_SIZE + 2]
            stored_crc = int.from_bytes(stored_crc_bytes, "big")
            calculated_crc = crc16_odrive(payload)
            crc_valid = (
                calculated_crc == stored_crc
                and crc16_odrive(payload + stored_crc_bytes) == 0
            )

            next_field = start_field + field_count
            active_marker = (
                next_field >= NVM_FIELD_COUNT
                or states[next_field] == NVM_STATE_ERASED
            )
            snapshots.append(
                Snapshot(
                    sector_offset=sector_offset,
                    sector_number=KNOWN_FLASH_SECTORS.get(sector_offset),
                    start_field=start_field,
                    field_count=field_count,
                    file_offset=file_offset,
                    active_marker=active_marker,
                    crc_valid=crc_valid,
                    stored_crc=stored_crc,
                    calculated_crc=calculated_crc,
                    padding_hex=block[CONFIG_PAYLOAD_SIZE + 2 :].hex(),
                )
            )
    return snapshots


def select_active_snapshot(snapshots: list[Snapshot]) -> Snapshot:
    active = [s for s in snapshots if s.active_marker and s.crc_valid]
    if len(active) == 1:
        return active[0]
    if len(active) > 1:
        unique_offsets = ", ".join(f"0x{s.file_offset:x}" for s in active)
        raise ValueError(
            "Multiple active CRC-valid NVM snapshots were found "
            f"({unique_offsets}); refusing to guess."
        )

    valid = [s for s in snapshots if s.crc_valid]
    if len(valid) == 1:
        return valid[0]
    if not snapshots:
        raise ValueError(
            "No fw-v0.5.1 configuration snapshot was found. The file may not "
            "contain ODrive NVM sectors, or it may use another firmware layout."
        )
    if not valid:
        raise ValueError(
            "NVM-shaped snapshots were found, but all failed the fw-v0.5.1 CRC check."
        )
    raise ValueError(
        "Several CRC-valid historical snapshots exist but none has an active marker; "
        "refusing to choose one silently."
    )


def finite_json_number(value: float) -> float | str:
    value = float(value)
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    return value


def endpoint_mapping_to_dict(mapping: PWMMapping) -> dict[str, Any]:
    endpoint_raw = int(mapping.endpoint)
    return {
        "endpoint_ref": None if endpoint_raw == 0 else f"0x{endpoint_raw:08x}",
        "min": finite_json_number(mapping.min),
        "max": finite_json_number(mapping.max),
    }


def struct_to_dict(obj: C.Structure, *, full_cogging_map: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    internal: dict[str, Any] = {}

    for name, field_type in obj._fields_:
        value = getattr(obj, name)

        if name == "parent":
            internal["parent_pointer"] = f"0x{int(value):08x}"
            continue

        if name in ("pwm_mappings", "analog_mappings"):
            out[name] = [endpoint_mapping_to_dict(item) for item in value]
            continue

        if name == "cogging_map":
            values = [finite_json_number(item) for item in value]
            if full_cogging_map:
                out[name] = values
            else:
                sparse = [
                    {"index": i, "value": item}
                    for i, item in enumerate(values)
                    if item != 0.0
                ]
                out[name] = {
                    "encoding": "sparse",
                    "length": len(values),
                    "default": 0.0,
                    "nonzero_entries": sparse,
                }
            continue

        if isinstance(value, C.Array):
            out[name] = [
                struct_to_dict(item, full_cogging_map=full_cogging_map)
                if isinstance(item, C.Structure)
                else finite_json_number(item) if isinstance(item, float)
                else item
                for item in value
            ]
        elif isinstance(value, C.Structure):
            out[name] = struct_to_dict(value, full_cogging_map=full_cogging_map)
        elif isinstance(value, float):
            out[name] = finite_json_number(value)
        elif isinstance(value, bool):
            out[name] = value
        else:
            out[name] = int(value)

    if internal:
        out["_internal"] = internal
    return out


def parse_serialized_payload(payload: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(payload) != CONFIG_PAYLOAD_SIZE:
        raise ValueError(
            f"Configuration payload is {len(payload)} bytes; expected {CONFIG_PAYLOAD_SIZE}."
        )

    parsed: dict[str, Any] = {}
    layout_meta: dict[str, Any] = {}
    offset = 0
    for name, cls, count in SERIAL_LAYOUT:
        items: list[C.Structure] = []
        section_offset = offset
        for _ in range(count):
            items.append(cls.from_buffer_copy(payload, offset))
            offset += C.sizeof(cls)
        parsed[name] = items[0] if count == 1 else items
        layout_meta[name] = {
            "payload_offset": section_offset,
            "element_size": C.sizeof(cls),
            "count": count,
            "total_size": C.sizeof(cls) * count,
        }

    if offset != CONFIG_PAYLOAD_SIZE:
        raise RuntimeError("Internal layout parser did not consume the whole payload")
    return parsed, layout_meta


def with_enum(value: int, names: dict[int, str]) -> dict[str, Any]:
    return {"value": value, "name": names.get(value, "Unknown")}


def axis_to_dict(
    index: int,
    parsed: dict[str, Any],
    *,
    full_cogging_map: bool,
) -> dict[str, Any]:
    encoder = struct_to_dict(parsed["encoder"][index], full_cogging_map=full_cogging_map)
    encoder["mode"] = with_enum(int(parsed["encoder"][index].mode), ENCODER_MODES)

    controller = struct_to_dict(parsed["controller"][index], full_cogging_map=full_cogging_map)
    controller["control_mode"] = with_enum(
        int(parsed["controller"][index].control_mode), CONTROL_MODES
    )
    controller["input_mode"] = with_enum(
        int(parsed["controller"][index].input_mode), INPUT_MODES
    )

    motor = struct_to_dict(parsed["motor"][index], full_cogging_map=full_cogging_map)
    motor["motor_type"] = with_enum(int(parsed["motor"][index].motor_type), MOTOR_TYPES)

    return {
        "config": struct_to_dict(parsed["axis"][index], full_cogging_map=full_cogging_map),
        "motor": motor,
        "encoder": encoder,
        "controller": controller,
        "sensorless_estimator": struct_to_dict(
            parsed["sensorless_estimator"][index], full_cogging_map=full_cogging_map
        ),
        "fet_thermistor": struct_to_dict(
            parsed["onboard_thermistor"][index], full_cogging_map=full_cogging_map
        ),
        "motor_thermistor": struct_to_dict(
            parsed["offboard_thermistor"][index], full_cogging_map=full_cogging_map
        ),
        "trap_traj": struct_to_dict(
            parsed["trap_traj"][index], full_cogging_map=full_cogging_map
        ),
        "min_endstop": struct_to_dict(
            parsed["min_endstop"][index], full_cogging_map=full_cogging_map
        ),
        "max_endstop": struct_to_dict(
            parsed["max_endstop"][index], full_cogging_map=full_cogging_map
        ),
    }


def firmware_fingerprint(data: bytes) -> dict[str, Any]:
    strings = {
        "odrive_v36_usb_string": b"ODrive 3.6" in data,
        "old_uart_api": b"enable_uart" in data,
        "old_i2c_can_mux_api": b"enable_i2c_instead_of_can" in data,
        "current_lim_margin_api": b"current_lim_margin" in data,
    }
    matches = sum(strings.values())
    return {
        "profile": "ODrive v3.6 / fw-v0.5.1 / config_version 0x0001",
        "confidence": "high" if matches >= 3 else "layout-and-crc-only",
        "string_markers": strings,
    }


def decode(data: bytes, source_name: str, *, full_cogging_map: bool) -> dict[str, Any]:
    snapshots = find_snapshots(data)
    selected = select_active_snapshot(snapshots)

    block = data[selected.file_offset : selected.file_offset + CONFIG_STORED_SIZE]
    payload = block[:CONFIG_PAYLOAD_SIZE]
    parsed, layout_meta = parse_serialized_payload(payload)

    board = struct_to_dict(parsed["board"], full_cogging_map=full_cogging_map)
    can = struct_to_dict(parsed["can"], full_cogging_map=full_cogging_map)
    can["protocol"] = with_enum(int(parsed["can"].protocol), CAN_PROTOCOLS)

    history = [
        {
            "sector_offset": f"0x{s.sector_offset:06x}",
            "sector_number": s.sector_number,
            "start_field": s.start_field,
            "field_count": s.field_count,
            "file_offset": f"0x{s.file_offset:06x}",
            "active_marker": s.active_marker,
            "crc_valid": s.crc_valid,
            "stored_crc": f"0x{s.stored_crc:04x}",
            "calculated_crc": f"0x{s.calculated_crc:04x}",
        }
        for s in snapshots
    ]

    return {
        "_metadata": {
            "source_file": source_name,
            "source_size_bytes": len(data),
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "decoder_profile": "odrive-v36-fw-v0.5.1-fixed-layout",
            "firmware_fingerprint": firmware_fingerprint(data),
            "selected_nvm": {
                "sector_offset": f"0x{selected.sector_offset:06x}",
                "sector_number": selected.sector_number,
                "snapshot_file_offset": f"0x{selected.file_offset:06x}",
                "start_field": selected.start_field,
                "field_count": selected.field_count,
                "stored_block_size": CONFIG_STORED_SIZE,
                "config_payload_size": CONFIG_PAYLOAD_SIZE,
                "stored_crc": f"0x{selected.stored_crc:04x}",
                "calculated_crc": f"0x{selected.calculated_crc:04x}",
                "crc_valid": selected.crc_valid,
                "padding_hex": selected.padding_hex,
            },
            "nvm_history": history,
            "float_special_values": "NaN/Infinity are represented as JSON strings.",
            "anticogging_map_encoding": (
                "full array" if full_cogging_map else "lossless sparse array"
            ),
            "internal_pointer_note": (
                "Fields under _internal are persisted 32-bit runtime pointers from the "
                "firmware object layout; they are not user configuration values."
            ),
            "serialized_layout": layout_meta,
        },
        "board": board,
        "can": can,
        "axis0": axis_to_dict(0, parsed, full_cogging_map=full_cogging_map),
        "axis1": axis_to_dict(1, parsed, full_cogging_map=full_cogging_map),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decode ODrive v3.6 fw-v0.5.1 configuration from a flash .bin"
    )
    parser.add_argument("input", type=Path, help="input .bin file")
    parser.add_argument("-o", "--output", type=Path, help="output JSON path")
    parser.add_argument(
        "--full-cogging-map",
        action="store_true",
        help="write all 3600 anticogging values per axis instead of sparse encoding",
    )
    args = parser.parse_args(argv)

    try:
        data = args.input.read_bytes()
        result = decode(
            data,
            args.input.name,
            full_cogging_map=args.full_cogging_map,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output = args.output or args.input.with_suffix(".json")
    try:
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"error writing {output}: {exc}", file=sys.stderr)
        return 2

    selected = result["_metadata"]["selected_nvm"]
    print(f"Decoded: {args.input}")
    print(f"JSON:    {output}")
    print(
        "NVM:     sector={} snapshot={} CRC={}".format(
            selected["sector_number"],
            selected["snapshot_file_offset"],
            "OK" if selected["crc_valid"] else "FAILED",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
