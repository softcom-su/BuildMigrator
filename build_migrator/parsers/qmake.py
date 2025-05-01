from __future__ import print_function
import re
import logging
import os
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
            "resources": re.compile(r"DEBUG 1: .+?\.prf:\d+: RESOURCES := (.+)"),
            "includepath": re.compile(r"DEBUG 1: .+?\.prf:\d+: INCLUDEPATH := (.+)"),
            "libs": re.compile(r"DEBUG 1: .+?\.prf:\d+: LIBS := (.+)"),
            "target": re.compile(r"DEBUG 1: .+?\.pro:\d+: TARGET := (.+)"),
            "template": re.compile(r"DEBUG 1: .+?\.pro:\d+: TEMPLATE := (.+)"),
            "cxx": re.compile(r"DEBUG 1: .+?\.pro:\d+: QMAKE_CXX := (.+)"),
            "cxxflags": re.compile(r"DEBUG 1: .+?\.prf:\d+: QMAKE_CXXFLAGS := (.+)"),
            "defines": re.compile(r"DEBUG 1: .+?\.prf:\d+: DEFINES := (.+)"),
            "config": re.compile(r"DEBUG 1: .+?\.prf:\d+: CONFIG := (.+)"),
        }
        self.global_config = {
            "includes": [],
            "libs": [],
            "target": None,
            "compiler": "g++",
            "compile_flags": [],
            "link_flags": [],
            "type": "executable",
            "headers": [],
            "sources": [],
            "forms": [],
        }
        self.build_object_model = []
        self.processed_sources = set()
        self.processed_headers = set()
        self.processed_forms = set()
        self.processed_resources = set()
        self.ui_headers = []
        self.moc_sources = []
        self.processed_lines = set()
        self.is_qt_project = False

    def _read_file_content(self, path):
        try:
            full_path = path.replace("@source_dir@", self.context.source_dir).replace("@build_dir@", self.context.build_dirs[0])
            with open(full_path, "r") as f:
                content = f.read()
                logger.debug("Read content for %s (%d bytes)" % (path, len(content)))
                return content
        except IOError as e:
            logger.warning("Cannot read file %s: %s" % (path, str(e)))
            return None

    def _get_include_dirs(self):
        include_dirs = set(self.global_config["includes"] + ["@source_dir@"])
        for header in self.global_config["headers"]:
            header_dir = os.path.dirname(header)
            if header_dir and header_dir not in include_dirs:
                include_dirs.add(header_dir)
        concrete_source_dir = self.context.source_dir
        include_dirs = set([d for d in include_dirs if d != "@source_dir@" or d == concrete_source_dir])
        return sorted(list(include_dirs))

    def _check_for_qobject(self, content):
        return content and "Q_OBJECT" in content

    def _ensure_qt_settings(self):
        if self.is_qt_project:
            for flag in ["-O2", "-fPIC", "-Wall", "-Wextra", "-D_REENTRANT", "-DQT_NO_DEBUG", "-DQT_WIDGETS_LIB", "-DQT_GUI_LIB", "-DQT_CORE_LIB"]:
                if flag not in self.global_config["compile_flags"]:
                    self.global_config["compile_flags"].append(flag)
            for lib in ["Qt5::Widgets", "Qt5::Gui", "Qt5::Core", "OpenGL::GL", "Threads::Threads"]:
                if lib not in self.global_config["libs"]:
                    self.global_config["libs"].append(lib)
            for inc in [
                "/usr/include/x86_64-linux-gnu/qt5",
                "/usr/include/x86_64-linux-gnu/qt5/QtWidgets",
                "/usr/include/x86_64-linux-gnu/qt5/QtGui",
                "/usr/include/x86_64-linux-gnu/qt5/QtCore",
                "/usr/lib/x86_64-linux-gnu/qt5/mkspecs/linux-g++"
            ]:
                if inc not in self.global_config["includes"]:
                    self.global_config["includes"].append(inc)
            if "-Wl,-O1" not in self.global_config["link_flags"]:
                self.global_config["link_flags"].append("-Wl,-O1")
            logger.debug("Applied Qt settings: libs=%s, flags=%s, includes=%s" % (
                self.global_config["libs"], self.global_config["compile_flags"], self.global_config["includes"]))

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
                    value = match.group(1).strip()
                    if not value:
                        logger.warning("Empty value for %s in line: %s" % (key, line))
                        continue

                    if key == "sources":
                        for source in value.split():
                            if source.endswith((".cpp", ".cc", ".cxx")):
                                source_path = self.context.normalize_path(source)
                                if source_path in self.processed_sources:
                                    logger.debug("Skipping already processed source: %s" % source_path)
                                    continue
                                self.processed_sources.add(source_path)
                                self.global_config["sources"].append(source_path)
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
                                header_path = self.context.normalize_path(header)
                                if header_path in self.processed_headers:
                                    logger.debug("Skipping already processed header: %s" % header_path)
                                    continue
                                self.processed_headers.add(header_path)
                                self.global_config["headers"].append(header_path)
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
                                    moc_path = os.path.join("@build_dir@/_build", "moc_%s.cpp" % os.path.basename(header_path).rsplit('.', 1)[0])
                                    if moc_path not in self.moc_sources:
                                        self.moc_sources.append(moc_path)
                                        logger.debug("Added moc source for AUTOMOC: %s for header: %s" % (moc_path, header_path))
                                logger.debug("Added header: %s, dir: %s" % (header_path, os.path.dirname(header_path)))
                    elif key == "forms":
                        for form in value.split():
                            if not form.endswith(".ui"):
                                logger.warning("Invalid FORMS file: %s" % form)
                                continue
                            self.is_qt_project = True
                            form_path = self.context.normalize_path(form)
                            if form_path in self.processed_forms:
                                logger.debug("Skipping already processed form: %s" % form_path)
                                continue
                            self.processed_forms.add(form_path)
                            self.global_config["forms"].append(form_path)
                            self.global_config["sources"].append(form_path)
                            base_name = os.path.basename(form).rsplit('.', 1)[0]
                            output = "@build_dir@/_build/ui_" + base_name + ".h"
                            if output not in self.ui_headers:
                                self.ui_headers.append(output)
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
                            resource_path = self.context.normalize_path(resource)
                            if resource_path in self.processed_resources:
                                logger.debug("Skipping already processed resource: %s" % resource_path)
                                continue
                            self.processed_resources.add(resource_path)
                            self.global_config["sources"].append(resource_path)
                            base_name = os.path.basename(resource).rsplit('.', 1)[0]
                            output = "@build_dir@/_build/qrc_" + base_name + ".cpp"
                            if output not in self.processed_sources:
                                self.processed_sources.add(output)
                                self.global_config["sources"].append(output)
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
                    elif key == "includepath":
                        paths = [self.context.normalize_path(p) for p in value.split()]
                        for path in paths:
                            if path not in self.global_config["includes"]:
                                self.global_config["includes"].append(path)
                                logger.debug("Added INCLUDEPATH: %s" % path)
                    elif key == "libs":
                        for lib in value.split():
                            if lib.startswith("-l"):
                                lib_name = lib[2:]
                                if lib_name not in self.global_config["libs"]:
                                    self.global_config["libs"].append(lib_name)
                            elif lib.startswith("-L"):
                                include_path = self.context.normalize_path(lib[2:])
                                if include_path not in self.global_config["includes"]:
                                    self.global_config["includes"].append(include_path)
                            else:
                                if lib not in self.global_config["libs"]:
                                    self.global_config["libs"].append(lib)
                            logger.debug("Added LIB: %s" % lib)
                    elif key == "target":
                        self.global_config["target"] = value.strip() or None
                        logger.debug("Set TARGET: %s" % self.global_config["target"])
                    elif key == "template":
                        self.global_config["type"] = "executable" if value == "app" else "shared_library"
                        logger.debug("Set TEMPLATE: %s" % self.global_config["type"])
                    elif key == "cxx":
                        self.global_config["compiler"] = value
                        logger.debug("Set CXX: %s" % value)
                    elif key == "cxxflags":
                        flags = value.split()
                        for flag in flags:
                            if flag not in self.global_config["compile_flags"]:
                                self.global_config["compile_flags"].append(flag)
                        logger.debug("Added CXXFLAGS: %s" % flags)
                    elif key == "defines":
                        for define in value.split():
                            if define.strip() and "-D" + define.strip() not in self.global_config["compile_flags"]:
                                self.global_config["compile_flags"].append("-D" + define.strip())
                            else:
                                logger.warning("Skipped invalid or duplicate DEFINE: '%s'" % define)
                    elif key == "config":
                        config_values = value.split()
                        logger.debug("Processing CONFIG line: %s" % line)
                        if "gcc" in config_values and not self.patterns["cxx"].search(line):
                            self.global_config["compiler"] = "g++"
                        if "c++17" in config_values or "c++1z" in config_values:
                            if "-std=gnu++1z" not in self.global_config["compile_flags"]:
                                self.global_config["compile_flags"].append("-std=gnu++1z")
                        if "debug" in config_values and "release" not in config_values:
                            if "-g" not in self.global_config["compile_flags"]:
                                self.global_config["compile_flags"].append("-g")
                        if "release" in config_values and "debug" not in config_values:
                            for flag in ["-O2", "-fPIC"]:
                                if flag not in self.global_config["compile_flags"]:
                                    self.global_config["compile_flags"].append(flag)
                            if "-Wl,-O1" not in self.global_config["link_flags"]:
                                self.global_config["link_flags"].append("-Wl,-O1")
                        if "qt" in config_values or "Qt" in value:
                            self.is_qt_project = True
                        if "warn_on" in config_values:
                            for flag in ["-Wall", "-Wextra"]:
                                if flag not in self.global_config["compile_flags"]:
                                    self.global_config["compile_flags"].append(flag)
                        logger.debug("Processed CONFIG: %s" % config_values)
                    target["line"] = ""

        if is_eof:
            self._ensure_qt_settings()
            logger.debug("build_object_model before save: %s" % self.build_object_model)
            self.context.build_object_model = self.build_object_model
            logger.debug("context.build_object_model after save: %s" % self.context.build_object_model)
            
            if self.global_config["target"] and self.global_config["sources"]:
                target_output = os.path.join("@build_dir@/_build", self.global_config["target"])
                dependencies = list(set(
                    self.global_config["sources"] +
                    self.global_config["headers"] +
                    self.global_config["forms"] +
                    self.ui_headers
                ))
                self.build_object_model.append({
                    "msvc_import_lib": None,
                    "link_flags": list(set(self.global_config["link_flags"])),
                    "compile_flags": [],
                    "sources": [{
                        "path": source_path,
                        "dependencies": None,
                        "compile_flags": list(set(self.global_config["compile_flags"])) if source_path.endswith((".cpp", ".cc", ".cxx")) else [],
                        "language": "C++" if source_path.endswith((".cpp", ".cc", ".cxx")) else None,
                        "include_dirs": self._get_include_dirs() if source_path.endswith((".cpp", ".cc", ".cxx")) else []
                    } for source_path in self.global_config["sources"]],
                    "objects": [],
                    "module_type": self.global_config["type"],
                    "dependencies": None,
                    "libs": list(set(self.global_config["libs"])),
                    "include_dirs": self._get_include_dirs(),
                    "compatibility_version": None,
                    "name": self.global_config["target"],
                    "version": None,
                    "output": target_output,
                    "type": "module"
                })
                logger.info("Added executable target: %s" % self.global_config["target"])
                self.context.build_object_model = self.build_object_model
            elif not self.global_config["target"]:
                logger.warning("Skipped final target: TARGET not specified in log")
            elif not self.global_config["sources"]:
                logger.warning("Skipped final target: No sources")

        target["working_dir"] = self.context.working_dir
        return self.build_object_model

__all__ = ["QmakeLogParser"]
