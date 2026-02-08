"""Generate Surge configs by reusing base Surge config structure."""

from __future__ import annotations

import os
import httpx
import ruamel.yaml

from surge_config import SurgeConfig, SurgeKeyValue, SurgeSection, SurgeRawLine


yaml = ruamel.yaml.YAML()
yaml.indent(mapping=4)
yaml.encoding = "utf-8"
yaml.default_flow_style = False
yaml.allow_unicode = True

HEADERS = {"user-agent": "surge/5.0"}


def _make_transport(proxy_url: str | None) -> httpx.HTTPTransport:
    if proxy_url:
        return httpx.HTTPTransport(proxy=httpx.Proxy(proxy_url))
    return httpx.HTTPTransport()


def _rewrite_rule_targets(rules: list[str], target_map: dict[str, str]) -> list[str]:
    if not rules:
        return []
    rewritten: list[str] = []
    for rule in rules:
        if not isinstance(rule, str) or "," not in rule:
            rewritten.append(rule)
            continue
        parts = [part.strip() for part in rule.split(",")]
        if not parts:
            rewritten.append(rule)
            continue
        target = parts[-1]
        mapped = None
        if target.startswith("{") and target.endswith("}"):
            key = target[1:-1].strip().lower()
            mapped = target_map.get(key)
        if mapped:
            parts[-1] = mapped
            rewritten.append(",".join(parts))
        else:
            rewritten.append(rule)
    return rewritten


def _parse_group_value(value: str) -> tuple[str, list[str], list[str]]:
    tokens = [token.strip() for token in value.split(",") if token.strip()]
    if not tokens:
        return "select", [], []
    gtype = tokens[0]
    proxies: list[str] = []
    options: list[str] = []
    for token in tokens[1:]:
        if "=" in token:
            options.append(token)
        else:
            proxies.append(token)
    return gtype, proxies, options


def _render_group_value(gtype: str, proxies: list[str], options: list[str]) -> str:
    parts = [gtype] + proxies + options
    return ", ".join(parts)


def _render_proxy_value(proxy: dict) -> str:
    payload = dict(proxy)
    name = payload.pop("name", None)
    ptype = payload.pop("type", None)
    if not name or not ptype:
        raise ValueError("Surge proxy must include name and type")
    parts = [ptype]
    positional = []
    keyed = []
    for key, value in payload.items():
        if key in {"server", "host"}:
            positional.append(str(value))
        elif key == "port":
            positional.append(str(value))
        else:
            keyed.append(f"{key}={value}")
    parts.extend(positional)
    parts.extend(keyed)
    return ", ".join(parts)


def _extract_proxy_entries(config: SurgeConfig) -> list[SurgeKeyValue]:
    section = config.get_section("Proxy")
    if not section:
        return []
    return [entry for entry in section.entries if isinstance(entry, SurgeKeyValue)]


def _extract_group_entries(config: SurgeConfig) -> list[SurgeKeyValue]:
    section = config.get_section("Proxy Group")
    if not section:
        return []
    return [entry for entry in section.entries if isinstance(entry, SurgeKeyValue)]


def _apply_proxies_and_groups(
    config: SurgeConfig,
    *,
    custom_proxies: list[dict],
    extra_proxy_entries: list[SurgeKeyValue],
    main_select: str | None,
    special_groups: dict,
    include_extra_in_select: bool,
    create_white_group: bool,
    white_group_name: str,
) -> None:
    system_proxies = {"DIRECT", "REJECT"}
    for name in (special_groups or {}).values():
        if name:
            system_proxies.add(name)
    if main_select:
        system_proxies.add(main_select)
    if create_white_group:
        system_proxies.add(white_group_name)

    # Reset Proxy section
    proxy_section = _ensure_section(config, "Proxy")
    proxy_section.entries = []

    custom_names: list[str] = []
    for proxy in custom_proxies:
        if not isinstance(proxy, dict):
            continue
        name = proxy.get("name")
        if not name:
            continue
        value = _render_proxy_value(proxy)
        proxy_section.set(name, value)
        custom_names.append(name)

    extra_names: list[str] = []
    for entry in extra_proxy_entries:
        proxy_section.set(entry.key, entry.value)
        extra_names.append(entry.key)

    # Update Proxy Group section
    group_section = _ensure_section(config, "Proxy Group")
    for entry in group_section.entries:
        if not isinstance(entry, SurgeKeyValue):
            continue
        gtype, proxies, options = _parse_group_value(entry.value)
        proxies = [p for p in proxies if p in system_proxies]
        if gtype == "select":
            for name in custom_names:
                if name not in proxies:
                    proxies.append(name)
            if include_extra_in_select:
                for name in extra_names:
                    if name not in proxies:
                        proxies.append(name)
            if create_white_group and white_group_name not in proxies:
                proxies.append(white_group_name)
        entry.value = _render_group_value(gtype, proxies, options)


def _add_white_group(
    config: SurgeConfig,
    white_group_name: str,
    white_proxy_names: list[str],
) -> None:
    if not white_proxy_names:
        return
    group_section = _ensure_section(config, "Proxy Group")
    # Remove existing white group if present
    group_section.entries = [
        entry for entry in group_section.entries
        if not (isinstance(entry, SurgeKeyValue) and entry.key == white_group_name)
    ]
    value = _render_group_value(
        "url-test",
        white_proxy_names,
        ["url=http://www.gstatic.com/generate_204", "interval=600"],
    )
    group_section.set(white_group_name, value)


