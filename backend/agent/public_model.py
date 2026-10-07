"""Remove non-rendering extras from the served GLB; retain original on disk."""
import json
import struct
from functools import lru_cache


def strip_extras(value):
    if isinstance(value, dict):
        return {k: strip_extras(v) for k, v in value.items() if k != 'extras'}
    if isinstance(value, list):
        return [strip_extras(v) for v in value]
    return value


@lru_cache(maxsize=2)
def _public_glb(path, modified_ns, size):
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from('<4sII', raw)
    if magic != b'glTF' or version != 2 or length != len(raw):
        raise ValueError('Invalid GLB')
    offset = 12
    chunks = []
    while offset < len(raw):
        size, kind = struct.unpack_from('<II', raw, offset)
        chunk = raw[offset+8:offset+8+size]
        if kind == 0x4E4F534A:
            chunk = json.dumps(strip_extras(json.loads(chunk)), ensure_ascii=False, separators=(',', ':')).encode()
            chunk += b' ' * (-len(chunk) % 4)
        chunks.append(struct.pack('<II', len(chunk), kind)+chunk)
        offset += size+8
    body = b''.join(chunks)
    return struct.pack('<4sII', magic, version, 12+len(body))+body


def public_glb(path):
    stat = path.stat()
    return _public_glb(path, stat.st_mtime_ns, stat.st_size)
