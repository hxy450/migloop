import os
import tempfile
import unittest

from extract_session import _infer_visible_source_lines, _spec_kind


SOURCE = """public class Sample {
    int alpha = 1;
    int beta = 2;
}
"""


class SourceVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "Sample.java")
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write(SOURCE)

    def tearDown(self):
        self.tmp.cleanup()

    def test_workflow_analysis_documents_are_spec_lineage(self):
        self.assertEqual("analysis", _spec_kind(".migration/analysis/09-parser.md"))
        self.assertEqual("shared", _spec_kind(".migration/architecture.md"))
        self.assertIsNone(_spec_kind("README.md"))

    def test_full_cat_records_all_emitted_lines(self):
        events = _infer_visible_source_lines(
            "Bash",
            {"command": f'cd "{self.tmp.name}" && cat "Sample.java"'},
            SOURCE,
            self.tmp.name,
        )
        self.assertEqual(events[0]["intervals"], [(1, 4)])

    def test_pipeline_records_only_final_matching_line(self):
        events = _infer_visible_source_lines(
            "Bash",
            {"command": f'cd "{self.tmp.name}" && cat "Sample.java" | grep beta'},
            "    int beta = 2;\n",
            self.tmp.name,
        )
        self.assertEqual(events[0]["intervals"], [(3, 1)])

    def test_grep_line_number_records_exact_line(self):
        events = _infer_visible_source_lines(
            "Grep",
            {"path": self.path, "pattern": "alpha", "output_mode": "content", "-n": True},
            "2:    int alpha = 1;",
            self.tmp.name,
        )
        self.assertEqual(events[0]["intervals"], [(2, 1)])

    def test_multi_file_grep_uses_section_header(self):
        other = os.path.join(self.tmp.name, "Other.java")
        with open(other, "w", encoding="utf-8") as stream:
            stream.write("class Other {\n    int gamma = 3;\n}\n")
        command = (
            f'cd "{self.tmp.name}" && grep -n alpha "Sample.java"; '
            'echo "=== Other.java ==="; grep -n gamma "Other.java"'
        )
        output = (
            "=== Sample.java ===\n"
            "2:    int alpha = 1;\n"
            "=== Other.java ===\n"
            "2:    int gamma = 3;\n"
        )
        events = _infer_visible_source_lines(
            "Bash", {"command": command}, output, self.tmp.name
        )
        by_name = {os.path.basename(x["path"]): x["intervals"] for x in events}
        self.assertEqual(by_name["Sample.java"], [(2, 1)])
        self.assertEqual(by_name["Other.java"], [(2, 1)])

    def test_path_only_result_is_not_source_visibility(self):
        events = _infer_visible_source_lines(
            "Bash",
            {"command": f'cd "{self.tmp.name}" && test -f "Sample.java" && echo Sample.java'},
            "Sample.java\n",
            self.tmp.name,
        )
        self.assertEqual(events, [])

    def test_no_output_is_not_source_visibility(self):
        events = _infer_visible_source_lines(
            "Bash",
            {"command": f'cd "{self.tmp.name}" && cat "Sample.java" > copy.txt'},
            "",
            self.tmp.name,
        )
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
