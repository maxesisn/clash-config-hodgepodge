"""Generate a Surge configuration that reuses dlercloud's rules."""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import ruamel.yaml

from surge_config import SurgeConfig, SurgeRawLine
from converter import convert_proxies_to_surge, render_surge_proxy

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


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


def load_custom_config(path: str = "custom_config.yaml") -> tuple[Dict[str, Any], bool]:
    """
    加载配置文件，支持新旧两种格式

    Returns:
        (config, is_new_format): 配置字典和格式标识
    """
    with open(path, "r", encoding="utf-8") as handle:
        config = yaml.load(handle)

    # 检测配置格式
    if "surge" in config and isinstance(config["surge"], dict):
        logger.info("检测到Surge配置块")
        return config, True
    else:
        logger.info("未检测到Surge配置块（向后兼容模式）")
        return config, False


def get_surge_config(config: Dict[str, Any], is_new_format: bool) -> Optional[Dict[str, Any]]:
    """
    获取Surge配置参数

    Args:
        config: 完整配置
        is_new_format: 是否为新格式

    Returns:
        Surge配置参数，如果禁用则返回None
    """
    if is_new_format:
        surge_config = config.get("surge", {})

        # 检查是否启用
        if not surge_config.get("enabled", True):
            logger.info("Surge配置已禁用")
            return None

        # 获取统一节点配置
        unified_proxies = config.get("proxies", [])

        return {
            "output": surge_config.get("output"),
            "base_sub": surge_config.get("base_sub"),
            "proxies": unified_proxies,  # 使用统一节点配置（Clash格式）
            "rules": surge_config.get("rules", []),
        }
    else:
        # 旧格式兼容（从surge配置块读取）
        surge_section = config.get("surge")
        if surge_section:
            return surge_section
        else:
            logger.info("未找到surge配置块")
            return None


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


def process_surge_config(raw_config: Dict[str, Any], is_new_format: bool) -> SurgeConfig:
    """
    处理Surge配置生成

    Args:
        raw_config: Surge配置字典
        is_new_format: 是否为新格式（统一配置）
    """
    output = raw_config["output"]
    base_sub = raw_config["base_sub"]

    logger.info(f"Surge输出路径: {output}")
    logger.info(f"从基础订阅获取配置: {base_sub[:50]}...")

    # 下载基础配置
    base_text = fetch_base_config(base_sub)
    surge_config = SurgeConfig.from_text(base_text)

    if is_new_format:
        # 新格式：统一节点配置（Clash格式） + 转换
        clash_proxies = raw_config.get("proxies", [])
        logger.info(f"从统一配置获取 {len(clash_proxies)} 个节点（Clash格式）")

        # 转换为Surge格式
        surge_proxies_dict = convert_proxies_to_surge(clash_proxies)
        logger.info(f"成功转换 {len(surge_proxies_dict)} 个节点为Surge格式")

        # 应用节点
        if surge_proxies_dict:
            section = surge_config.ensure_section("Proxy")
            for surge_proxy in surge_proxies_dict:
                proxy_line = render_surge_proxy(surge_proxy.copy())
                # 分离名称和值
                name, _, value = proxy_line.partition(" = ")
                section.set(name, value)
                logger.info(f"  添加节点: {name}")

        # 应用自定义规则（可选）
        custom_rules = raw_config.get("rules", [])
        if custom_rules:
            logger.info(f"添加 {len(custom_rules)} 条自定义规则")
            apply_custom_rules(surge_config, custom_rules)
    else:
        # 旧格式：使用原有的SurgeCustomConfig处理
        custom = SurgeCustomConfig.from_dict(raw_config)
        logger.info(f"使用旧格式配置，{len(custom.proxies)} 个节点，{len(custom.proxy_groups)} 个代理组")

        # 应用自定义配置
        apply_custom_proxies(surge_config, custom.proxies)
        apply_custom_proxy_groups(surge_config, custom.proxy_groups)
        apply_custom_rules(surge_config, custom.rules)

    # 输出配置
    ensure_parent_dir(output)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(surge_config.to_text())

    logger.info(f"✓ Surge配置已生成: {output}")
    return surge_config


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


if __name__ == "__main__":
    # 加载配置
    config, is_new_format = load_custom_config()

    # 获取Surge配置
    surge_config_dict = get_surge_config(config, is_new_format)

    if surge_config_dict:
        try:
            process_surge_config(surge_config_dict, is_new_format)
            logger.info("✓ Surge配置处理完成")
        except Exception as e:
            logger.error(f"✗ Surge配置处理失败: {e}")
            raise
    else:
        logger.info("跳过Surge配置生成")

