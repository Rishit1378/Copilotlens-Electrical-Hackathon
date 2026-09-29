import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "mcp_server"))
from analyzers.clogic_session_analyzer import CLogicSessionAnalyzer


SAMPLE_XML = """<project>
  <projectnamemgr><defaultname typename="DEVICE" defaultprefix="DEV" /></projectnamemgr>
  <logicaldesign name="Design1"><connectivity>
    <device id="dev-1" name="DEV1" partnumber="P-1">
      <pin id="dp-1" name="P1" pintype="NC" />
      <deviceconnector id="dc-1" name="J1">
        <pin id="cp-1" name="1" pintype="U" />
        <dcpinmap dcpin="cp-1" devpin="dp-1" />
        <backshell id="bs-1" name="BS1"><termination id="term-1" name="BK1" /></backshell>
      </deviceconnector>
    </device>
  </connectivity></logicaldesign>
</project>"""


class CLogicSessionAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.analyzer = CLogicSessionAnalyzer(self.temp.name)

    def tearDown(self):
        self.analyzer.stop_monitoring()
        self.temp.cleanup()

    def test_extracts_design_objects_not_project_type_metadata(self):
        import xml.etree.ElementTree as ET

        result = self.analyzer._extract_placed_objects(ET.fromstring(SAMPLE_XML))
        self.assertEqual(result["summary"]["devices"], 1)
        self.assertEqual(result["summary"]["device_connectors"], 1)
        self.assertEqual(result["summary"]["pins"], 2)
        self.assertEqual(result["summary"]["backshells"], 1)
        self.assertEqual(result["summary"]["terminations"], 1)
        self.assertEqual(len(result["pin_mappings"]), 1)

    def test_suggestions_advance_from_device_to_connectivity(self):
        analyzed = self.analyzer._analyze_snapshot(SAMPLE_XML, "sample.xml")
        self.assertIn("wire/conductor", analyzed["recommended_next_steps"][0].lower())
        self.assertTrue(analyzed["bug_reproduction_procedure"])

    def test_poller_reports_added_objects_and_log_activity(self):
        workspace = Path(self.temp.name) / "workspace"
        workspace.mkdir()
        self.analyzer._monitor_target = workspace
        snapshot = workspace / "design.xml"
        snapshot.write_text(SAMPLE_XML, encoding="utf-8")
        self.analyzer._poll_once()
        snapshot.write_text(SAMPLE_XML.replace("</connectivity>", '<wireconductor id="w-1" name="W1" /></connectivity>'), encoding="utf-8")
        log = workspace / "cmanager.log"
        log.write_text("Wire routed between J1 and J2\n", encoding="utf-8")
        self.analyzer._poll_once()
        events = list(self.analyzer._events)
        self.assertTrue(any(event["type"] == "object_added" and "W1" in event["message"] for event in events))
        self.assertTrue(any(event["type"] == "wire_activity" for event in events))

    def test_bad_input_returns_actionable_error(self):
        result = self.analyzer.inspect_live_session("C:\\missing\\design.xml")
        self.assertTrue(result["error"])
        self.assertIn("Could not read", result["reason"])


if __name__ == "__main__":
    unittest.main()

