"""Utilities for parsing and manipulating Surge configuration files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional
from collections import OrderedDict


@dataclass
class SurgeEntry:
    """Base class for a parsed Surge configuration line."""

    def to_line(self) -> str:
        raise NotImplementedError


@dataclass
class SurgeEmptyLine(SurgeEntry):
    """Represents an empty line within a Surge section."""

    def to_line(self) -> str:
        return ""


@dataclass
class SurgeComment(SurgeEntry):
    """Represents a comment line."""

    content: str

    def to_line(self) -> str:
        return self.content


@dataclass
class SurgeRawLine(SurgeEntry):
    """Represents a raw line that should be preserved verbatim."""

    content: str

    def to_line(self) -> str:
        return self.content


@dataclass
class SurgeKeyValue(SurgeEntry):
    """Represents a key-value pair such as ``foo = bar``."""

    key: str
    value: str

    def to_line(self) -> str:
        return f"{self.key} = {self.value}"


@dataclass
class SurgeSection:
    """A parsed Surge section containing multiple entries."""

    name: str
    entries: List[SurgeEntry] = field(default_factory=list)

    def __iter__(self) -> Iterator[SurgeEntry]:
        return iter(self.entries)

    def get(self, key: str) -> Optional[SurgeKeyValue]:
        for entry in self.entries:
            if isinstance(entry, SurgeKeyValue) and entry.key == key:
                return entry
        return None

    def set(self, key: str, value: str) -> None:
        existing = self.get(key)
        if existing is not None:
            existing.value = value
        else:
            self.entries.append(SurgeKeyValue(key=key, value=value))

    def remove(self, key: str) -> None:
        self.entries = [
            entry
            for entry in self.entries
            if not (isinstance(entry, SurgeKeyValue) and entry.key == key)
        ]


class SurgeConfig:
    """In-memory representation of a Surge configuration file."""

    def __init__(
        self,
        *,
        managed_config: Optional[str] = None,
        preamble: Optional[List[str]] = None,
        sections: Optional[Dict[str, SurgeSection]] = None,
    ) -> None:
        self.managed_config = managed_config
        self.preamble = preamble or []
        self.sections: "OrderedDict[str, SurgeSection]" = OrderedDict()
        if sections:
            for name, section in sections.items():
                self.sections[name] = section

    def iter_section_names(self) -> Iterable[str]:
        return self.sections.keys()

    def get_section(self, name: str) -> Optional[SurgeSection]:
        return self.sections.get(name)

    def ensure_section(self, name: str) -> SurgeSection:
        section = self.get_section(name)
        if section is None:
            section = SurgeSection(name=name)
            self.sections[name] = section
        return section

    def to_text(self) -> str:
        lines: List[str] = []
        if self.managed_config:
            lines.append(self.managed_config)
        lines.extend(self.preamble)
        for section in self.sections.values():
            lines.append(f"[{section.name}]")
            lines.extend(entry.to_line() for entry in section.entries)
        text = "\n".join(lines)
        if text and not text.endswith("\n"):
            text += "\n"
        return text

    @classmethod
    def from_text(cls, text: str) -> "SurgeConfig":
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.split("\n")
        managed_config: Optional[str] = None
        sections: "OrderedDict[str, SurgeSection]" = OrderedDict()
        preamble: List[str] = []
        current_section: Optional[SurgeSection] = None

        for idx, line in enumerate(lines):
            if idx == 0 and line.startswith("#!MANAGED-CONFIG"):
                managed_config = line
                continue
            if line.startswith("[") and line.endswith("]") and len(line) > 2:
                section_name = line[1:-1]
                current_section = SurgeSection(name=section_name)
                sections[section_name] = current_section
                continue
            section_name = current_section.name if current_section else None
            entry = _parse_section_line(line, section_name)
            if current_section is None:
                preamble.append(entry.to_line())
            else:
                current_section.entries.append(entry)

        return cls(managed_config=managed_config, preamble=preamble, sections=sections)


def _parse_section_line(line: str, section: Optional[str]) -> SurgeEntry:
    if not line:
        return SurgeEmptyLine()
    stripped = line.lstrip()
    if not stripped:
        return SurgeEmptyLine()
    if stripped.startswith("#") or stripped.startswith(";"):
        return SurgeComment(content=line)
    if section in {"General", "Proxy", "Proxy Group", "Host"} and "=" in line:
        key, value = line.split("=", 1)
        return SurgeKeyValue(key=key.strip(), value=value.strip())
    return SurgeRawLine(content=line)

