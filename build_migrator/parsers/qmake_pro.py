import sys
import re
import json
import logging

try:
    from build_migrator.modules import Parser
except ImportError:
    class Parser(object):
        pass

logger = logging.getLogger(__name__)

class QmakeProParser(Parser):

    priority = 1

    @staticmethod
    def add_arguments(arg_parser):
        pass

    @staticmethod
    def is_applicable(log_type=None):
        return log_type == "qmake"

    def __init__(self, context):
        self.context = context
        self.file_path = re.compile(r"DEBUG 1: (/.+?\.pro):\d+:")
        self.get_file = False
        self.result = {
            "variables": {},
            "conditions": [],
            "includes": [],
            "errors": []
        }
        self.condition_stack = []
        self.variables = {}

        self.colon_cond_re = re.compile(r"^((?:!?\w+(?:-\w+)*(?:\([^\)]*\))?|\w+\([^\)]*\))(?:\s*:\s*(?:!?\w+(?:-\w+)*(?:\([^\)]*\))?|\w+\([^\)]*\)))*)\s*\{$")
        self.inline_cond_re = re.compile(r"^(else\s*:)?((?:!?\w+(?:-\w+)*(?:\([^\)]*\))?|\w+\([^\)]*\))(?:\s*:\s*(?:!?\w+(?:-\w+)*(?:\([^\)]*\))?|\w+\([^\)]*\)))*)\s*:")
        self.simple_cond_re = re.compile(r"^(!?\w+(?:\([^\)]*\))?(?:\s*,\s*!?\w+(?:\([^\)]*\))?)*)\s*\{$")
        self.else_re = re.compile(r"^\}?\s*else\s*\{?$")
        self.closing_brace_re = re.compile(r"^\}$")
        self.include_re = re.compile(r"^include\s*\(([^)]+)\)$")
        self.target = []

    
    def _substitute_variable(self, value):
        if not value or not isinstance(value, str):
            return value or ""
        
        def replace_match(match):
            var_name = match.group(1).lower()
            var_values = self.variables.get(var_name, [])
            if not var_values:
                return match.group(0)
            value = str(var_values[0])
            return value

        substituted = re.sub(r"\$\$(\w+)", replace_match, value)
        return substituted

    def _process_assignment(self, line):
        match = re.match(r"(\S+)\s+(\+=|\-=|=)\s*(.+)$", line)
        if not match:
            return None, None, None
        key = match.group(1).strip().lower()
        op = match.group(2)
        value = match.group(3).strip()
        values = [self._substitute_variable(v.strip("\\").strip()) for v in re.split(r"\s+", value) if v.strip("\\").strip()]
        return key, op, values
    
    def _read_lines(self, file):
        lines = []
        current_line = ""
        for line in file:
            line = line.rstrip("\n").rstrip()
            if line.endswith("\\"):
                current_line += line[:-1].strip() + " "
            else:
                current_line += line
                lines.append(current_line)
                current_line = ""
        if current_line:
            lines.append(current_line)
        return lines

    def parse(self, target):
        if self.get_file:
            return target
        
        line = target.get("line", "")
        if line:
            match = self.file_path.search(line)
            if match:
                file_path = match.group(1)
                self.get_file = True

                try:
                    with open(file_path, "r", encoding="utf-8") as file:

                        lines = self._read_lines(file)
                        for line_number, line in enumerate(lines, 1):
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue

                            include_match = self.include_re.match(line)
                            if include_match:
                                inc_file = self._substitute_variable(include_match.group(1))
                                self.result["includes"].append(inc_file)
                                logger.debug(f"Include: \"{inc_file}\"")
                                continue

                            colon_cond_match = self.colon_cond_re.match(line)
                            if colon_cond_match and line.strip().endswith("{"):
                                cond_str = colon_cond_match.group(1)
                                conds = [c.strip() for c in re.split(r"\s*:\s*", cond_str) if c.strip()]
                                new_block = {
                                    "condition": conds,
                                    "variables": {},
                                    "conditions": []
                                }
                                self.condition_stack.append(new_block)
                                continue

                            simple_cond_match = self.simple_cond_re.match(line)
                            if simple_cond_match:
                                cond_str = simple_cond_match.group(1)
                                conds = [c.strip() for c in cond_str.split(",")]
                                new_block = {
                                    "condition": conds,
                                    "variables": {},
                                    "conditions": []
                                }
                                self.condition_stack.append(new_block)
                                continue

                            inline_cond_match = self.inline_cond_re.match(line)
                            if inline_cond_match:
                                else_prefix = inline_cond_match.group(1) or ""
                                cond_str = inline_cond_match.group(2)
                                assign_str = line[inline_cond_match.end():].strip()
                                conds = [c.strip() for c in re.split(r"\s*:\s*", cond_str) if c.strip()]
                                if else_prefix:
                                    conds.insert(0, "else")
                                key, op, values = self._process_assignment(assign_str)
                                if key:
                                    new_cond = {
                                        "condition": conds,
                                        "variables": {},
                                        "conditions": []
                                    }
                                    key_clean = key.replace("+", "").strip()
                                    if op == "+=":
                                        if key_clean not in new_cond["variables"]:
                                            new_cond["variables"][key_clean] = []
                                        if key_clean not in self.variables:
                                            self.variables[key_clean] = []
                                        new_cond["variables"][key_clean].extend([v for v in values if v not in new_cond["variables"][key_clean]])
                                        self.variables[key_clean].extend([v for v in values if v not in self.variables[key_clean]])
                                    elif op == "-=":
                                        pass
                                    else:
                                        new_cond["variables"][key_clean] = values
                                        self.variables[key_clean] = values
                                    if self.condition_stack:
                                        self.condition_stack[-1]["conditions"].append(new_cond)
                                    else:
                                        self.result["conditions"].append(new_cond)
                                continue

                            if self.else_re.match(line):
                                if self.condition_stack:
                                    block = self.condition_stack.pop()
                                    if self.condition_stack:
                                        self.condition_stack[-1]["conditions"].append(block)
                                    else:
                                        self.result["conditions"].append(block)
                                else_block = {
                                    "condition": ["else"],
                                    "variables": {},
                                    "conditions": []
                                }
                                self.condition_stack.append(else_block)
                                continue

                            if self.closing_brace_re.match(line):
                                if self.condition_stack:
                                    block = self.condition_stack.pop()
                                    if self.condition_stack:
                                        self.condition_stack[-1]["conditions"].append(block)
                                    else:
                                        self.result["conditions"].append(block)
                                continue

                            key, op, values = self._process_assignment(line)
                            if key:
                                target_vars = self.condition_stack[-1]["variables"] if self.condition_stack else self.result["variables"]
                                key_clean = key.replace("+", "").strip()
                                if op == "+=":
                                    if key_clean not in target_vars:
                                        target_vars[key_clean] = []
                                    if key_clean not in self.variables:
                                        self.variables[key_clean] = []
                                    target_vars[key_clean].extend([v for v in values if v not in target_vars[key_clean]])
                                    self.variables[key_clean].extend([v for v in values if v not in self.variables[key_clean]])
                                elif op == "-=":
                                    pass
                                else:
                                    target_vars[key_clean] = values
                                    self.variables[key_clean] = values

                except FileNotFoundError as e:
                    return self.result
                except Exception as e:
                    return self.result

                while self.condition_stack:
                    block = self.condition_stack.pop()
                    if self.condition_stack:
                        self.condition_stack[-1]["conditions"].append(block)
                    else:
                        self.result["conditions"].append(block)

                self.target = {
                    "conditions": self.result["conditions"],
                    "line": target.get("line", "")
                }
                self.context.build_object_model = self.target

        return self.target

__all__ = ["QmakeProParser"]
