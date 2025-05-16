import os
import sys
import unittest
from unittest import mock
from pathlib import Path

__module_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, __module_dir)
import base
from build_migrator.parsers.qmake import QmakeLogParser

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
TEST_FILES_DIR = os.path.join(SCRIPT_DIR, "files", "test_qmake_log_parser")

class TestQmakeLogParser(base.TestBase):
    def setUp(self):
        self.context = mock.Mock()
        self.context.source_dir = "/project/src"
        self.context.build_dirs = ["/project/build"]
        self.context.working_dir = "/project/build"
        def normalize_path(path, working_dir=None, ignore_working_dir=False):
            if not ignore_working_dir:
                full_path = os.path.join(working_dir or self.context.working_dir, path)
            else:
                full_path = path
            if full_path.startswith(self.context.source_dir):
                return full_path.replace(self.context.source_dir, "@source_dir@")
            if full_path.startswith(self.context.build_dirs[0]):
                return full_path.replace(self.context.build_dirs[0], "@build_dir@")
            return full_path
        self.context.normalize_path.side_effect = normalize_path
        self.context.build_object_model = []
        self.parser = QmakeLogParser(self.context)
        Path(TEST_FILES_DIR).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.parser.processed_lines.clear()

    def test_is_applicable(self):
        self.assertTrue(QmakeLogParser.is_applicable(log_type="qmake"))
        self.assertFalse(QmakeLogParser.is_applicable(log_type="ninja"))
        self.assertFalse(QmakeLogParser.is_applicable(log_type=None))

    def test_parse_empty_line(self):
        target = {"line": ""}
        result = self.parser.parse(target)
        self.assertEqual(result, self.parser.build_object_model)
        self.assertEqual(target["line"], "")
        self.assertEqual(len(self.parser.build_object_model), 0)

    def test_parse_sources(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:10: SOURCES := main.cpp utils.cpp"}
        with mock.patch.object(self.parser, "_read_file_content", return_value=b"// Content"):
            result = self.parser.parse(target)
        self.assertEqual(target["line"], "")
        self.assertEqual(len(self.parser.processed_sources), 2)
        self.assertIn("@source_dir@/main.cpp", self.parser.processed_sources)
        self.assertIn("@source_dir@/utils.cpp", self.parser.processed_sources)
        self.assertEqual(len(self.parser.build_object_model), 2)
        self.assertEqual(self.parser.build_object_model[0], {
            "content": b"// Content",
            "output": "@source_dir@/main.cpp",
            "dependencies": [],
            "type": "file"
        })
        self.assertEqual(self.parser.global_config["sources"], {"@source_dir@/main.cpp", "@source_dir@/utils.cpp"})

    def test_parse_headers_with_qobject(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:11: HEADERS := main.h"}
        with mock.patch.object(self.parser, "_read_file_content", return_value=b"#include <QObject>\nclass Test : public QObject { Q_OBJECT };"):
            result = self.parser.parse(target)
        self.assertTrue(self.parser.is_qt_project)
        self.assertEqual(len(self.parser.build_object_model), 1)
        self.assertEqual(self.parser.build_object_model[0], {
            "content": b"#include <QObject>\nclass Test : public QObject { Q_OBJECT };",
            "output": "@source_dir@/main.h",
            "dependencies": [],
            "type": "file"
        })
        self.assertEqual(self.parser.global_config["sources"], {"@build_dir@/moc/moc_main.cpp"})
        self.assertEqual(self.parser.moc_sources, {"@build_dir@/moc/moc_main.cpp"})

    def test_parse_forms(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:12: FORMS := dialog.ui"}
        with mock.patch.object(self.parser, "_read_file_content", return_value=b"<ui>...</ui>"):
            result = self.parser.parse(target)
        self.assertTrue(self.parser.is_qt_project)
        self.assertEqual(len(self.parser.build_object_model), 1)
        self.assertEqual(self.parser.build_object_model[0], {
            "content": b"<ui>...</ui>",
            "output": "@source_dir@/dialog.ui",
            "dependencies": [],
            "type": "file",
            "extension": ".ui"
        })
        self.assertEqual(self.parser.ui_headers, {"@build_dir@/uic/ui_dialog.h"})
        self.assertEqual(self.parser.global_config["forms"], {"@source_dir@/dialog.ui"})

    def test_parse_qt_modules(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:13: QT := core gui widgets"}
        result = self.parser.parse(target)
        self.assertTrue(self.parser.is_qt_project)
        self.assertEqual(self.parser.global_config["qt_modules"], {"core", "gui", "widgets"})
        self.assertEqual(self.parser.global_config["libs"], {
            "/usr/lib/x86_64-linux-gnu/libQt5Core.so",
            "/usr/lib/x86_64-linux-gnu/libQt5Gui.so",
            "/usr/lib/x86_64-linux-gnu/libQt5Widgets.so",
            "GL",
            "pthread"
        })
        self.assertEqual(self.parser.global_config["compile_flags"], {
            "-DQT_CORE_LIB",
            "-DQT_GUI_LIB",
            "-DQT_WIDGETS_LIB"
        })

    def test_parse_custom_compiler(self):
        lines = [
            {"line": "DEBUG 1: /project/src/test.pro:14: QMAKE_EXTRA_COMPILERS := mycompiler"},
            {"line": "DEBUG 1: /project/src/test.pro:15: mycompiler.input := input.txt"},
            {"line": "DEBUG 1: /project/src/test.pro:16: mycompiler.output := output.o"},
            {"line": "DEBUG 1: /project/src/test.pro:17: mycompiler.commands := gcc -c input.txt -o output.o"},
            {"line": "", "eof": True}
        ]
        for target in lines:
            self.parser.parse(target)
        self.assertEqual(len(self.parser.build_object_model), 2)
        custom_command = next(item for item in self.parser.build_object_model if item["type"] == "custom_command")
        self.assertEqual(custom_command["command"], "gcc -c input.txt -o output.o")
        self.assertEqual(custom_command["output"], "@build_dir@/output.o")
        self.assertEqual(custom_command["dependencies"], ["@source_dir@/input.txt"])

    def test_eof_with_target(self):
        self.parser.global_config["target"] = "test_app"
        self.parser.global_config["sources"] = {"@source_dir@/main.cpp"}
        self.parser.global_config["headers"] = {"@source_dir@/main.h"}
        self.parser.global_config["destdir"] = "@build_dir@/_build"
        self.parser.global_config["type"] = "executable"
        self.parser.global_config["compile_flags"] = {"-std=c++17"}
        target = {"eof": True}
        with mock.patch.object(self.parser, "_get_include_dirs", return_value=["@source_dir@/include"]):
            result = self.parser.parse(target)
        self.assertEqual(len(self.parser.build_object_model), 2)
        module = next(item for item in self.parser.build_object_model if item["type"] == "module")
        self.assertEqual(module["output"], "@build_dir@/_build/test_app")
        self.assertEqual(module["module_type"], "executable")
        self.assertEqual(module["sources"], [{
            "path": "@source_dir@/main.cpp",
            "dependencies": [],
            "compile_flags": ["-std=c++17"],
            "language": "C++",
            "include_dirs": ["@source_dir@/include"]
        }])
        self.assertEqual(self.context.build_object_model, self.parser.build_object_model)

    def test_duplicate_line(self):
        target1 = {"line": "DEBUG 1: /project/src/test.pro:10: SOURCES := main.cpp"}
        target2 = {"line": "DEBUG 1: /project/src/test.pro:10: SOURCES := main.cpp"}
        with mock.patch.object(self.parser, "_read_file_content", return_value=b"// Content"):
            self.parser.parse(target1)
            result = self.parser.parse(target2)
        self.assertEqual(len(self.parser.build_object_model), 1)
        self.assertEqual(self.parser.processed_sources, {"@source_dir@/main.cpp"})

    def test_invalid_form(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:12: FORMS := dialog.txt"}
        result = self.parser.parse(target)
        self.assertEqual(len(self.parser.build_object_model), 0)
        self.assertEqual(self.parser.global_config["forms"], set())

    def test_missing_target(self):
        self.parser.global_config["sources"] = {"@source_dir@/main.cpp"}
        target = {"eof": True}
        with mock.patch("logging.Logger.warning") as mock_warning:
            result = self.parser.parse(target)
        mock_warning.assert_called_with("Skipped final target: TARGET not specified in log")
        self.assertEqual(len(self.parser.build_object_model), 1)

if __name__ == "__main__":
    unittest.main()
