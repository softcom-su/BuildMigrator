import os
import sys
import unittest
from unittest import mock
from pathlib import Path
import tempfile

__module_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, __module_dir)
import base
from build_migrator.generators.cmake import CMakeContext

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
TEST_FILES_DIR = os.path.join(SCRIPT_DIR, "files", "test_cmake_generator")

class TestCMakeGenerator(base.TestBase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.context = mock.Mock()
        self.context.out_dir = os.path.join(self.temp_dir.name, "output")
        self.context.source_dir = os.path.join(self.temp_dir.name, "src")
        self.context.build_dirs = [os.path.join(self.temp_dir.name, "build")]
        self.context.build_dir_placeholder = "@build_dir@"
        self.context.source_dir_placeholder = "@source_dir@"
        self.context.target_index = {}

        self.patcher_open = mock.patch("builtins.open", mock.mock_open())
        self.patcher_makedirs = mock.patch("os.makedirs")
        self.patcher_exists = mock.patch(
            "os.path.exists",
            side_effect=lambda path: path.startswith(self.temp_dir.name) or path in [
                os.path.join(self.temp_dir.name, "output"),
                os.path.join(self.temp_dir.name, "output", "src"),
                os.path.join(self.temp_dir.name, "build")
            ]
        )
        self.patcher_isdir = mock.patch("os.path.isdir", return_value=True)
        self.patcher_path_mkdir = mock.patch("pathlib.Path.mkdir", return_value=None)

        self.mock_open = self.patcher_open.start()
        self.mock_makedirs = self.patcher_makedirs.start()
        self.mock_exists = self.patcher_exists.start()
        self.mock_isdir = self.patcher_isdir.start()
        self.mock_path_mkdir = self.patcher_path_mkdir.start()

        self.parser = CMakeContext(
            self.context,
            out_dir=self.context.out_dir,
            source_subdir="src",
            build_dir=self.context.build_dirs[0],
            qt_version="5",
            qt_components=["Core", "Gui", "Widgets"]
        )
        Path(TEST_FILES_DIR).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        with mock.patch("os.remove"), mock.patch("os.listdir", return_value=[]), mock.patch("os.path.exists", return_value=False):
            if os.path.exists(TEST_FILES_DIR):
                for file in os.listdir(TEST_FILES_DIR):
                    os.remove(os.path.join(TEST_FILES_DIR, file))

        self.temp_dir.cleanup()
        self.patcher_open.stop()
        self.patcher_makedirs.stop()
        self.patcher_exists.stop()
        self.patcher_isdir.stop()
        self.patcher_path_mkdir.stop()

    def test_add_arguments(self):
        parser = mock.Mock()
        CMakeContext.add_arguments(parser)
        parser.add_argument.assert_any_call("--qt_version", choices=["5", "6"], default="5", help="Qt version to use (5 or 6). Default: 5.")
        parser.add_argument.assert_any_call("--qt_components", metavar="COMPONENT", nargs="+", help="Qt components to include (e.g., Core Gui Widgets).")

    def test_initialization(self):
        self.assertEqual(self.parser.qt_version, "5")
        self.assertEqual(self.parser.qt_components, ["Core", "Gui", "Widgets"])
        self.assertTrue(self.parser.qt_enabled)
        self.assertEqual(self.parser.values["@build_dir@"], "")
        self.assertEqual(self.parser.values["@source_dir@"], "")
        self.assertEqual(self.parser.substitutions["@build_dir@"], "")
        self.assertEqual(self.parser.substitutions["@source_dir@"], "")
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
            "output": os.path.join(self.temp_dir.name, "output")
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
            {"type": "module", "cxxflags": ["-std=gnu++14"], "config": ["c++14"], "sources": [{"path": "@source_dir@/main.cpp", "compile_flags": ["-std=gnu++1y"]}], "output": "@source_dir@/output", "module_type": "executable"},
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
        mock_file().write.assert_called_with('add_custom_command(OUTPUT output.o\n    COMMAND "gcc -c input.c"\n    DEPENDS input.c\n    VERBATIM\n)\n\n')

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
        mock_file().write.assert_called_with('add_custom_target(custom_tgt\n    COMMAND "echo Done"\n    DEPENDS input.c\n    VERBATIM\n)\n\n')

    def test_format_target_output_subdir(self):
        result = self.parser.format_target_output_subdir("test_app", "@build_dir@/bin")
        self.assertEqual(result, 'set_target_output_subdir(test_app RUNTIME_OUTPUT_DIRECTORY bin )\n')

    def test_generate_cmake_with_qt(self):
        targets = [{
            "type": "module",
            "libs": ["/usr/lib/x86_64-linux-gnu/libQt5Core.so", "GL", "pthread"],
            "sources": [],
            "output": os.path.join(self.temp_dir.name, "output"),
            "module_type": "executable"
        }]
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser.initialize_cmakelist(targets)
        calls = mock_file().write.call_args_list
        self.assertIn(mock.call("set(CMAKE_AUTOMOC ON)\n"), calls)
        self.assertIn(mock.call("set(CMAKE_AUTOUIC ON)\n"), calls)
        self.assertIn(mock.call("set(CMAKE_AUTORCC ON)\n"), calls)
        self.assertIn(mock.call("find_package(Qt5 COMPONENTS Core REQUIRED)\n"), calls)
        self.assertIn(mock.call("find_package(OpenGL REQUIRED)\n"), calls)
        self.assertIn(mock.call("find_package(Threads REQUIRED)\n"), calls)

    def test_generate_for_file_in_source_dir(self):
        target = {
            "type": "file",
            "output": "@source_dir@/main.cpp",
            "content": b"int main() {}"
        }
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._generate_for_file(target)
        mock_file.assert_any_call(os.path.join(self.temp_dir.name, "output", "src", "main.cpp"), "wb")
        mock_file().write.assert_any_call(b"int main() {}")
        self.assertNotIn(mock.call(os.path.join(self.temp_dir.name, "output", "CMakeLists.txt"), "a"), mock_file.call_args_list)

    def test_generate_for_file_qt_prebuilt(self):
        targets = [
            {"type": "file", "output": "@build_dir@/moc_main.cpp", "content": b"moc content"},
            {"type": "file", "output": "@build_dir@/ui_dialog.h", "content": b"ui content"}
        ]
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            for target in targets:
                self.parser._generate_for_file(target)
        mock_file.assert_not_called()

    def test_generate_for_include(self):
        target = {
            "type": "include",
            "output": "@source_dir@/config.cmake"
        }
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._generate_for_include(target)
        mock_file.assert_called_with(os.path.join(self.temp_dir.name, "output", "CMakeLists.txt"), "a")
        mock_file().write.assert_called_with('include(config)\n')

    def test_generate_for_subproject(self):
        target = {
            "type": "subproject",
            "module_type": "subdirs",
            "output": "@source_dir@/sub1",
            "dependencies": ["@source_dir@/sub2"]
        }
        self.parser.target_index = {
            "@source_dir@/sub2": {"type": "subproject", "module_type": "subdirs", "name": "sub2", "output": "@source_dir@/sub2"}
        }
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._generate_for_subproject(target)
        mock_file.assert_called_with(os.path.join(self.temp_dir.name, "output", "CMakeLists.txt"), "a")
        mock_file().write.assert_any_call('add_subdirectory(sub1)\n')
        self.assertEqual(target["name"], "_source_dir__sub1")
        self.assertIn("@source_dir@/sub1", self.parser.target_index)

    def test_generate_for_subproject_invalid_module_type(self):
        target = {
            "type": "subproject",
            "module_type": "executable",
            "output": "@source_dir@/sub1"
        }
        with mock.patch("builtins.open", mock.mock_open()):
            with mock.patch("logging.Logger.warning") as mock_warning:
                self.parser._generate_for_subproject(target)
        mock_warning.assert_called_with("Skipping subproject with unsupported module_type: executable")

    def test_resolve_vars(self):
        value = "$$BINDIR/app $$DATADIR/config $$PWD/src $$MYVAR"
        with mock.patch("os.path.dirname", return_value=self.temp_dir.name):
            result = self.parser.resolve_vars(value)
        self.assertEqual(result, f"/usr/bin/app /usr/share/config {self.temp_dir.name}/src ${{MYVAR}}")

        value_list = ["$$BINDIR/lib", "$$DATADIR/data"]
        result = self.parser.resolve_vars(value_list)
        self.assertEqual(result, ["/usr/bin/lib", "/usr/share/data"])

    def test_generate_for_conditions(self):
        target = {
            "type": "conditions",
            "project_name": "test_app",
            "conditions": [
                {"condition": ["win32"], "variables": {"libs": ["-luser32"]}},
                {"condition": ["else"], "variables": {"libs": ["-lX11"]}}
            ],
            "dependencies": []
        }
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._generate_for_conditions(target)
        mock_file.assert_called_with(os.path.join(self.temp_dir.name, "output", "CMakeLists.txt"), "a")
        calls = mock_file().write.call_args_list
        self.assertIn(mock.call("\n"), calls)
        self.assertIn(mock.call('if(CMAKE_SYSTEM_NAME MATCHES "Windows")\n'), calls)
        self.assertIn(mock.call('    target_link_libraries(test_app PRIVATE user32)\n'), calls)
        self.assertIn(mock.call("else()\n"), calls)
        self.assertIn(mock.call('    target_link_libraries(test_app PRIVATE X11)\n'), calls)
        self.assertIn(mock.call("endif()\n\n"), calls)

    def test_process_conditions_nested(self):
        conditions = [
            {
                "condition": ["win32"],
                "variables": {"libs": ["-luser32"]},
                "conditions": [
                    {"condition": ["msvc"], "variables": {"defines": ["MSVC_BUILD"]}}
                ]
            }
        ]
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._process_conditions("test_app", mock_file(), conditions, [], space=0)
        calls = mock_file().write.call_args_list
        self.assertIn(mock.call('if(CMAKE_SYSTEM_NAME MATCHES "Windows")\n'), calls)
        self.assertIn(mock.call('    target_link_libraries(test_app PRIVATE user32)\n'), calls)
        self.assertIn(mock.call('    if("msvc" IN_LIST CONFIG)\n'), calls)
        self.assertIn(mock.call('        set(DEFINES MSVC_BUILD)\n'), calls)
        self.assertIn(mock.call('    endif()\n\n'), calls)
        self.assertIn(mock.call('endif()\n\n'), calls)

    def test_translate_condition_to_cmake(self):
        conditions = ["win32", "!unix"]
        result = self.parser._translate_condition_to_cmake(conditions)
        self.assertEqual(result, 'CMAKE_SYSTEM_NAME MATCHES "Windows" AND NOT "unix" IN_LIST CMAKE_SYSTEM_NAME')

        result = self.parser._translate_condition_to_cmake(["else"])
        self.assertEqual(result, "")

    def test_translate_single_condition(self):
        self.assertEqual(self.parser._translate_single_condition("win32"), 'CMAKE_SYSTEM_NAME MATCHES "Windows"')
        self.assertEqual(self.parser._translate_single_condition("unix"), '"unix" IN_LIST CMAKE_SYSTEM_NAME')
        self.assertEqual(self.parser._translate_single_condition("!linux"), 'NOT "linux" IN_LIST CMAKE_SYSTEM_NAME')
        self.assertEqual(self.parser._translate_single_condition("isEmpty(MY_VAR)"), "NOT DEFINED MY_VAR")
        self.assertEqual(self.parser._translate_single_condition("exists(/usr/lib)"), 'EXISTS "/usr/lib"')
        self.assertEqual(self.parser._translate_single_condition("equals(FOO,bar)"), '"FOO" STREQUAL "bar"')
        self.assertEqual(self.parser._translate_single_condition("contains(CONFIG,debug)"), '"debug" IN_LIST CONFIG')
        self.assertEqual(self.parser._translate_single_condition("custom"), '"custom" IN_LIST CONFIG')

    def test_process_variables_sources(self):
        variables = {"sources": ["@source_dir@/main.cpp", "@source_dir@/utils.cpp"]}
        conditions = [{"condition": [], "variables": variables}]
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._process_conditions("test_app", mock_file(), conditions, [], space=0)
        mock_file().write.assert_any_call('    target_sources(test_app PRIVATE main.cpp utils.cpp)\n')

    def test_process_variables_install(self):
        variables = {
            "binfile.files": ["@source_dir@/app", "@source_dir@/lib/*"],
            "binfile.path": ["/usr/bin"]
        }
        with mock.patch("glob.glob", return_value=[os.path.join(self.temp_dir.name, "output", "src", "app"), os.path.join(self.temp_dir.name, "output", "src", "lib", "lib1.so")]):
            with mock.patch("builtins.open", mock.mock_open()) as mock_file:
                self.parser._process_variables("test_app", mock_file(), variables, [], 0, 1, [{"variables": variables}], space=1)
        mock_file().write.assert_called_with(f'        install(FILES app {os.path.join("/output", "src", "app")} {os.path.join("/output", "src", "lib", "lib1.so")} DESTINATION /usr/bin)\n')

    def test_process_variables_libs(self):
        variables = {"libs": ["-lboost", "-L/usr/lib", "/custom/lib.so"]}
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._process_variables("test_app", mock_file(), variables, [], 0, 1, [{"variables": variables}], space=0)
        mock_file().write.assert_any_call('    target_link_libraries(test_app PRIVATE boost /custom/lib.so)\n')

    def test_process_variables_defines(self):
        variables = {"my.defines": ["DEBUG", "MY_MACRO"]}
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._process_variables("test_app", mock_file(), variables, [], 0, 1, [{"variables": variables}], space=0)
        mock_file().write.assert_called_with('    add_definitions(-DDEBUG -DMY_MACRO)\n')

    def test_process_variables_includepath(self):
        variables = {"my.includepath": ["/usr/include", "@source_dir@/include"]}
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.parser._process_variables("test_app", mock_file(), variables, [], 0, 1, [{"variables": variables}], space=0)
        mock_file().write.assert_called_with('    include_directories(/usr/include include)\n')

    def test_process_variables_invalid(self):
        variables = {"invalid": None}
        with mock.patch("builtins.open", mock.mock_open()):
            with mock.patch("logging.Logger.warning") as mock_warning:
                self.parser._process_variables("test_app", mock.MagicMock(), variables, [], 0, 1, [{"variables": variables}], space=0)
        mock_warning.assert_called_with("Skipping invalid variable: invalid")

    def test_get_subproject_dependencies(self):
        target = {
            "type": "subproject",
            "module_type": "subdirs",
            "output": "@source_dir@/sub",
            "dependencies": ["@source_dir@/sub1", "@source_dir@/sub2", "@source_dir@/invalid"]
        }
        self.parser.target_index = {
            "@source_dir@/sub1": {"type": "subproject", "module_type": "subdirs", "output": "@source_dir@/sub1"},
            "@source_dir@/sub2": {"type": "subproject", "module_type": "subdirs", "output": "@source_dir@/sub2", "name": "sub2"},
            "@source_dir@/invalid": {"type": "module", "module_type": "executable"}
        }

        with mock.patch("logging.Logger.debug") as mock_debug:
            result = self.parser._get_subproject_dependencies(target)
        self.assertEqual(set(result), {"sub1", "sub2"})
        self.parser.target_index["@source_dir@/sub1"]["name"] = "sub1"
        mock_debug.assert_any_call("Skipping non-subproject dependency: @source_dir@/invalid")

if __name__ == "__main__":
    unittest.main()