def _ensure_section(config: SurgeConfig, name: str) -> SurgeSection:
    section = config.get_section(name)
    if section is None:
        section = SurgeSection(name=name)
        config.sections[name] = section
    return section


def main() -> None:
    with open("common_config.yaml", "r", encoding="utf-8") as f:
        common_config = yaml.load(f) or {}

    with open("surge_config.yaml", "r", encoding="utf-8") as f:
        surge_config = yaml.load(f) or {}

    base_sub = surge_config.get("base_sub")
    if not base_sub:
        print("错误: surge.base_sub 未配置")
        return

    output = surge_config.get("output")
    if not output:
        print("错误: surge.output 未配置")
        return

    if output.endswith(".conf"):
        output_extra = output[:-5] + "_extra.conf"
    else:
        output_extra = output + "_extra"

    ua = surge_config.get("user_agent") or HEADERS["user-agent"]
    proxy_url = common_config.get("http_proxy")

    print(f"正在下载 Surge 基础配置")
    transport = _make_transport(proxy_url)
    with httpx.Client(headers={"user-agent": ua}, transport=transport, timeout=30.0, follow_redirects=True) as client:
        r = client.get(base_sub)
        r.raise_for_status()
        base_text = r.text

    # Create two independent configs for standard and extra outputs
    surge_standard = SurgeConfig.from_text(base_text)
    surge_extra = SurgeConfig.from_text(base_text)

    proxy_groups_cfg = surge_config.get("proxy_groups", {})
    main_select = proxy_groups_cfg.get("main_select")
    special_groups = proxy_groups_cfg.get("special_groups", {})

    custom_proxies = surge_config.get("proxies", [])

    # Standard config: only custom proxies
    _apply_proxies_and_groups(
        surge_standard,
        custom_proxies=custom_proxies,
        extra_proxy_entries=[],
        main_select=main_select,
        special_groups=special_groups,
        include_extra_in_select=False,
        create_white_group=False,
        white_group_name="White",
    )

    # Rules: prepend custom rules with placeholder replacement
    target_map: dict[str, str] = {}
    if main_select:
        target_map["proxy"] = main_select
    if special_groups.get("domestic"):
        target_map["domestic"] = special_groups.get("domestic")
    if special_groups.get("ai"):
        target_map["ai"] = special_groups.get("ai")
    if special_groups.get("adblock"):
        target_map["adblock"] = special_groups.get("adblock")

    custom_rules = surge_config.get("rules", [])
    custom_rules = _rewrite_rule_targets(custom_rules, target_map)

    for cfg in (surge_standard, surge_extra):
        rule_section = _ensure_section(cfg, "Rule")
        if custom_rules:
            new_entries = [SurgeRawLine(content=rule) for rule in custom_rules]
            rule_section.entries = new_entries + rule_section.entries

    # Load extra proxies from third-party sources
    sources = surge_config.get("sources", [])
    extra_proxy_entries: list[SurgeKeyValue] = []
    if sources:
        print(f"正在下载 {len(sources)} 个第三方订阅...")
        for source in sources:
            try:
                transport = _make_transport(proxy_url)
                with httpx.Client(headers={"user-agent": ua}, transport=transport, timeout=30.0, follow_redirects=True) as client:
                    r = client.get(source)
                    r.raise_for_status()
                remote_cfg = SurgeConfig.from_text(r.text)
                entries = _extract_proxy_entries(remote_cfg)
                extra_proxy_entries.extend(entries)
                print(f"  从 {source[:50]}... 获取了 {len(entries)} 个节点")
            except Exception as e:
                print(f"  警告: 获取订阅失败 {source[:50]}... - {e}")

    proxies_blacklist = common_config.get("proxies_blacklist", []) or []
    if proxies_blacklist and extra_proxy_entries:
        filtered = []
        for entry in extra_proxy_entries:
            if not any(keyword in entry.key for keyword in proxies_blacklist):
                filtered.append(entry)
            else:
                print(f"  黑名单过滤: {entry.key}")
        extra_proxy_entries = filtered

    white_keywords = common_config.get("white_keywords", []) or []
    white_group_name = "White"
    if white_keywords and extra_proxy_entries:
        white_entries = [e for e in extra_proxy_entries if any(k in e.key for k in white_keywords)]
        if white_entries:
            print(f"  找到 {len(white_entries)} 个 White 节点")
            _apply_proxies_and_groups(
                surge_extra,
                custom_proxies=custom_proxies,
                extra_proxy_entries=white_entries,
                main_select=main_select,
                special_groups=special_groups,
                include_extra_in_select=False,
                create_white_group=True,
                white_group_name=white_group_name,
            )
            _add_white_group(surge_extra, white_group_name, [e.key for e in white_entries])
        else:
            _apply_proxies_and_groups(
                surge_extra,
                custom_proxies=custom_proxies,
                extra_proxy_entries=[],
                main_select=main_select,
                special_groups=special_groups,
                include_extra_in_select=False,
                create_white_group=False,
                white_group_name=white_group_name,
            )
    else:
        _apply_proxies_and_groups(
            surge_extra,
            custom_proxies=custom_proxies,
            extra_proxy_entries=extra_proxy_entries,
            main_select=main_select,
            special_groups=special_groups,
            include_extra_in_select=True,
            create_white_group=False,
            white_group_name=white_group_name,
        )

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(surge_standard.to_text())

    with open(output_extra, "w", encoding="utf-8") as f:
        f.write(surge_extra.to_text())

    print("\n完成!")
    print(f"  Surge 标准配置: {output}")
    print(f"  Surge 扩展配置: {output_extra}")


if __name__ == "__main__":
    main()
