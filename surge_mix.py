"""Generate a Surge configuration that reuses dlercloud's rules."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

import httpx
import ruamel.yaml

from surge_config import SurgeConfig, SurgeRawLine


def _create_yaml() -> ruamel.yaml.YAML:
    yaml = ruamel.yaml.YAML()
    yaml.indent(mapping=4)
    yaml.encoding = "utf-8"
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    return yaml


yaml = _create_yaml()

HEADERS = {"user-agent": "surge-ver/5.0"}


@dataclass
class SurgeProxy:
    """Representation of a custom Surge proxy entry."""

    name: str
    type: str
    options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SurgeProxy":
        payload = dict(data)
        name = payload.pop("name")
        type_ = payload.pop("type")
        return cls(name=name, type=type_, options=payload)

    def render_value(self) -> str:
        parts: List[str] = [self.type]
        positional: List[str] = []
        keyed: List[str] = []
        for key, value in self.options.items():
            if key in {"server", "host"}:
                positional.append(str(value))
            elif key == "port":
                positional.append(str(value))
            else:
                keyed.append(f"{key}={_format_value(value)}")
        parts.extend(positional)
        parts.extend(keyed)
        return ", ".join(parts)


@dataclass
class SurgeProxyGroup:
    """Representation of a custom Surge proxy group."""

    name: str
    type: str
    proxies: List[str] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SurgeProxyGroup":
        payload = dict(data)
        name = payload.pop("name")
        type_ = payload.pop("type")
        proxies = list(payload.pop("proxies", []))
        return cls(name=name, type=type_, proxies=proxies, options=payload)

    def render_value(self) -> str:
        parts: List[str] = [self.type]
        parts.extend(self.proxies)
        for key, value in self.options.items():
            parts.append(f"{key}={_format_value(value)}")
        return ", ".join(parts)


@dataclass
class SurgeCustomConfig:
    """User-provided configuration for Surge processing."""

    output: str
    base_sub: str
    proxies: List[SurgeProxy] = field(default_factory=list)
    proxy_groups: List[SurgeProxyGroup] = field(default_factory=list)
    rules: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SurgeCustomConfig":
        output = data["output"]
        base_sub = data["base_sub"]
        proxies = [SurgeProxy.from_dict(item) for item in data.get("proxies", [])]
        proxy_groups = [
            SurgeProxyGroup.from_dict(item) for item in data.get("proxy_groups", [])
        ]
        rules = list(data.get("rules", []))
        return cls(
            output=output,
            base_sub=base_sub,
            proxies=proxies,
            proxy_groups=proxy_groups,
            rules=rules,
        )


def load_custom_config(path: str = "custom_config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.load(handle)


def fetch_base_config(url: str) -> str:
    with httpx.Client(headers=HEADERS, timeout=30.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def ensure_parent_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def apply_custom_proxies(config: SurgeConfig, proxies: List[SurgeProxy]) -> None:
    if not proxies:
        return
    section = config.ensure_section("Proxy")
    for proxy in proxies:
        section.set(proxy.name, proxy.render_value())


def apply_custom_proxy_groups(config: SurgeConfig, groups: List[SurgeProxyGroup]) -> None:
    if not groups:
        return
    section = config.ensure_section("Proxy Group")
    for group in groups:
        section.set(group.name, group.render_value())


def apply_custom_rules(config: SurgeConfig, rules: List[str]) -> None:
    if not rules:
        return
    section = config.ensure_section("Rule")
    for rule in rules:
        section.entries.append(SurgeRawLine(content=rule))


def process_surge_config(raw_config: Dict[str, Any]) -> SurgeConfig:
    custom = SurgeCustomConfig.from_dict(raw_config)
    base_text = fetch_base_config(custom.base_sub)
    surge_config = SurgeConfig.from_text(base_text)

    # The manipulation helpers mirror the Clash workflow but are intentionally
    # unused for now. Uncomment the following lines once the modification rules
    # are finalised.
    # apply_custom_proxies(surge_config, custom.proxies)
    # apply_custom_proxy_groups(surge_config, custom.proxy_groups)
    # apply_custom_rules(surge_config, custom.rules)

    ensure_parent_dir(custom.output)
    with open(custom.output, "w", encoding="utf-8") as handle:
        handle.write(surge_config.to_text())

    return surge_config


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


if __name__ == "__main__":
    config = load_custom_config()
    surge_section = config.get("surge")
    if surge_section:
        process_surge_config(surge_section)

