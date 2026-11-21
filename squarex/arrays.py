"""numpy arrays arrive msgpack-numpy encoded as {nd, type, shape, data}; turn them into plain lists."""
import struct

FORMATS = {"<f4": "f", "<f8": "d"}


def to_list(value) -> list:
    if not isinstance(value, dict):
        return value
    field = lambda name: value.get(name, value.get(name.encode()))
    dtype = field("type")
    code = FORMATS[dtype.decode() if isinstance(dtype, bytes) else dtype]
    data, shape = field("data"), list(field("shape"))
    flat = list(struct.unpack(f"<{len(data) // struct.calcsize(code)}{code}", data))
    if len(shape) == 2:
        return [flat[row * shape[1]:(row + 1) * shape[1]] for row in range(shape[0])]
    return flat
