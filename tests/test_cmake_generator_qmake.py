import os
import sys
import unittest
from unittest import mock
from pathlib import Path

__module_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, __module_dir)
import base
from build_migrator.generators.cmake import CMakeContext

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
TEST_FILES_DIR = os.path.join(SCRIPT_DIR, "files", "test_cmake_generator")

class TestCMakeGenerator(base.TestBase):
    def setUp(self):
        self.context = mock.Mock()
        self.context.out_dir = "/project/output"
        self.context.source_dir = "/project/src"
        self.context.build_dirs = ["/project/build"]
        self.context.build_dir_placeholder = "@build_dir@"
        self.context.source_dir_placeholder = "@source_dir@"
        self.context.target_index = {}
        with mock.patch("os.path.exists", side_effect=lambda path: path in ["/project/output", "/project/output/src", "/project/build"]):
            self.parser = CMakeContext(self.context, out_dir=self.context.out_dir, source_subdir="src", build_dir="/project/build", qt_version="5", qt_components=["Core", "Gui", "Widgets"])
        Path(TEST_FILES_DIR).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if os.path.exists(TEST_FILES_DIR):
            for file in os.listdir(TEST_FILES_DIR):
                os.remove(os.path.join(TEST_FILES_DIR, file))

    def test_add_arguments(self):
        parser = mock.Mock()
        CMakeContext.add_arguments(parser)
        parser.add_argument.assert_any_call("--qt_version", choices=["5", "6"], default="5", help="Qt version to use (5 or 6). Default: 5.")
        parser.add_argument.assert_any_call("--qt_components", metavar="COMPONENT", nargs="+", help="Qt components to include (e.g., Core Gui Widgets).")

    def test_initialization(self):
        self.assertEqual(self.parser.qt_version, "5")
        self.assertEqual(self.parser.qt_components, ["Core", "Gui", "Widgets"])
        self.assertTrue(self.parser.qt_enabled)
        self.assertEqual(self.parser.source_dir_full_path, "/project/output/src")
        self.assertEqual(self.parser.current_list_dir_full_path, "/project/output")
        self.assertEqual(self.parser.build_dir_full_path, "/project/build")
        self.assertEqual(self.parser.values["@build_dir@"], "/project/build")
        self.assertEqual(self.parser.values["@source_dir@"], "/project/output/src")
        self.assertEqual(self.parser.substitutions["@build_dir@"], "/project/build")
        self.assertEqual(self.parser.substitutions["@source_dir@"], "/project/output/src")
        self.assertEqual(self.parser.cxx_standard, "17")
        self.assertEqual(self.parser.cxx_standard_required, "ON")
        self.assertEqual(self.parser.cxx_extensions, "OFF")

    def test_process_qt_sources(self):
        targets = [{
            "type": "module",
            "sources": [
                {"path": "@source_dir@/main.cpp", "compile_flags": ["-std=c++17", "-DQT_CORE_LIB"], "include_dirs": ["/usr/include/x86_64-linux-gnu/qt5"]},
                {"path": "@build_dir@/moc_main.cpp", "compile_flags": []},
                {"path": "@build_dir@/ui_dialog.h", "compile_flags": []}
            ],
            "libs": ["/usr/lib/x86_64-linux-gnu/libQt5Core.so", "GL", "pthread"],
            "output": "/project/output"
        }]
        qt_sources = [{"path": "@source_dir@/dialog.ui", "extension": ".ui"}]
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._process_qt_sources(mock_file, targets, qt_sources)
        self.assertEqual(targets[0]["sources"], [
            {"path": "@source_dir@/main.cpp", "compile_flags": ["-std=c++17"], "include_dirs": []},
            {"path": "@source_dir@/dialog.ui", "extension": ".ui"}
        ])
        self.assertEqual(targets[0]["libs"], ["Qt5::Core", "OpenGL::GL", "Threads::Threads"])

    def test_cxx_standard_detection(self):
        targets = [
            {"type": "module", "cxxflags": ["-std=gnu++14"], "config": ["c++14"], "sources": [{"path": "@source_dir@/main.cpp", "compile_flags": ["-std=gnu++1y"]}], "output": "@source_dir@/output", 'module_type': 'executable'},
        ]
        with mock.patch("builtins.open", mock.mock_open()):
            self.parser.initialize_cmakelist(targets)
        self.assertEqual(self.parser.cxx_standard, "14")
        self.assertEqual(self.parser.cxx_extensions, "ON")

    def test_generate_for_custom_command(self):
        target = {
            "type": "custom_command",
            "output": "@build_dir@/output.o",
            "command": "gcc -c input.c",
            "dependencies": ["@source_dir@/input.c"]
        }
        self.context.target_index = {"@source_dir@/input.c": {"name": "input_c"}}
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._generate_for_custom_command(target)
        mock_file().write.assert_called_with('add_custom_command(OUTPUT /project/build/output.o\n    COMMAND "gcc -c input.c"\n    DEPENDS /project/output/src/input.c\n    VERBATIM\n)\n\n')

    def test_generate_for_custom_target(self):
        target = {
            "type": "custom_target",
            "name": "custom_tgt",
            "commands": ["echo Done"],
            "dependencies": ["@source_dir@/input.c"]
        }
        self.context.target_index = {"@source_dir@/input.c": {"name": "input_c"}}
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._generate_for_custom_target(target)
        mock_file().write.assert_called_with('add_custom_target(custom_tgt\n    COMMAND "echo Done"\n    DEPENDS /project/output/src/input.c\n    VERBATIM\n)\n\n')

    def test_format_target_output_subdir(self):
        result = self.parser.format_target_output_subdir("test_app", "@build_dir@/bin")
        self.assertEqual(result, 'set_target_output_subdir(test_app RUNTIME_OUTPUT_DIRECTORY /project/build/bin )\n')

    def test_generate_cmake_with_qt(self):
        targets = [{
            "type": "module",
            "libs": ["/usr/lib/x86_64-linux-gnu/libQt5Core.so", "GL", "pthread"],
            "sources": [],
            "output": "/project/output",
            'module_type': 'executable'
        }]
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser.initialize_cmakelist(targets)
        calls = mock_file().write.call_args_list
        self.assertIn(mock.call("set(CMAKE_AUTOMOC ON)\n"), calls)
        self.assertIn(mock.call("set(CMAKE_AUTOUIC ON)\n"), calls)
        self.assertIn(mock.call("set(CMAKE_AUTORCC ON)\n"), calls)
        self.assertIn(mock.call("find_package(Qt5 COMPONENTS Widgets Gui Core REQUIRED)\n"), calls)
        self.assertIn(mock.call("find_package(OpenGL REQUIRED)\n"), calls)
        self.assertIn(mock.call("find_package(Threads REQUIRED)\n"), calls)

if __name__ == "__main__":
    unittest.main()
