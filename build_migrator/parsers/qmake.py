from __future__ import print_function
import re
import logging
import os
import uuid
try:
    from build_migrator.modules import Parser
except ImportError:
    class Parser(object):
        pass

logger = logging.getLogger(__name__)

class QmakeLogParser(Parser):
    """Parser for qmake -d logs in BuildMigrator, generating build_object_model for Qt projects."""
    
    priority = 1

    @staticmethod
    def add_arguments(arg_parser):
        pass

    @staticmethod
    def is_applicable(log_type=None):
        return log_type == "qmake"

    def __init__(self, context):
        self.context = context
        self.patterns = {
            "sources": re.compile(r"DEBUG 1: .+?\.pro:\d+: SOURCES := (.+)"),
            "headers": re.compile(r"DEBUG 1: .+?\.pro:\d+: HEADERS := (.+)"),
            "forms": re.compile(r"DEBUG 1: .+?\.pro:\d+: FORMS := (.+)"),
            "resources": re.compile(r"DEBUG 1: .+?\.pro:\d+: RESOURCES := (.+)"),
            "includepath": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: INCLUDEPATH := (.+)"),
            "libs": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: LIBS := (.+)"),
            "target": re.compile(r"DEBUG 1: .+?\.pro:\d+: TARGET := (.+)"),
            "template": re.compile(r"DEBUG 1: .+?\.pro:\d+: TEMPLATE := (.+)"),
            "cxx": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: QMAKE_CXX := (.+)"),
            "cc": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: QMAKE_CC := (.+)"),
            "cxxflags": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: QMAKE_CXXFLAGS := (.+)"),
            "cflags": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: QMAKE_CFLAGS := (.+)"),
            "defines": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: DEFINES := (.+)"),
            "config": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: CONFIG := (.+)"),
            "lflags": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: QMAKE_LFLAGS := (.+)"),
            "qt": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: QT := (.+)"),
            "moc_dir": re.compile(r"DEBUG 1: .+?\.pro:\d+: MOC_DIR := (.+)"),
            "ui_dir": re.compile(r"DEBUG 1: .+?\.pro:\d+: UI_DIR := (.+)"),
            "rcc_dir": re.compile(r"DEBUG 1: .+?\.pro:\d+: RCC_DIR := (.+)"),
            "subdirs": re.compile(r"DEBUG 1: .+?\.pro:\d+: SUBDIRS := (.+)"),
            "debug_config": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: CONFIG\(debug, debug\|release\)\s*\{(.+?)\}"),
            "release_config": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: CONFIG\(release, debug\|release\)\s*\{(.+?)\}"),
            "destdir": re.compile(r"DEBUG 1: .+?\.pro:\d+: DESTDIR := (.+)"),
            "dependpath": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: DEPENDPATH := (.+)"),
            "precompiled_header": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: PRECOMPILED_HEADER := (.+)"),
            "platform_win32": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: win32\s*\{(.+?)\}"),
            "platform_unix": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: unix\s*\{(.+?)\}"),
            "platform_macx": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: macx\s*\{(.+?)\}"),
            "testcase": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: CONFIG\s*\+=\s*testcase"),
            "cxxflags_release": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: QMAKE_CXXFLAGS_RELEASE := (.+)"),
            "cxxflags_debug": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: QMAKE_CXXFLAGS_DEBUG := (.+)"),
            "distfiles": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: DISTFILES := (.+)"),
            "version": re.compile(r"DEBUG 1: .+?\.(pro|prf):\d+: VERSION := (.+)"),
            "extra_compilers": re.compile(r"DEBUG 1: .+?\.pro:\d+: QMAKE_EXTRA_COMPILERS\s*:=\s*(.+)"),
            "compiler_input": re.compile(r"DEBUG 1: .+?\.pro:\d+: (\w+)\.input\s*:=\s*(.+)"),
            "compiler_output": re.compile(r"DEBUG 1: .+?\.pro:\d+: (\w+)\.output\s*:=\s*(.+)"),
            "compiler_variable": re.compile(r"DEBUG 1: .+?\.pro:\d+: (\w+)\.variable\s*:=\s*(.+)"),
            "extra_targets": re.compile(r"DEBUG 1: .+?\.pro:\d+: QMAKE_EXTRA_TARGETS\s*\:=\s*(.+)"),
            "target_target": re.compile(r"DEBUG 1: .+?\.pro:\d+: (\w+)\.target\s*:=\s*(.+)"),
            "target_depends": re.compile(r"DEBUG 1: .+?\.pro:\d+: (\w+)\.depends\s*:=\s*(.+)"),
            "pre_targetdeps": re.compile(r"DEBUG 1: .+?\.pro:\d+: PRE_TARGETDEPS\s*\:=\s*(.+)"),
            "post_targetdeps": re.compile(r"DEBUG 1: .+?\.pro:\d+: QMAKE_POST_TARGETDEPS\s*\:=\s*(.+)"),
            "commands": re.compile(r"DEBUG 1: .+?\.pro:\d+: (\w+)\.commands\s*:=\s*(.+)"),
        }
        self.global_config = {
            "includes": set(),
            "libs": set(),
            "target": None,
            "compiler": "g++",
            "c_compiler": "gcc",
            "compile_flags": set(),
            "link_flags": set(),
            "type": "executable",
            "headers": set(),
            "sources": set(),
            "forms": set(),
            "resources": set(),
            "distfiles": set(),
            "qt_modules": set(),
            "moc_dir": "@build_dir@/moc",
            "ui_dir": "@build_dir@/uic",
            "rcc_dir": "@build_dir@/rcc",
            "subdirs": set(),
            "destdir": "@build_dir@/_build",
            "dependpath": set(),
            "precompiled_header": None,
            "platform_settings": {"win32": set(), "unix": set(), "macx": set()},
            "testcase": False,
            "version": None,
            "custom_commands": [],
            "custom_targets": [],
        }
        self.build_object_model = []
        self.processed_sources = set()
        self.processed_headers = set()
        self.processed_forms = set()
        self.processed_resources = set()
        self.ui_headers = set()
        self.moc_sources = set()
        self.rcc_sources = set()
        self.processed_lines = set()
        self.is_qt_project = False
        self.automoc_enabled = False
        self.autouic_enabled = False
        self.autorcc_enabled = False
        self.debug_config = False
        self.release_config = False
        self.valid_qt_modules = {"core", "gui", "widgets", "network", "sql", "testlib"}
        self.qt_include_dirs = {
            "/usr/include",
            "/usr/include/x86_64-linux-gnu/qt5",
            "/usr/include/x86_64-linux-gnu/qt5/QtGui",
            "/usr/include/x86_64-linux-gnu/qt5/QtCore",
            "/usr/lib/x86_64-linux-gnu/qt5/mkspecs/linux-g++"
        }
        self.custom_compilers = {}
        self.custom_targets_info = {}
        self.post_targetdeps = {}
        self.commands = {}

    def _read_file_content(self, path):
        try:
            full_path = path.replace("@source_dir@", self.context.source_dir).replace("@build_dir@", self.context.build_dirs[0])
            with open(full_path, "rb") as f:
                content = f.read()
                logger.debug("Read content for %s (%d bytes)" % (path, len(content)))
                return content
        except IOError as e:
            logger.warning("Cannot read file %s: %s" % (path, str(e)))
            return None

    def _get_include_dirs(self):
        include_dirs = set(["@source_dir@", "@build_dir@/_build", "@source_dir@/include"])
        include_dirs.update(self.global_config["includes"])
        include_dirs.update(self.global_config["dependpath"])
        if self.global_config["rcc_dir"]:
            include_dirs.add(self.global_config["rcc_dir"])
        if self.global_config["ui_dir"]:
            include_dirs.add(self.global_config["ui_dir"])
        if self.is_qt_project:
            include_dirs.update(self.qt_include_dirs)
        return sorted([path for path in include_dirs if not path.endswith((".pro", ".prf")) and path not in ("prf", "pro")])

    def _check_for_qobject(self, content):
        return content and b"Q_OBJECT" in content

    def _post_normalize_path(self, path):
        """Replace source_dir and build_dir with @source_dir@ and @build_dir@."""
        source_dir = self.context.source_dir
        build_dir = self.context.build_dirs[0]
        if path.startswith(source_dir):
            return path.replace(source_dir, "@source_dir@")
        if path.startswith(build_dir):
            return path.replace(build_dir, "@build_dir@")
        return path

    def _process_conditional_config(self, config_content, build_type):
        defines_match = re.search(r"DEFINES\s*\+=\s*(\S+)", config_content)
        if defines_match:
            define = defines_match.group(1)
            if "-D" + define not in self.global_config["compile_flags"] and not define.endswith((".pro", ".prf")) and define != "prf":
                self.global_config["compile_flags"].add("-D" + define)
            logger.debug(f"Added {build_type} DEFINE: {define}")
        cxxflags_match = re.search(r"QMAKE_CXXFLAGS\s*\+=\s*(.+)", config_content)
        if cxxflags_match:
            for flag in cxxflags_match.group(1).split():
                if flag not in self.global_config["compile_flags"] and not flag.endswith((".pro", ".prf")) and flag != "prf":
                    self.global_config["compile_flags"].add(flag)
            logger.debug(f"Added {build_type} CXXFLAGS: {cxxflags_match.group(1)}")
        lflags_match = re.search(r"QMAKE_LFLAGS\s*\+=\s*(.+)", config_content)
        if lflags_match:
            for flag in lflags_match.group(1).split():
                if flag not in self.global_config["link_flags"] and not flag.endswith((".pro", ".prf")) and flag != "prf":
                    self.global_config["link_flags"].add(flag)
            logger.debug(f"Added {build_type} LFLAGS: {lflags_match.group(1)}")

    def _process_platform_config(self, config_content, platform):
        libs_match = re.search(r"LIBS\s*\+=\s*(.+)", config_content)
        if libs_match:
            for lib in libs_match.group(1).split():
                if lib.startswith("-l"):
                    lib_name = lib[2:]
                    if lib_name not in self.global_config["libs"] and not lib_name.endswith((".pro", ".prf")) and lib_name != "prf":
                        self.global_config["libs"].add(lib_name)
                elif lib.startswith("-L"):
                    include_path = self._post_normalize_path(self.context.normalize_path(lib[2:], ignore_working_dir=True))
                    if include_path not in self.global_config["includes"] and not include_path.endswith((".pro", ".prf")) and include_path not in ("prf", "pro"):
                        self.global_config["includes"].add(include_path)
                else:
                    normalized_lib = self._post_normalize_path(self.context.normalize_path(lib, ignore_working_dir=True))
                    if normalized_lib not in self.global_config["libs"] and not normalized_lib.endswith((".pro", ".prf")) and normalized_lib != "prf" and (os.path.isfile(normalized_lib) or normalized_lib == "fmt"):
                        self.global_config["libs"].add(normalized_lib)
                logger.debug(f"Added {platform} LIB: {lib}")

    def _process_custom_command(self, compiler_name, input_files, output, commands):
        command_id = str(uuid.uuid4())
        normalized_command = commands.strip()
        normalized_output = self._post_normalize_path(self.context.normalize_path(output, ignore_working_dir=True))
        normalized_inputs = [self._post_normalize_path(self.context.normalize_path(inp, ignore_working_dir=True)) for inp in input_files]
        self.global_config["custom_commands"].append({
            "id": command_id,
            "command": normalized_command,
            "output": normalized_output,
            "inputs": normalized_inputs
        })
        self.build_object_model.append({
            "type": "custom_command",
            "command": normalized_command,
            "output": normalized_output,
            "dependencies": normalized_inputs,
            "id": command_id
        })

    def _process_custom_target(self, target_name, target, commands, depends):
        target_id = str(uuid.uuid4())
        normalized_target = self._post_normalize_path(self.context.normalize_path(target, ignore_working_dir=True))
        normalized_deps = [self._post_normalize_path(self.context.normalize_path(dep, ignore_working_dir=True)) for dep in depends]
        normalized_commands = [cmd.strip() for cmd in commands.split("&&")]
        self.global_config["custom_targets"].append({
            "id": target_id,
            "name": normalized_target,
            "dependencies": normalized_deps,
            "commands": normalized_commands
        })
        self.build_object_model.append({
            "type": "custom_target",
            "name": normalized_target,
            "dependencies": normalized_deps,
            "commands": normalized_commands,
            "id": target_id
        })

    def parse(self, target):
        line = target.get("line", "")
        is_eof = target.get("eof", False)

        if line:
            normalized_line = " ".join(line.split())
            if normalized_line in self.processed_lines:
                logger.debug("Skipping already processed line: %s" % normalized_line)
                target["line"] = ""
                return target
            self.processed_lines.add(normalized_line)

            for key, pattern in self.patterns.items():
                match = pattern.search(line)
                if match:
                    if key in ["debug_config", "release_config", "platform_win32", "platform_unix", "platform_macx", "testcase"]:
                        value = match.group(0)
                    elif key in ["compiler_input", "compiler_output", "compiler_variable", "commands", "target_target", "target_depends"]:
                        if match.groups() and len(match.groups()) >= 2:
                            value = match.groups()
                        else:
                            logger.warning(f"Invalid format for {key} in line: {line}")
                            continue
                    elif "(pro|prf)" in pattern.pattern:
                        if match.groups() and len(match.groups()) >= 2:
                            value = match.group(2).strip()
                        else:
                            logger.warning(f"Missing group(2) for {key} in line: {line}")
                            continue
                    else:
                        value = match.group(1).strip()
                    if not value and key not in ["testcase"]:
                        logger.warning("Empty value for %s in line: %s" % (key, line))
                        continue

                    if key == "sources":
                        for source in value.split():
                            if source.endswith((".cpp", ".cc", ".cxx")):
                                source_path = self._post_normalize_path(self.context.normalize_path(
                                    source,
                                    working_dir=self.context.source_dir,
                                    ignore_working_dir=False
                                ))
                                if source_path in self.processed_sources:
                                    logger.debug("Skipping already processed source: %s" % source_path)
                                    continue
                                self.processed_sources.add(source_path)
                                self.global_config["sources"].add(source_path)
                                content = self._read_file_content(source_path)
                                if content is not None:
                                    self.build_object_model.append({
                                        "content": content,
                                        "output": source_path,
                                        "dependencies": [],
                                        "type": "file"
                                    })
                                logger.debug("Added source: %s" % source_path)
                    elif key == "headers":
                        for header in value.split():
                            if header.endswith((".h", ".hpp", ".hh", ".hxx")):
                                header_path = self._post_normalize_path(self.context.normalize_path(
                                    header,
                                    working_dir=self.context.source_dir,
                                    ignore_working_dir=False
                                ))
                                if header_path in self.processed_headers:
                                    logger.debug("Skipping already processed header: %s" % header_path)
                                    continue
                                self.processed_headers.add(header_path)
                                self.global_config["headers"].add(header_path)
                                content = self._read_file_content(header_path)
                                if content is not None:
                                    self.build_object_model.append({
                                        "content": content,
                                        "output": header_path,
                                        "dependencies": [],
                                        "type": "file"
                                    })
                                if content and self._check_for_qobject(content):
                                    self.is_qt_project = True
                                    if self.automoc_enabled:
                                        self.global_config["sources"].add(header_path)
                                        logger.debug("Added header for AUTOMOC: %s" % header_path)
                                    else:
                                        moc_path = self._post_normalize_path(self.context.normalize_path(
                                            os.path.join(self.global_config["moc_dir"], "moc_%s.cpp" % os.path.basename(header_path).rsplit('.', 1)[0]),
                                            ignore_working_dir=True
                                        ))
                                        if moc_path not in self.moc_sources:
                                            self.moc_sources.add(moc_path)
                                            self.global_config["sources"].add(moc_path)
                                            logger.debug("Added moc source: %s for header: %s" % (moc_path, header_path))
                                logger.debug("Added header: %s" % header_path)
                    elif key == "forms":
                        for form in value.split():
                            if not form.endswith(".ui"):
                                logger.warning("Invalid FORMS file: %s" % form)
                                continue
                            self.is_qt_project = True
                            form_path = self._post_normalize_path(self.context.normalize_path(
                                form,
                                working_dir=self.context.source_dir,
                                ignore_working_dir=False
                            ))
                            if form_path in self.processed_forms:
                                logger.debug("Skipping already processed form: %s" % form_path)
                                continue
                            self.processed_forms.add(form_path)
                            self.global_config["forms"].add(form_path)
                            if self.autouic_enabled:
                                self.global_config["sources"].add(form_path)
                                logger.debug("Added form for AUTOUIC: %s" % form_path)
                            else:
                                base_name = os.path.basename(form).rsplit('.', 1)[0]
                                output = self._post_normalize_path(self.context.normalize_path(
                                    os.path.join(self.global_config["ui_dir"], "ui_" + base_name + ".h"),
                                    ignore_working_dir=True
                                ))
                                if output not in self.ui_headers:
                                    self.ui_headers.add(output)
                                content = self._read_file_content(form_path)
                                if content is not None:
                                    self.build_object_model.append({
                                        "content": content,
                                        "output": form_path,
                                        "dependencies": [],
                                        "type": "file",
                                        "extension": ".ui"
                                    })
                                logger.debug("Added FORM: %s (ui header: %s)" % (form_path, output))
                    elif key == "resources":
                        for resource in value.split():
                            if not resource.endswith(".qrc"):
                                logger.warning("Invalid RESOURCES file: %s" % resource)
                                continue
                            self.is_qt_project = True
                            resource_path = self._post_normalize_path(self.context.normalize_path(
                                resource,
                                working_dir=self.context.source_dir,
                                ignore_working_dir=False
                            ))
                            if resource_path in self.processed_resources:
                                logger.debug("Skipping already processed resource: %s" % resource_path)
                                continue
                            self.processed_resources.add(resource_path)
                            self.global_config["resources"].add(resource_path)
                            if self.autorcc_enabled:
                                self.global_config["sources"].add(resource_path)
                                logger.debug("Added resource for AUTORCC: %s" % resource_path)
                            else:
                                base_name = os.path.basename(resource).rsplit('.', 1)[0]
                                output = self._post_normalize_path(self.context.normalize_path(
                                    os.path.join(self.global_config["rcc_dir"], "qrc_" + base_name + ".cpp"),
                                    ignore_working_dir=True
                                ))
                                if output not in self.rcc_sources:
                                    self.rcc_sources.add(output)
                                content = self._read_file_content(resource_path)
                                if content is not None:
                                    self.build_object_model.append({
                                        "content": content,
                                        "output": resource_path,
                                        "dependencies": [],
                                        "type": "file",
                                        "extension": ".qrc"
                                    })
                                logger.debug("Added RESOURCE: %s -> %s" % (resource_path, output))
                    elif key == "distfiles":
                        for distfile in value.split():
                            distfile_path = self._post_normalize_path(self.context.normalize_path(distfile, working_dir=self.context.source_dir))
                            self.global_config["distfiles"].add(distfile_path)
                            content = self._read_file_content(distfile_path)
                            if content is not None:
                                self.build_object_model.append({
                                    "content": content,
                                    "output": distfile_path,
                                    "dependencies": [],
                                    "type": "file"
                                })
                    elif key == "includepath":
                        for path in value.split():
                            normalized_path = self._post_normalize_path(self.context.normalize_path(path, ignore_working_dir=True))
                            if normalized_path not in self.global_config["includes"] and not normalized_path.endswith((".pro", ".prf")) and normalized_path not in ("prf", "pro"):
                                self.global_config["includes"].add(normalized_path)
                                logger.debug("Added INCLUDEPATH: %s (normalized: %s)" % (path, normalized_path))
                    elif key == "libs":
                        for lib in value.split():
                            if lib.startswith("-l"):
                                lib_name = lib[2:]
                                if lib_name not in self.global_config["libs"] and not lib_name.endswith((".pro", ".prf")) and lib_name != "prf":
                                    self.global_config["libs"].add(lib_name)
                            elif lib.startswith("-L"):
                                include_path = self._post_normalize_path(self.context.normalize_path(lib[2:], ignore_working_dir=True))
                                if include_path not in self.global_config["includes"] and not include_path.endswith((".pro", ".prf")) and include_path not in ("prf", "pro"):
                                    self.global_config["includes"].add(include_path)
                            else:
                                normalized_lib = self._post_normalize_path(self.context.normalize_path(lib, ignore_working_dir=True))
                                if normalized_lib not in self.global_config["libs"] and not normalized_lib.endswith((".pro", ".prf")) and normalized_lib != "prf" and (os.path.isfile(normalized_lib) or normalized_lib == "fmt"):
                                    self.global_config["libs"].add(normalized_lib)
                            logger.debug("Added LIB: %s" % lib)
                    elif key == "target":
                        self.global_config["target"] = value.strip() or None
                        logger.debug("Set TARGET: %s" % self.global_config["target"])
                    elif key == "template":
                        if value == "app":
                            self.global_config["type"] = "executable"
                        elif value == "lib":
                            self.global_config["type"] = "shared_library"
                        elif value == "subdirs":
                            self.global_config["type"] = "subdirs"
                        logger.debug("Set TEMPLATE: %s" % self.global_config["type"])
                    elif key == "cxx":
                        self.global_config["compiler"] = value
                        logger.debug("Set CXX: %s" % value)
                    elif key == "cc":
                        self.global_config["c_compiler"] = value
                        logger.debug("Set CC: %s" % value)
                    elif key == "cxxflags":
                        for flag in value.split():
                            if flag not in self.global_config["compile_flags"] and not flag.endswith((".pro", ".prf")) and flag != "prf":
                                self.global_config["compile_flags"].add(flag)
                        logger.debug("Added CXXFLAGS: %s" % value)
                    elif key == "cflags":
                        for flag in value.split():
                            if flag not in self.global_config["compile_flags"] and not flag.endswith((".pro", ".prf")) and flag != "prf":
                                self.global_config["compile_flags"].add(flag)
                        logger.debug("Added CFLAGS: %s" % value)
                    elif key == "defines":
                        for define in value.split():
                            if define.strip() and "-D" + define.strip() not in self.global_config["compile_flags"] and not define.endswith((".pro", ".prf")) and define != "prf":
                                self.global_config["compile_flags"].add("-D" + define.strip())
                            else:
                                logger.warning("Skipped invalid or duplicate DEFINE: '%s'" % define)
                    elif key == "config":
                        config_values = value.split()
                        logger.debug("Processing CONFIG line: %s" % line)
                        if "gcc" in config_values:
                            self.global_config["compiler"] = "g++"
                            self.global_config["c_compiler"] = "gcc"
                        if "c++17" in config_values or "c++1z" in config_values:
                            self.global_config["compile_flags"].add("-std=gnu++1z")
                            logger.debug("Added C++17 flag: -std=gnu++1z")
                        if "c++20" in config_values:
                            self.global_config["compile_flags"].add("-std=gnu++20")
                        if "debug" in config_values and "release" not in config_values:
                            self.debug_config = True
                            self.release_config = False
                            self.global_config["compile_flags"].add("-g")
                            logger.debug("Activated debug mode")
                        if "release" in config_values and "debug" not in config_values:
                            self.debug_config = False
                            self.release_config = True
                            for flag in ["-O2", "-fPIC", "-Wall", "-Wextra"]:
                                self.global_config["compile_flags"].add(flag)
                            self.global_config["link_flags"].add("-Wl,-O1")
                            logger.debug("Activated release mode via CONFIG")
                        if "qt" in config_values or "Qt" in value:
                            self.is_qt_project = True
                            logger.debug("Qt project detected via CONFIG")
                            self.global_config["compile_flags"].add("-D_REENTRANT")
                            if not self.global_config["qt_modules"]:
                                self.global_config["qt_modules"].update(["core", "gui"])
                                self.global_config["libs"].update([
                                    "/usr/lib/x86_64-linux-gnu/libQt5Core.so",
                                    "/usr/lib/x86_64-linux-gnu/libQt5Gui.so",
                                    "GL",
                                    "pthread"
                                ])
                                self.global_config["compile_flags"].update([
                                    "-DQT_CORE_LIB",
                                    "-DQT_GUI_LIB",
                                    "-DQT_NO_DEBUG"
                                ])
                        if "automoc" in config_values:
                            self.automoc_enabled = True
                            logger.debug("Enabled AUTOMOC")
                        if "autouic" in config_values:
                            self.autouic_enabled = True
                            logger.debug("Enabled AUTOUIC")
                        if "autorcc" in config_values:
                            self.autorcc_enabled = True
                            logger.debug("Enabled AUTORCC")
                        if "warn_on" in config_values:
                            self.global_config["compile_flags"].update(["-Wall", "-Wextra"])
                        logger.debug("Processed CONFIG: %s" % config_values)
                    elif key == "lflags":
                        for flag in value.split():
                            if flag not in self.global_config["link_flags"] and not flag.endswith((".pro", ".prf")) and flag != "prf":
                                self.global_config["link_flags"].add(flag)
                        logger.debug("Added LFLAGS: %s" % value)
                    elif key == "qt":
                        for module in value.split():
                            module = module.strip()
                            if module.startswith("+="):
                                module = module[2:].strip()
                            if module in self.valid_qt_modules:
                                self.global_config["qt_modules"].add(module)
                                self.global_config["libs"].add(f"/usr/lib/x86_64-linux-gnu/libQt5{module.capitalize()}.so")
                                self.global_config["compile_flags"].add(f"-DQT_{module.upper()}_LIB")
                            else:
                                logger.warning("Skipping invalid Qt module: %s" % module)
                        if self.global_config["qt_modules"]:
                            self.is_qt_project = True
                            self.global_config["libs"].update(["GL", "pthread"])
                            logger.debug("Qt project detected via QT: %s" % value)
                        logger.debug("Added QT modules: %s" % value)
                    elif key == "moc_dir":
                        self.global_config["moc_dir"] = self._post_normalize_path(self.context.normalize_path(value, ignore_working_dir=True))
                        logger.debug("Set MOC_DIR: %s" % self.global_config["moc_dir"])
                    elif key == "ui_dir":
                        self.global_config["ui_dir"] = self._post_normalize_path(self.context.normalize_path(value, ignore_working_dir=True))
                        logger.debug("Set UI_DIR: %s" % self.global_config["ui_dir"])
                    elif key == "rcc_dir":
                        self.global_config["rcc_dir"] = self._post_normalize_path(self.context.normalize_path(value, ignore_working_dir=True))
                        logger.debug("Set RCC_DIR: %s" % self.global_config["rcc_dir"])
                    elif key == "subdirs":
                        for subdir in value.split():
                            self.global_config["subdirs"].add(self._post_normalize_path(self.context.normalize_path(
                                subdir,
                                working_dir=self.context.source_dir,
                                ignore_working_dir=False
                            )))
                        logger.debug("Added SUBDIRS: %s" % value)
                    elif key == "debug_config":
                        self._process_conditional_config(match.group(1), "debug")
                        self.debug_config = True
                        self.release_config = False
                        self.global_config["compile_flags"].add("-g")
                        logger.debug("Activated debug mode via debug_config")
                    elif key == "release_config":
                        self._process_conditional_config(match.group(1), "release")
                        self.debug_config = False
                        self.release_config = True
                        for flag in ["-O2", "-fPIC", "-Wall", "-Wextra"]:
                            self.global_config["compile_flags"].add(flag)
                        self.global_config["link_flags"].add("-Wl,-O1")
                        logger.debug("Activated release mode via release_config")
                    elif key == "destdir":
                        self.global_config["destdir"] = self._post_normalize_path(self.context.normalize_path(value, ignore_working_dir=True))
                        logger.debug("Set DESTDIR: %s" % self.global_config["destdir"])
                    elif key == "dependpath":
                        for path in value.split():
                            normalized_path = self._post_normalize_path(self.context.normalize_path(path, ignore_working_dir=True))
                            if normalized_path not in self.global_config["dependpath"] and not normalized_path.endswith((".pro", ".prf")) and normalized_path not in ("prf", "pro"):
                                self.global_config["dependpath"].add(normalized_path)
                                logger.debug("Added DEPENDPATH: %s (normalized: %s)" % (path, normalized_path))
                    elif key == "precompiled_header":
                        header_path = self._post_normalize_path(self.context.normalize_path(
                            value,
                            working_dir=self.context.source_dir,
                            ignore_working_dir=False
                        ))
                        self.global_config["precompiled_header"] = header_path
                        self.global_config["headers"].add(header_path)
                        logger.debug("Set PRECOMPILED_HEADER: %s" % header_path)
                    elif key == "platform_win32":
                        self._process_platform_config(match.group(1), "win32")
                    elif key == "platform_unix":
                        self._process_platform_config(match.group(1), "unix")
                    elif key == "platform_macx":
                        self._process_platform_config(match.group(1), "macx")
                    elif key == "testcase":
                        self.global_config["testcase"] = True
                        self.global_config["type"] = "test_executable"
                        logger.debug("Enabled testcase: module_type set to test_executable")
                    elif key == "cxxflags_release":
                        if self.release_config:
                            for flag in value.split():
                                if flag not in self.global_config["compile_flags"] and not flag.endswith((".pro", ".prf")) and flag != "prf":
                                    self.global_config["compile_flags"].add(flag)
                            logger.debug("Added CXXFLAGS_RELEASE: %s" % value)
                    elif key == "cxxflags_debug":
                        if self.debug_config:
                            for flag in value.split():
                                if flag not in self.global_config["compile_flags"] and not flag.endswith((".pro", ".prf")) and flag != "prf":
                                    self.global_config["compile_flags"].add(flag)
                            logger.debug("Added CXXFLAGS_DEBUG: %s" % value)
                    elif key == "distfiles":
                        for distfile in value.split():
                            distfile_path = self._post_normalize_path(self.context.normalize_path(
                                distfile,
                                working_dir=self.context.source_dir,
                                ignore_working_dir=False
                            ))
                            self.global_config["distfiles"].add(distfile_path)
                            content = self._read_file_content(distfile_path)
                            if content is not None:
                                self.build_object_model.append({
                                    "content": content,
                                    "output": distfile_path,
                                    "dependencies": [],
                                    "type": "file"
                                })
                            logger.debug("Added DISTFILE: %s" % distfile_path)
                    elif key == "version":
                        self.global_config["version"] = value
                        logger.debug("Set VERSION: %s" % value)
                    elif key == "extra_compilers":
                        for compiler in value.split():
                            if compiler not in self.custom_compilers:
                                self.custom_compilers[compiler] = {"input": [], "output": "", "commands": "", "variable": ""}
                    elif key == "compiler_input":
                        compiler_name, inputs = value
                        if compiler_name not in self.custom_compilers:
                            self.custom_compilers[compiler_name] = {"input": [], "output": "", "commands": "", "variable": ""}
                        self.custom_compilers[compiler_name]["input"] = [self._post_normalize_path(self.context.normalize_path(input, working_dir=self.context.source_dir, ignore_working_dir=False)) for input in inputs.split()] if inputs else []
                    elif key == "compiler_output":
                        compiler_name, output = value
                        if compiler_name not in self.custom_compilers:
                            self.custom_compilers[compiler_name] = {"input": [], "output": "", "commands": "", "variable": ""}
                        self.custom_compilers[compiler_name]["output"] = self._post_normalize_path(self.context.normalize_path(output, ignore_working_dir=False))
                    elif key == "compiler_variable":
                        compiler_name, variable = value
                        if compiler_name not in self.custom_compilers:
                            self.custom_compilers[compiler_name] = {"input": [], "output": "", "commands": "", "variable": ""}
                        self.custom_compilers[compiler_name]["variable"] = variable
                    elif key == "commands":
                        target_name, commands = value
                        self.commands[target_name] = commands
                        if target_name in self.post_targetdeps:
                            self.post_targetdeps[target_name]["commands"] = commands
                        elif target_name in self.custom_targets_info:
                            self.custom_targets_info[target_name]["commands"] = commands
                        elif target_name in self.custom_compilers:
                            self.custom_compilers[target_name]["commands"] = commands
                        else:
                            self.custom_targets_info[target_name] = {"target": target_name, "commands": commands, "depends": []}
                    elif key == "extra_targets":
                        for target_name in value.split():
                            if target_name not in self.custom_targets_info:
                                self.custom_targets_info[target_name] = {"target": "", "commands": "", "depends": []}
                    elif key == "target_target":
                        target_name, target = value
                        if target_name in self.custom_targets_info:
                            self.custom_targets_info[target_name]["target"] = target
                        elif target_name in self.custom_compilers:
                            self.custom_compilers[target_name]["target"] = target
                        else:
                            self.custom_targets_info[target_name] = {"target": target, "commands": "", "depends": []}
                    elif key == "target_depends":
                        target_name, depends = value
                        if target_name in self.custom_targets_info:
                            self.custom_targets_info[target_name]["depends"] = depends.split()
                        elif target_name in self.custom_compilers:
                            self.custom_compilers[target_name]["depends"] = depends.split()
                    elif key == "pre_targetdeps":
                        for dep in value.split():
                            normalized_dep = self._post_normalize_path(self.context.normalize_path(dep, ignore_working_dir=True))
                            for target_name, info in self.custom_targets_info.items():
                                if info["target"] == dep:
                                    self._process_custom_target(target_name, info["target"], info["commands"], info["depends"])
                                    break
                    elif key == "post_targetdeps":
                        for target_name in value.split():
                            if target_name not in self.post_targetdeps:
                                self.post_targetdeps[target_name] = {"target": target_name, "commands": "", "depends": []}
                                if target_name in self.custom_targets_info:
                                    self.post_targetdeps[target_name]["depends"] = self.custom_targets_info[target_name]["depends"]
                                    self.post_targetdeps[target_name]["target"] = self.custom_targets_info[target_name]["target"]
                    target["line"] = ""

        if is_eof:
            logger.debug("build_object_model before save: %s" % self.build_object_model)
            self.context.build_object_model = self.build_object_model
            logger.debug("context.build_object_model after save: %s" % self.context.build_object_model)

            for compiler_name, info in self.custom_compilers.items():
                if info["input"] and info["output"]:
                    self._process_custom_command(compiler_name, info["input"], info["output"], self.commands[compiler_name])
            for target_name, info in self.custom_targets_info.items():
                if info["target"]:
                    self._process_custom_target(target_name, info["target"], self.commands[target_name], info["depends"])
            for target_name, info in self.post_targetdeps.items():
                if info["target"]:
                    self._process_custom_target(target_name, info["target"], self.commands[target_name], info["depends"])
            if {"type": "directory", "output": "@build_dir@/_build", "dependencies": None} not in self.build_object_model:
                self.build_object_model.append({
                    "type": "directory",
                    "output": "@build_dir@/_build",
                    "dependencies": None
                })

            if self.global_config["type"] == "subdirs":
                for subdir in self.global_config["subdirs"]:
                    subdir_path = self._post_normalize_path(self.context.normalize_path(
                        os.path.join(subdir, f"{os.path.basename(subdir)}.pro"),
                        working_dir=self.context.source_dir,
                        ignore_working_dir=False
                    ))
                    self.build_object_model.append({
                        "type": "subproject",
                        "output": subdir_path,
                        "dependencies": [],
                        "module_type": "subdirs"
                    })
                    logger.info("Added subproject: %s" % subdir_path)
            elif self.global_config["target"] and self.global_config["sources"]:
                target_output = self._post_normalize_path(self.context.normalize_path(
                    os.path.join(self.global_config["destdir"], self.global_config["target"]),
                    working_dir=self.context.source_dir,
                    ignore_working_dir=True
                ))
                dependencies = list(set(
                    ["@build_dir@/_build"] +
                    list(self.global_config["sources"]) +
                    list(self.global_config["headers"]) +
                    list(self.global_config["forms"]) +
                    list(self.global_config["resources"]) +
                    list(self.ui_headers) +
                    list(self.moc_sources) +
                    list(self.rcc_sources) +
                    [cmd["output"] for cmd in self.global_config["custom_commands"]] +
                    [tgt["name"] for tgt in self.global_config["custom_targets"]]
                ))
                if self.global_config["precompiled_header"]:
                    dependencies.append(self.global_config["precompiled_header"])
                self.build_object_model.append({
                    "msvc_import_lib": None,
                    "link_flags": sorted(self.global_config["link_flags"]),
                    "compile_flags": [],
                    "include_dirs": [],
                    "sources": [{
                        "path": source_path,
                        "dependencies": [],
                        "compile_flags": sorted(self.global_config["compile_flags"]) if source_path.endswith((".cpp", ".cc", ".cxx", ".ui", ".qrc")) else [],
                        "language": "C++" if source_path.endswith((".cpp", ".cc", ".cxx")) else None,
                        "include_dirs": self._get_include_dirs() if source_path.endswith((".cpp", ".cc", ".cxx", ".ui", ".qrc")) else []
                    } for source_path in sorted(self.global_config["sources"])],
                    "objects": [],
                    "module_type": self.global_config["type"],
                    "dependencies": dependencies,
                    "libs": sorted(self.global_config["libs"]),
                    "name": self.global_config["target"],
                    "version": self.global_config["version"],
                    "compatibility_version": self.global_config["version"].split('.')[0] if self.global_config["version"] else None,
                    "output": target_output,
                    "type": "module"
                })
                logger.info("Added target: %s (type: %s)" % (self.global_config["target"], self.global_config["type"]))
                self.context.build_object_model = self.build_object_model
            elif not self.global_config["target"]:
                logger.warning("Skipped final target: TARGET not specified in log")
            elif not self.global_config["sources"]:
                logger.warning("Skipped final target: No sources")

        target["working_dir"] = self.context.working_dir
        return self.build_object_model

__all__ = ["QmakeLogParser"]
