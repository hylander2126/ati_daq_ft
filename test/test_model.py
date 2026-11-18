import math
import pytest
from ati_daq_ft.model import transform_wrench


def test_rotation_and_moment_shift():
    result = transform_wrench(
        [2, 0, 0, 0, 0, 0], [0, 0, math.sqrt(0.5), math.sqrt(0.5)], [0.1, 0, 0]
    )
    assert result == pytest.approx([0, 2, 0, 0, 0, 0.2])


@pytest.mark.parametrize(
    "rotation,origin", [([0, 0, 0, 2], [0, 0, 0]), ([0, 0, 0, 1], [float("nan"), 0, 0])]
)
def test_invalid_mapping(rotation, origin):
    with pytest.raises(ValueError):
        transform_wrench([0] * 6, rotation, origin)


def test_native_scan_layout_counts_and_input_limit_without_a_daq():
    import ctypes as C
    from ati_daq_ft.core import AnalogReader

    class Library:
        def DAQmxBaseReadAnalogF64(
            self, task, n, timeout, group, out, size, count, reserved
        ):
            assert group == 1  # NI GroupByScanNumber
            for i, v in enumerate(
                [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]
            ):
                out[i] = v
            C.cast(count, C.POINTER(C.c_int32))[0] = 2
            return 0

    reader = object.__new__(AnalogReader)
    reader.lib = Library()
    reader.task = C.c_void_p(1)
    reader.sample_rate = 500
    reader.block_size = 2
    assert reader.read_block() == [
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
        [1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7],
    ]
    original = reader.lib.DAQmxBaseReadAnalogF64

    def partial(*args):
        original(*args)
        C.cast(args[-2], C.POINTER(C.c_int32))[0] = 1
        return 0

    reader.lib.DAQmxBaseReadAnalogF64 = partial
    with pytest.raises(RuntimeError, match="Invalid acquisition"):
        reader.read_block()
