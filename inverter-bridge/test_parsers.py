"""
Unit tests for inverter_bridge parsers.

Tests follow Given-When-Then naming convention
(infosit.standards: Definition-of-Done 2.2).
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# Stub serial module so inverter_bridge can import without pyserial installed
import types
serial_stub = types.ModuleType("serial")
serial_stub.Serial = type("Serial", (), {})
serial_stub.SerialException = type("SerialException", (Exception,), {})
serial_stub.EIGHTBITS = 8
serial_stub.PARITY_NONE = "N"
serial_stub.STOPBITS_ONE = 1
sys.modules["serial"] = serial_stub

# Stub paho.mqtt.client
mqtt_stub = types.ModuleType("paho.mqtt.client")
mqtt_stub.Client = type("Client", (), {"__init__": lambda self, **kw: None})
sys.modules["paho"] = types.ModuleType("paho")
sys.modules["paho.mqtt"] = types.ModuleType("paho.mqtt")
sys.modules["paho.mqtt.client"] = mqtt_stub

import inverter_bridge as ib


class TestParseP17GS(unittest.TestCase):
    """Tests for _parse_p17_gs — P17 General Status parser."""

    SAMPLE_GS = (
        "3968,3285,0797,0585,0363,000,+00000,2410,,,4988,0000,,,"
        "2410,,,4999,,,,034,040,000,0"
    )

    def test_given_valid_gs_response_when_parsed_then_grid_voltage_correct(self):
        data = ib._parse_p17_gs(self.SAMPLE_GS)
        # f[7]=2410 / 10 = 241.0V
        self.assertAlmostEqual(data["grid_voltage"], 241.0, places=1)

    def test_given_valid_gs_response_when_parsed_then_grid_frequency_correct(self):
        data = ib._parse_p17_gs(self.SAMPLE_GS)
        # f[10]=4988 / 100 = 49.88Hz
        self.assertAlmostEqual(data["grid_frequency"], 49.88, places=2)

    def test_given_valid_gs_response_when_parsed_then_ac_output_voltage_correct(self):
        data = ib._parse_p17_gs(self.SAMPLE_GS)
        # f[14]=2410 / 10 = 241.0V
        self.assertAlmostEqual(data["ac_output_voltage"], 241.0, places=1)

    def test_given_valid_gs_response_when_parsed_then_ac_output_frequency_correct(self):
        data = ib._parse_p17_gs(self.SAMPLE_GS)
        # f[17]=4999 / 100 = 49.99Hz
        self.assertAlmostEqual(data["ac_output_frequency"], 49.99, places=2)

    def test_given_valid_gs_response_when_parsed_then_pv_voltage_is_max_of_both(self):
        data = ib._parse_p17_gs(self.SAMPLE_GS)
        # f[0]=3968/10=396.8, f[1]=3285/10=328.5 → max=396.8
        self.assertAlmostEqual(data["pv_input_voltage"], 396.8, places=1)

    def test_given_valid_gs_response_when_parsed_then_temperature_correct(self):
        data = ib._parse_p17_gs(self.SAMPLE_GS)
        self.assertEqual(data["inverter_heat_sink_temp"], 34)

    def test_given_low_battery_when_parsed_then_battery_voltage_is_zero(self):
        # f[4]=0200 → 20.0V < MIN_VALID_BATTERY_VOLTAGE (30V) → 0.0
        gs = "3968,3285,0797,0585,0200,000,+00000,2410,,,4988,0000,,,2410,,,4999,,,,034,040,000,0"
        data = ib._parse_p17_gs(gs)
        self.assertEqual(data["battery_voltage"], 0.0)

    def test_given_valid_battery_when_parsed_then_battery_voltage_correct(self):
        # f[4]=0540 → 54.0V > 30V → 54.0
        gs = "3968,3285,0797,0585,0540,080,+00000,2410,,,4988,0000,,,2410,,,4999,,,,034,040,000,0"
        data = ib._parse_p17_gs(gs)
        self.assertAlmostEqual(data["battery_voltage"], 54.0, places=1)

    def test_given_positive_charge_current_when_parsed_then_charging_on(self):
        gs = "3968,3285,0797,0585,0540,080,+00150,2410,,,4988,0000,,,2410,,,4999,,,,034,040,000,0"
        data = ib._parse_p17_gs(gs)
        self.assertEqual(data["charging_on"], 1)
        self.assertEqual(data["battery_charging_current"], 15)

    def test_given_negative_charge_current_when_parsed_then_discharging(self):
        gs = "3968,3285,0797,0585,0540,080,-00100,2410,,,4988,0000,,,2410,,,4999,,,,034,040,000,0"
        data = ib._parse_p17_gs(gs)
        self.assertEqual(data["charging_on"], 0)
        self.assertEqual(data["battery_discharge_current"], 10)

    def test_given_no_pv_when_parsed_then_scc_charging_off(self):
        gs = "0000,0000,0000,0000,0540,080,+00000,2410,,,4988,0000,,,2410,,,4999,,,,034,040,000,0"
        data = ib._parse_p17_gs(gs)
        self.assertEqual(data["scc_charging"], 0)

    def test_given_too_few_fields_when_parsed_then_returns_empty(self):
        data = ib._parse_p17_gs("1234,5678,0000")
        self.assertEqual(data, {})

    def test_given_empty_string_when_parsed_then_returns_empty(self):
        data = ib._parse_p17_gs("")
        self.assertEqual(data, {})


class TestParseP17PS(unittest.TestCase):
    """Tests for _parse_p17_ps — P17 Power Status parser."""

    SAMPLE_PS = "03095,01924,,,,,,0261,,,00261,0584,,,00584,011,1,1,1,0,2,2"

    def test_given_valid_ps_when_parsed_then_pv_power_is_sum(self):
        data = {}
        ib._parse_p17_ps(self.SAMPLE_PS, data)
        # 3095 + 1924 = 5019
        self.assertEqual(data["pv_input_power"], 5019)

    def test_given_valid_ps_when_parsed_then_active_power_correct(self):
        data = {}
        ib._parse_p17_ps(self.SAMPLE_PS, data)
        self.assertEqual(data["ac_output_active_power"], 261)

    def test_given_valid_ps_when_parsed_then_load_percent_correct(self):
        data = {}
        ib._parse_p17_ps(self.SAMPLE_PS, data)
        self.assertEqual(data["output_load_percent"], 11)

    def test_given_valid_ps_when_parsed_then_load_on_correct(self):
        data = {}
        ib._parse_p17_ps(self.SAMPLE_PS, data)
        self.assertEqual(data["load_on"], 1)

    def test_given_zero_power_when_parsed_then_values_zero(self):
        data = {}
        ib._parse_p17_ps("00000,00000,,,,,,0000,,,00000,0000,,,00000,000,0,0,0,0,0,0", data)
        self.assertEqual(data["pv_input_power"], 0)
        self.assertEqual(data["ac_output_active_power"], 0)
        self.assertEqual(data["output_load_percent"], 0)


class TestCRC(unittest.TestCase):
    """Tests for CRC16/XMODEM calculation."""

    def test_given_known_input_when_crc_calculated_then_matches_expected(self):
        # ^0 → CRC = 0x1BE3 (confirmed from inverter heartbeat)
        self.assertEqual(ib._crc16(b"^0"), 0x1BE3)

    def test_given_qpigs_when_crc_calculated_then_matches_expected(self):
        # QPIGS → CRC = 0xB7A9
        self.assertEqual(ib._crc16(b"QPIGS"), 0xB7A9)

    def test_given_crc_byte_needs_escape_when_escaped_then_incremented(self):
        # CRC bytes 0x0A, 0x0D, 0x28 must be incremented by 1
        crc_bytes = ib._crc_bytes(b"test_0x0d")
        for b in crc_bytes:
            self.assertNotIn(b, (0x0A, 0x0D, 0x28))


class TestBuildCommands(unittest.TestCase):
    """Tests for command builders."""

    def test_given_gs_command_when_built_for_hid_then_correct_format(self):
        # ^P003GS\r — len("GS")+1=3, no CRC
        pkt = ib.build_p18_hid_command("GS")
        self.assertEqual(pkt, b"^P003GS\r")

    def test_given_qpigs_when_built_for_hid_then_correct_length(self):
        pkt = ib.build_p18_hid_command("QPIGS")
        self.assertEqual(pkt, b"^P006QPIGS\r")

    def test_given_mod_when_built_for_hid_then_correct_format(self):
        pkt = ib.build_p18_hid_command("MOD")
        self.assertEqual(pkt, b"^P004MOD\r")

    def test_given_qpigs_when_built_for_serial_then_has_crc(self):
        pkt = ib.build_pi18_command("QPIGS")
        # ^P005QPIGS + 2 CRC bytes + \r = should NOT equal HID version
        self.assertTrue(pkt.startswith(b"^P005QPIGS"))
        self.assertTrue(pkt.endswith(b"\r"))
        self.assertEqual(len(pkt), len(b"^P005QPIGS") + 2 + 1)


class TestModeMap(unittest.TestCase):
    """Tests for P18 mode mapping."""

    def test_given_line_mode_code_when_mapped_then_returns_line(self):
        self.assertEqual(ib.P18_MODE_MAP["05"], "Line")

    def test_given_battery_mode_code_when_mapped_then_returns_battery(self):
        self.assertEqual(ib.P18_MODE_MAP["04"], "Battery")

    def test_given_fault_mode_code_when_mapped_then_returns_fault(self):
        self.assertEqual(ib.P18_MODE_MAP["06"], "Fault")


if __name__ == "__main__":
    unittest.main()
