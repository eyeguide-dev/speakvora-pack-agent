import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import datetime as dt, unittest
from speakvora_pack_agent.connectors import gcal


def utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


class Zones(unittest.TestCase):
    def test_outlook_windows_zone_names_mean_the_right_time(self):
        for zone, want in (("Eastern Standard Time", "2026-10-22 06:10"), ("Pacific Standard Time", "2026-10-22 09:10"), ("GMT Standard Time", "2026-10-22 01:10"), ("India Standard Time", "2026-10-21 20:40")):
            e = gcal.parse_ics(f"BEGIN:VEVENT\nDTSTART;TZID={zone}:20261022T021000\nSUMMARY:x\nEND:VEVENT")[0]
            self.assertEqual(utc(e["start"]), want, zone)

    def test_a_time_with_no_zone_is_the_agents_own_local_time_not_utc(self):
        e = gcal.parse_ics("BEGIN:VEVENT\nDTSTART:20261022T021000\nSUMMARY:x\nEND:VEVENT", "America/New_York")[0]
        self.assertEqual(utc(e["start"]), "2026-10-22 06:10")

    def test_normal_names_and_utc_still_work(self):
        a = gcal.parse_ics("BEGIN:VEVENT\nDTSTART;TZID=America/Chicago:20261022T021000\nSUMMARY:x\nEND:VEVENT")[0]; b = gcal.parse_ics("BEGIN:VEVENT\nDTSTART:20261022T021000Z\nSUMMARY:x\nEND:VEVENT")[0]
        self.assertEqual(utc(a["start"]), "2026-10-22 07:10"); self.assertEqual(utc(b["start"]), "2026-10-22 02:10")


if __name__ == "__main__":
    unittest.main()
