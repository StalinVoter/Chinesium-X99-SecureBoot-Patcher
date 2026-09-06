from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import uuid

@dataclass(frozen=True)
class FfsFile:
    offset: int
    size: int
    header_size: int
    guid: str
    ffs_type: int
    attributes: int
    state: int
    data: bytes

    @property
    def sha256(self) -> str:
        return sha256(self.data).hexdigest()

@dataclass(frozen=True)
class FirmwareVolume:
    offset: int
    size: int
    header_length: int

    @property
    def end(self) -> int:
        return self.offset + self.size


def guid_bytes_le(text: str) -> bytes:
    return uuid.UUID(text).bytes_le


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def parse_ffs_at(buf: bytes, offset: int, expected_guid: str | None = None) -> FfsFile:
    if offset < 0 or offset + 24 > len(buf):
        raise ValueError('truncated FFS header')
    guid = str(uuid.UUID(bytes_le=bytes(buf[offset:offset + 16]))).upper()
    if expected_guid and guid != expected_guid.upper():
        raise ValueError(f'FFS GUID mismatch: expected {expected_guid}, got {guid}')
    ffs_type = buf[offset + 0x12]
    attrs = buf[offset + 0x13]
    size24 = int.from_bytes(buf[offset + 0x14:offset + 0x17], 'little')
    state = buf[offset + 0x17]
    size = size24
    header_size = 24
    # PI FFS3 large-file header: FFS_ATTRIB_LARGE_FILE bit + 0xFFFFFF size.
    if (attrs & 0x01) and size24 == 0xFFFFFF:
        if offset + 32 > len(buf):
            raise ValueError('truncated extended FFS header')
        size = int.from_bytes(buf[offset + 24:offset + 32], 'little')
        header_size = 32
    if size < header_size or size > 64 * 1024 * 1024 or offset + size > len(buf):
        raise ValueError(f'implausible FFS size 0x{size:X}')
    return FfsFile(offset, size, header_size, guid, ffs_type, attrs, state, buf[offset:offset + size])


def find_ffs_by_guid(buf: bytes, guid: str) -> list[FfsFile]:
    pattern = guid_bytes_le(guid)
    result: list[FfsFile] = []
    start = 0
    while True:
        pos = buf.find(pattern, start)
        if pos < 0:
            break
        try:
            item = parse_ffs_at(buf, pos, guid)
            # Avoid duplicate false-positive parses at the same offset.
            if not result or result[-1].offset != item.offset:
                result.append(item)
        except ValueError:
            pass
        start = pos + 1
    return result


def find_enclosing_fv(buf: bytes, target_offset: int) -> FirmwareVolume | None:
    """Return the outermost structurally-valid FV containing target_offset.

    UEFIReplace is allowed to rebuild padding/free-space *inside* the containing
    firmware volume. It must not alter bytes outside the outermost containing FV.
    The standard EFI_FIRMWARE_VOLUME_HEADER has FvLength at +0x20, signature
    '_FVH' at +0x28 and HeaderLength at +0x30.
    """
    candidates: list[FirmwareVolume] = []
    search = 0
    while True:
        sig = buf.find(b'_FVH', search)
        if sig < 0:
            break
        start = sig - 0x28
        search = sig + 1
        if start < 0 or start + 0x38 > len(buf):
            continue
        size = int.from_bytes(buf[start + 0x20:start + 0x28], 'little')
        header_len = int.from_bytes(buf[start + 0x30:start + 0x32], 'little')
        if size < 0x38 or header_len < 0x38 or header_len > size:
            continue
        end = start + size
        if end > len(buf):
            continue
        if start <= target_offset < end:
            candidates.append(FirmwareVolume(start, size, header_len))
    if not candidates:
        return None
    # Outermost FV gives nested-volume rebuilds room while still enforcing a
    # strong mutation boundary around the firmware region UEFIReplace touched.
    return max(candidates, key=lambda fv: fv.size)
