import csv

from core.hardware.interface import TelemetrySample
from core.telemetry.csv_logger import COLUMNS, CsvLogger


def test_csv_file_shape_columns_and_rows(tmp_path):
    logger = CsvLogger(mode="velocity", hardware_source="sim", logs_dir=tmp_path)
    path = logger.open()
    assert path.exists()
    assert path.name.startswith("telemetry_")
    assert path.name.endswith("_velocity_sim.csv")

    samples = [
        TelemetrySample(t=0.0, position=0.0, velocity=0.0, current_iq=0.0, torque_est=0.0),
        TelemetrySample(t=0.02, position=0.001, velocity=0.05, current_iq=0.1, torque_est=0.006),
        TelemetrySample(t=0.04, position=0.003, velocity=0.10, current_iq=0.2, torque_est=0.012),
    ]
    for s in samples:
        logger.log_sample(s, mode="velocity", target=0.5)
    logger.close()

    with open(path, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    assert rows[0] == COLUMNS
    assert len(rows) == 1 + len(samples)  # header + one row per sample

    data_row = rows[1]
    assert data_row[2] == "velocity"  # mode
    assert data_row[3] == "0.5"  # target
    assert float(data_row[4]) == samples[0].position
    assert float(data_row[5]) == samples[0].velocity
    assert float(data_row[6]) == samples[0].current_iq
    assert float(data_row[7]) == samples[0].torque_est


def test_logs_dir_created_and_named_with_mode_and_source(tmp_path):
    logs_dir = tmp_path / "nested" / "logs"
    logger = CsvLogger(mode="torque", hardware_source="real", logs_dir=logs_dir)
    path = logger.open()
    assert logs_dir.exists()
    assert "_torque_real.csv" in path.name
    logger.close()


def test_experiment_columns_empty_for_non_experiment_runs(tmp_path):
    logger = CsvLogger(mode="velocity", hardware_source="sim", logs_dir=tmp_path)
    path = logger.open()
    logger.log_sample(TelemetrySample(t=0.0, position=0.0, velocity=0.0, current_iq=0.0, torque_est=0.0), mode="velocity", target=0.5)
    logger.close()

    with open(path, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    for col in ("experiment_state", "position_m", "velocity_m_s", "commanded_torque_nm", "bus_voltage_v", "estimated_power_w", "target_position_m"):
        assert rows[1][COLUMNS.index(col)] == ""


def test_experiment_columns_populated_when_passed(tmp_path):
    logger = CsvLogger(mode="experiment-static_hold", hardware_source="real", logs_dir=tmp_path)
    path = logger.open()
    logger.log_sample(
        TelemetrySample(t=0.0, position=0.0, velocity=0.0, current_iq=0.0, torque_est=0.0, bus_voltage_v=24.0),
        mode="experiment-static_hold",
        target=1.0,
        experiment_state="holding",
        position_m=0.5,
        velocity_m_s=0.01,
        commanded_torque_nm=0.2,
        bus_voltage_v=24.0,
        estimated_power_w=0.0126,
        target_position_m=1.0,
    )
    logger.close()

    with open(path, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    row = rows[1]
    assert row[COLUMNS.index("experiment_state")] == "holding"
    assert row[COLUMNS.index("position_m")] == "0.5"
    assert row[COLUMNS.index("target_position_m")] == "1.0"
