"""Telemetry frame format shared by the MCU (simulated), the bridge and tests.

Payload, little-endian:
    u32 seq          frame counter, gaps mean lost frames
    u64 t_us         MCU sample time in microseconds
    9 x (f32 pos_rad, f32 vel_rad_s, f32 current_a)

On the wire: payload + CRC-16/CCITT-FALSE, COBS-encoded, terminated by 0x00.
"""
import binascii
import struct

JOINTS = ["L hip roll", "L hip pitch", "L knee", "L ankle",
          "R hip roll", "R hip pitch", "R knee", "R ankle", "head pan"]
HEADER = struct.Struct("<IQ")
JOINT = struct.Struct("<fff")
PAYLOAD_SIZE = HEADER.size + JOINT.size * len(JOINTS)  # 120 bytes
WIRE_SIZE = PAYLOAD_SIZE + 2 + 2  # + CRC, + COBS code byte and delimiter


def pack(seq, t_us, joints):
    out = bytearray(HEADER.pack(seq, t_us))
    for pos, vel, cur in joints:
        out += JOINT.pack(pos, vel, cur)
    return bytes(out)


def unpack(payload):
    seq, t_us = HEADER.unpack_from(payload)
    joints = [JOINT.unpack_from(payload, HEADER.size + i * JOINT.size) for i in range(len(JOINTS))]
    return seq, t_us, joints


def cobs_encode(data):
    out = bytearray()
    for chunk in data.split(b"\0"):
        while len(chunk) >= 254:
            out.append(255)
            out += chunk[:254]
            chunk = chunk[254:]
        out.append(len(chunk) + 1)
        out += chunk
    return bytes(out)


def cobs_decode(data):
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        end = i + code
        if code == 0 or end > len(data):
            raise ValueError("bad COBS")
        out += data[i + 1:end]
        i = end
        if code < 255 and i < len(data):
            out.append(0)
    return bytes(out)


def encode(payload):
    crc = binascii.crc_hqx(payload, 0xFFFF)
    return cobs_encode(payload + struct.pack("<H", crc)) + b"\0"


def decode(chunk):
    """Decode one COBS chunk (delimiter removed). Returns payload or raises ValueError."""
    raw = cobs_decode(chunk)
    if len(raw) != PAYLOAD_SIZE + 2:
        raise ValueError("bad length")
    payload, (crc,) = raw[:-2], struct.unpack("<H", raw[-2:])
    if binascii.crc_hqx(payload, 0xFFFF) != crc:
        raise ValueError("bad CRC")
    return payload
