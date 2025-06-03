import os
import sys
import unittest
from unittest import mock
from pathlib import Path

__module_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, __module_dir)
import base
from build_migrator.parsers.qmake import QmakeLogParser
from build_migrator.parsers.qmake_pro import QmakeProParser

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
TEST_FILES_DIR = os.path.join(SCRIPT_DIR, "files", "test_qmake_log_parser")

class TestQmakeParsers(base.TestBase):
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
        self.log_parser = QmakeLogParser(self.context)
        self.pro_parser = QmakeProParser(self.context)
        Path(TEST_FILES_DIR).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.log_parser.processed_lines.clear()
        self.pro_parser.get_file = False
        self.pro_parser.result = {
            "variables": {},
            "conditions": [],
            "includes": [],
            "errors": []
        }
        self.pro_parser.condition_stack = []
        self.pro_parser.variables = {}
        self.pro_parser.target = {}

    # QmakeLogParser Tests
    def test_is_applicable(self):
        self.assertTrue(QmakeLogParser.is_applicable(log_type="qmake"))
        self.assertFalse(QmakeLogParser.is_applicable(log_type="ninja"))
        self.assertFalse(QmakeLogParser.is_applicable(log_type=None))

    def test_parse_empty_line(self):
        target = {"line": ""}
        result = self.log_parser.parse(target)
        self.assertEqual(result, self.log_parser.build_object_model)
        self.assertEqual(target["line"], "")
        self.assertEqual(len(self.log_parser.build_object_model), 0)

    def test_parse_sources(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:10: SOURCES := main.cpp utils.cpp"}
        with mock.patch.object(self.log_parser, "_read_file_content", return_value=b"// Content"):
            result = self.log_parser.parse(target)
        self.assertEqual(target["line"], "")
        self.assertEqual(len(self.log_parser.processed_sources), 2)
        self.assertIn("@source_dir@/main.cpp", self.log_parser.processed_sources)
        self.assertIn("@source_dir@/utils.cpp", self.log_parser.processed_sources)
        self.assertEqual(len(self.log_parser.build_object_model), 2)
        self.assertEqual(self.log_parser.build_object_model[0], {
            "content": b"// Content",
            "output": "@source_dir@/main.cpp",
            "dependencies": [],
            "type": "file"
        })
        self.assertEqual(self.log_parser.global_config["sources"], {"@source_dir@/main.cpp", "@source_dir@/utils.cpp"})

    def test_parse_headers_with_qobject(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:11: HEADERS := main.h"}
        with mock.patch.object(self.log_parser, "_read_file_content", return_value=b"#include <QObject>\nclass Test : public QObject { Q_OBJECT };"):
            result = self.log_parser.parse(target)
        self.assertTrue(self.log_parser.is_qt_project)
        self.assertEqual(len(self.log_parser.build_object_model), 1)
        self.assertEqual(self.log_parser.build_object_model[0], {
            "content": b"#include <QObject>\nclass Test : public QObject { Q_OBJECT };",
            "output": "@source_dir@/main.h",
            "dependencies": [],
            "type": "file"
        })
        self.assertEqual(self.log_parser.global_config["sources"], {"@build_dir@/moc/moc_main.cpp"})
        self.assertEqual(self.log_parser.moc_sources, {"@build_dir@/moc/moc_main.cpp"})

    def test_parse_forms(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:12: FORMS := dialog.ui"}
        with mock.patch.object(self.log_parser, "_read_file_content", return_value=b"<ui>...</ui>"):
            result = self.log_parser.parse(target)
        self.assertTrue(self.log_parser.is_qt_project)
        self.assertEqual(len(self.log_parser.build_object_model), 1)
        self.assertEqual(self.log_parser.build_object_model[0], {
            "content": b"<ui>...</ui>",
            "output": "@source_dir@/dialog.ui",
            "dependencies": [],
            "type": "file",
            "extension": ".ui"
        })
        self.assertEqual(self.log_parser.ui_headers, {"@build_dir@/uic/ui_dialog.h"})
        self.assertEqual(self.log_parser.global_config["forms"], {"@source_dir@/dialog.ui"})

    def test_parse_qt_modules(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:13: QT := core gui widgets"}
        result = self.log_parser.parse(target)
        self.assertTrue(self.log_parser.is_qt_project)
        self.assertEqual(self.log_parser.global_config["qt_modules"], {"core", "gui", "widgets"})
        self.assertEqual(self.log_parser.global_config["libs"], {
            "/usr/lib/x86_64-linux-gnu/libQt5Core.so",
            "/usr/lib/x86_64-linux-gnu/libQt5Gui.so",
            "/usr/lib/x86_64-linux-gnu/libQt5Widgets.so",
            "GL",
            "pthread"
        })
        self.assertEqual(self.log_parser.global_config["compile_flags"], {
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
            self.log_parser.parse(target)
        self.assertEqual(len(self.log_parser.build_object_model), 1)
        custom_command = self.log_parser.build_object_model[0]
        self.assertEqual(custom_command["type"], "custom_commands")
        self.assertEqual(custom_command["command"], "gcc -c input.txt -o output.o")
        self.assertEqual(custom_command["output"], "@build_dir@/output.o")
        self.assertEqual(custom_command["dependencies"], ["@source_dir@/input.txt"])

    def test_eof_with_target(self):
        self.log_parser.global_config["target"] = "test_app"
        self.log_parser.global_config["sources"] = {"@source_dir@/main.cpp"}
        self.log_parser.global_config["headers"] = {"@source_dir@/main.h"}
        self.log_parser.global_config["destdir"] = "@build_dir@/_build"
        self.log_parser.global_config["type"] = "executable"
        self.log_parser.global_config["compile_flags"] = {"-std=c++17"}
        target = {"eof": True}
        with mock.patch.object(self.log_parser, "_get_include_dirs", return_value=["@source_dir@/include"]):
            result = self.log_parser.parse(target)
        self.assertEqual(len(self.log_parser.build_object_model), 1)
        module = self.log_parser.build_object_model[0]
        self.assertEqual(module["output"], "@build_dir@/_build/test_app")
        self.assertEqual(module["module_type"], "executable")
        self.assertEqual(module["sources"], [{
            "path": "@source_dir@/main.cpp",
            "dependencies": [],
            "compile_flags": ["-std=c++17"],
            "language": "C++",
            "include_dirs": ["@source_dir@/include"]
        }])
        self.assertEqual(self.context.build_object_model, self.log_parser.build_object_model)

    def test_duplicate_line(self):
        target1 = {"line": "DEBUG 1: /project/src/test.pro:10: SOURCES := main.cpp"}
        target2 = {"line": "DEBUG 1: /project/src/test.pro:10: SOURCES := main.cpp"}
        with mock.patch.object(self.log_parser, "_read_file_content", return_value=b"// Content"):
            self.log_parser.parse(target1)
            result = self.log_parser.parse(target2)
        self.assertEqual(len(self.log_parser.build_object_model), 1)
        self.assertEqual(self.log_parser.processed_sources, {"@source_dir@/main.cpp"})

    def test_invalid_form(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:12: FORMS := dialog.txt"}
        result = self.log_parser.parse(target)
        self.assertEqual(len(self.log_parser.build_object_model), 0)
        self.assertEqual(self.log_parser.global_config["forms"], set())

    def test_missing_target(self):
        self.log_parser.global_config["sources"] = {"@source_dir@/main.cpp"}
        target = {"eof": True}
        with mock.patch("logging.Logger.warning") as mock_warning:
            result = self.log_parser.parse(target)
        mock_warning.assert_called_with("Skipped final target: TARGET not specified in log")
        self.assertEqual(len(self.log_parser.build_object_model), 0)

    def test_parse_includepath(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:14: INCLUDEPATH := /usr/include /project/src/include"}
        result = self.log_parser.parse(target)
        self.assertEqual(self.log_parser.global_config["includes"], {"/usr/include", "@source_dir@/include"})
        self.assertEqual(target["line"], "")

    def test_parse_libs(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:15: LIBS := -lboost -L/usr/lib /custom/lib.so"}
        with mock.patch("os.path.isfile", return_value=True):
            result = self.log_parser.parse(target)
        self.assertEqual(self.log_parser.global_config["libs"], {"boost", "/custom/lib.so"})
        self.assertEqual(self.log_parser.global_config["includes"], {"/usr/lib"})
        self.assertEqual(target["line"], "")

    def test_parse_defines(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:16: DEFINES := MY_MACRO DEBUG"}
        result = self.log_parser.parse(target)
        self.assertEqual(self.log_parser.global_config["compile_flags"], {"-DMY_MACRO", "-DDEBUG"})
        self.assertEqual(target["line"], "")

    def test_parse_config(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:17: CONFIG := qt c++17 warn_on"}
        result = self.log_parser.parse(target)
        self.assertTrue(self.log_parser.is_qt_project)
        self.assertEqual(self.log_parser.global_config["config"], {"qt", "c++17", "warn_on"})
        self.assertEqual(self.log_parser.global_config["compile_flags"], {
            "-D_REENTRANT", "-DQT_CORE_LIB", "-DQT_GUI_LIB", "-DQT_NO_DEBUG", "-std=gnu++1z", "-Wall", "-Wextra"
        })
        self.assertEqual(self.log_parser.global_config["libs"], {
            "/usr/lib/x86_64-linux-gnu/libQt5Core.so", "/usr/lib/x86_64-linux-gnu/libQt5Gui.so", "GL", "pthread"
        })

    def test_parse_subdirs(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:18: SUBDIRS := sub1 sub2"}
        result = self.log_parser.parse(target)
        self.assertEqual(self.log_parser.global_config["subdirs"], {"@source_dir@/sub1", "@source_dir@/sub2"})
        target = {"eof": True}
        result = self.log_parser.parse(target)
        self.assertEqual(len(self.log_parser.build_object_model), 2)
        outputs = [proj["output"] for proj in self.log_parser.build_object_model]
        self.assertIn("@source_dir@/sub1", outputs)
        self.assertIn("@source_dir@/sub2", outputs)

    def test_parse_precompiled_header(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:19: PRECOMPILED_HEADER := common.h"}
        result = self.log_parser.parse(target)
        self.assertEqual(self.log_parser.global_config["precompiled_header"], "@source_dir@/common.h")
        self.assertEqual(self.log_parser.global_config["headers"], {"@source_dir@/common.h"})

    def test_parse_rc_file(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:20: RC_FILE := app.rc"}
        with mock.patch.object(self.log_parser, "_read_file_content", return_value=b"RC_CONTENT"):
            result = self.log_parser.parse(target)
        self.assertEqual(self.log_parser.global_config["sources"], {"@source_dir@/app.rc"})
        self.assertEqual(len(self.log_parser.build_object_model), 1)
        self.assertEqual(self.log_parser.build_object_model[0], {
            "content": b"RC_CONTENT",
            "output": "@source_dir@/app.rc",
            "dependencies": [],
            "type": "file",
            "extension": ".rc"
        })

    def test_parse_installs(self):
        lines = [
            {"line": "DEBUG 1: /project/src/test.pro:21: INSTALLS := binfile"},
            {"line": "DEBUG 1: /project/src/test.pro:22: binfile.files := sasm Linux/bin/*"},
            {"line": "DEBUG 1: /project/src/test.pro:23: binfile.path := /usr/bin"},
            {"line": "", "eof": True}
        ]
        for target in lines:
            self.log_parser.parse(target)
        self.assertEqual(len(self.log_parser.build_object_model), 1)
        install = self.log_parser.build_object_model[0]
        self.assertEqual(install["type"], "installs")
        self.assertEqual(install["output"], "/usr/bin")
        self.assertEqual(install["dependencies"], ["@source_dir@/sasm", "@source_dir@/Linux/bin/*"])

    def test_parse_conditions(self):
        target = {
            "eof": True,
            "line": "DEBUG 1: /project/src/test.pro:24: LIBS := -luser32",
            "conditions": [{"condition": ["win32"], "variables": {"libs": ["-luser32"]}, "conditions": [],}]
        }
        self.log_parser.global_config["target"] = "project_name"
        with mock.patch("os.path.isfile", return_value=True):
            result = self.log_parser.parse(target)
        self.assertEqual(self.log_parser.global_config["libs"], {"user32"})
        self.assertEqual(len(self.log_parser.build_object_model), 1)
        condition = self.log_parser.build_object_model[0]
        self.assertEqual(condition["type"], "conditions")
        self.assertEqual(condition["conditions"], [{"condition": ["win32"], "variables": {"libs": ["-luser32"]}, 'conditions': []}])

    def test_parse_invalid_line(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:25: INVALID := value"}
        result = self.log_parser.parse(target)
        self.assertEqual(len(self.log_parser.build_object_model), 0)

    def test_read_file_content_ioerror(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:10: SOURCES := main.cpp"}
        with mock.patch("builtins.open", side_effect=IOError("File not found")):
            with mock.patch("logging.Logger.warning") as mock_warning:
                result = self.log_parser.parse(target)
        mock_warning.assert_called_with("Cannot read file @source_dir@/main.cpp: File not found")
        self.assertEqual(len(self.log_parser.build_object_model), 0)

    # QmakeProParser Tests
    def test_pro_is_applicable(self):
        self.assertTrue(QmakeProParser.is_applicable(log_type="qmake"))
        self.assertFalse(QmakeProParser.is_applicable(log_type="cmake"))
        self.assertFalse(QmakeProParser.is_applicable(log_type=None))

    def test_pro_parse_empty_target(self):
        target = {"line": ""}
        result = self.pro_parser.parse(target)
        self.assertEqual(result, [])
        self.assertEqual(self.pro_parser.result["variables"], {})
        self.assertEqual(self.pro_parser.result["conditions"], [])

    def test_pro_parse_assignment(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:1: SOURCES = main.cpp utils.cpp"}
        with mock.patch("builtins.open", mock.mock_open(read_data="SOURCES = main.cpp utils.cpp")):
            result = self.pro_parser.parse(target)
        self.assertEqual(self.pro_parser.result["variables"], {"sources": ["main.cpp", "utils.cpp"]})
        self.assertEqual(result["conditions"], [])

    def test_pro_parse_plus_equals(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:1: binfile.files += sasm\nbinfile.files += Linux/bin/*"}
        with mock.patch("builtins.open", mock.mock_open(read_data="binfile.files += sasm\nbinfile.files += Linux/bin/*")):
            result = self.pro_parser.parse(target)
        self.assertEqual(self.pro_parser.result["variables"], {"binfile.files": ["sasm", "Linux/bin/*"]})
        self.assertEqual(result["conditions"], [])

    def test_pro_parse_condition(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:1: QT := core"}
        with mock.patch("builtins.open", mock.mock_open(read_data="win32 { \nLIBS += -luser32 \n}")):
            result = self.pro_parser.parse(target)
        self.assertEqual(self.pro_parser.result["conditions"], [{
            "condition": ["win32"],
            "variables": {"libs": ["-luser32"]},
            "conditions": []
        }])
        self.assertEqual(self.pro_parser.variables["libs"], ["-luser32"])

    def test_pro_parse_else(self):
        target = {
            "line": "DEBUG 1: /project/src/test.pro:1: QT := core"
        }
        pro_file_content = """
        unix { 
        LIBS += -lX11 
        }
        else { 
        LIBS += -luser32 
        }
        """
        with mock.patch("builtins.open", mock.mock_open(read_data=pro_file_content)):
            result = self.pro_parser.parse(target)
        self.assertEqual(len(self.pro_parser.result["conditions"]), 2)
        self.assertEqual(self.pro_parser.result["conditions"][0], {
            "condition": ["unix"],
            "variables": {"libs": ["-lX11"]},
            "conditions": []
        })
        self.assertEqual(self.pro_parser.result["conditions"][1], {
            "condition": ["else"],
            "variables": {"libs": ["-luser32"]},
            "conditions": []
        })

    def test_pro_parse_variable_substitution(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:1: MY_PATH = /usr\nSOURCES = $$MY_PATH/main.cpp"}
        with mock.patch("builtins.open", mock.mock_open(read_data="MY_PATH = /usr\nSOURCES = $$MY_PATH/main.cpp")):
            result = self.pro_parser.parse(target)
        self.assertEqual(self.pro_parser.result["variables"], {
            "my_path": ["/usr"],
            "sources": ["/usr/main.cpp"]
        })

    def test_pro_parse_inline_condition(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:1: win32:LIBS += -luser32"}
        with mock.patch("builtins.open", mock.mock_open(read_data="win32:LIBS += -luser32")):
            result = self.pro_parser.parse(target)
        self.assertEqual(self.pro_parser.result["conditions"], [{
            "condition": ["win32"],
            "variables": {"libs": ["-luser32"]},
            "conditions": []
        }])

    def test_pro_parse_file_not_found(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:1: SOURCES = main.cpp"}
        with mock.patch("builtins.open", side_effect=FileNotFoundError("No such file")):
            result = self.pro_parser.parse(target)
        self.assertEqual(result, self.pro_parser.result)
        self.assertEqual(self.pro_parser.result["variables"], {})
        self.assertEqual(self.pro_parser.result["conditions"], [])

    def test_pro_parse_invalid_assignment(self):
        target = {"line": "DEBUG 1: /project/src/test.pro:1: INVALID LINE"}
        with mock.patch("builtins.open", mock.mock_open(read_data="INVALID LINE")):
            result = self.pro_parser.parse(target)
        self.assertEqual(self.pro_parser.result["variables"], {})
        self.assertEqual(self.pro_parser.result["conditions"], [])

if __name__ == "__main__":
    unittest.main()
