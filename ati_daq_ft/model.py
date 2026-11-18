"""Rotate a wrench and shift its torque reference point."""

import math


def transform_wrench(wrench, rotation, origin):
    """Rotate sensor axes; origin is sensor origin measured from output origin.

    F_out = R F_sensor; torque_out = R torque_sensor + origin × F_out.
    """
    if len(rotation) != 4 or len(origin) != 3 or len(wrench) != 6:
        raise ValueError("Expected quaternion, translation, and six-axis wrench")
    if not all(math.isfinite(float(x)) for x in [*rotation, *origin, *wrench]):
        raise ValueError("Nonfinite wrench mapping")
    x, y, z, w = map(float, rotation)
    if abs(x * x + y * y + z * z + w * w - 1) > 1e-6:
        raise ValueError("Mount quaternion must have unit norm")
    R = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    force = [sum(row[j] * wrench[j] for j in range(3)) for row in R]
    torque = [sum(row[j] * wrench[j + 3] for j in range(3)) for row in R]
    a, b, c = origin
    fx, fy, fz = force
    shift = [b * fz - c * fy, c * fx - a * fz, a * fy - b * fx]
    return force + [t + s for t, s in zip(torque, shift)]
