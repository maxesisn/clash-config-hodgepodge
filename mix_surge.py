"""Generate Surge configs by reusing base Surge config structure.

Workflow (mirrors mix_clash.py):
1. Read config_common.yaml + config_surge.yaml
2. Resolve active subscription group (base_sub_groups / active_group)
3. Download base Surge config from airport subscription
4. Strip original proxies, inject custom proxies & rules
5. Save standard config (custom proxies only)
6. Download third-party sources, apply blacklist / White filter
7. Save extra config (with third-party nodes)
"""

from __future__ import annotations

import os
import re
import httpx
import ruamel.yaml

from surge_config import SurgeConfig, SurgeKeyValue, SurgeSection, SurgeRawLine


yaml = ruamel.yaml.YAML()
yaml.indent(mapping=4)
yaml.encoding = "utf-8"
yaml.default_flow_style = False
yaml.allow_unicode = True

HEADERS = {"user-agent": "surge/5.0"}


# ---------------------------------------------------------------------------
# Flag emoji helpers (ported from mix_clash.py)
# ---------------------------------------------------------------------------

def _country_code_to_flag(code: str) -> str | None:
    code = code.strip().upper()
    if len(code) != 2 or not code.isalpha():
        return None
    base = 0x1F1E6
    return chr(base + (ord(code[0]) - ord("A"))) + chr(base + (ord(code[1]) - ord("A")))


_FLAG_CODE_RE = re.compile(r"^\s*\[?([A-Za-z]{2})\]?(?=[\s\-_])")
_FLAG_CODE_PAIR_RE = re.compile(r"^\s*\[?([A-Za-z]{2})\]?\s+\[?([A-Za-z]{2})\]?(?=[\s\-_])")


def _maybe_replace_flag_prefix(name: str) -> str:
    if not isinstance(name, str) or not name:
        return name
    if len(name) >= 2 and 0x1F1E6 <= ord(name[0]) <= 0x1F1FF and 0x1F1E6 <= ord(name[1]) <= 0x1F1FF:
        return name
    pair_match = _FLAG_CODE_PAIR_RE.match(name)
    if pair_match:
        code_a, code_b = pair_match.group(1), pair_match.group(2)
        flag_a = _country_code_to_flag(code_a)
        flag_b = _country_code_to_flag(code_b)
        if flag_a and flag_b:
            remainder = name[pair_match.end():].lstrip(" -_")
            return f"{flag_a}{flag_b} {remainder}".strip()
    match = _FLAG_CODE_RE.match(name)
    if not match:
        return name
    code = match.group(1)
    flag = _country_code_to_flag(code)
    if not flag:
        return name
    remainder = name[match.end():].lstrip(" -_")
    return f"{flag} {remainder}".strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    """Parse a Surge proxy group value into (type, proxy_names, options)."""
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


def _extract_proxy_entries(config: SurgeConfig) -> list[SurgeKeyValue]:
    section = config.get_section("Proxy")
    if not section:
        return []
    return [entry for entry in section.entries if isinstance(entry, SurgeKeyValue)]


def _ensure_section(config: SurgeConfig, name: str) -> SurgeSection:
    section = config.get_section(name)
    if section is None:
        section = SurgeSection(name=name)
        config.sections[name] = section
    return section


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _apply_proxies_and_groups(
    config: SurgeConfig,
    *,
    custom_proxies: dict[str, str],
    extra_proxy_entries: list[SurgeKeyValue],
    main_select: str | None,
    special_groups: dict,
    include_extra_in_select: bool,
    create_white_group: bool,
    white_group_name: str,
) -> None:
    """Reset [Proxy] section and update [Proxy Group] references.

    Parameters
    ----------
    custom_proxies:
        Mapping of proxy name -> Surge INI value string.
    extra_proxy_entries:
        Proxy entries parsed from third-party Surge subscriptions.
    """
    system_proxies = {"DIRECT", "REJECT"}
    for name in (special_groups or {}).values():
        if name:
            system_proxies.add(name)
    if main_select:
        system_proxies.add(main_select)
    if create_white_group:
        system_proxies.add(white_group_name)

    # Preserve inter-group references: collect all proxy group names
    group_section = config.get_section("Proxy Group")
    if group_section:
        for entry in group_section.entries:
            if isinstance(entry, SurgeKeyValue):
                system_proxies.add(entry.key)

    # Reset [Proxy] section
    proxy_section = _ensure_section(config, "Proxy")
    proxy_section.entries = []

    # Add custom proxies (INI strings from config_surge.yaml)
    custom_names: list[str] = []
    for name, value in custom_proxies.items():
        proxy_section.set(name, value)
        custom_names.append(name)

    # Add extra proxies from third-party sources
    extra_names: list[str] = []
    for entry in extra_proxy_entries:
        proxy_section.set(entry.key, entry.value)
        extra_names.append(entry.key)

    # Update [Proxy Group] section
    group_section = _ensure_section(config, "Proxy Group")
    for entry in group_section.entries:
        if not isinstance(entry, SurgeKeyValue):
            continue
        gtype, proxies, options = _parse_group_value(entry.value)
        # Keep only system / special proxies, strip original airport nodes
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # ── Read configs ──────────────────────────────────────────────────────
    with open("config_common.yaml", "r", encoding="utf-8") as f:
        common_config = yaml.load(f) or {}

    with open("config_surge.yaml", "r", encoding="utf-8") as f:
        surge_config = yaml.load(f) or {}

    proxy_url = common_config.get("http_proxy")

    output = surge_config.get("output")
    if not output:
        print("错误: config_surge.output 未配置")
        return

    if output.endswith(".conf"):
        output_extra = output[:-5] + "_extra.conf"
    else:
        output_extra = output + "_extra"

    # ── Resolve active subscription group ─────────────────────────────────
    base_sub_groups: dict = surge_config.get("base_sub_groups", {})
    single_base_sub: str | None = surge_config.get("base_sub")

    active_base_name = ""
    base_sub_config: dict | None = None

    if base_sub_groups:
        active_group = surge_config.get("active_group", "")
        if not active_group or active_group not in base_sub_groups:
            active_group = list(base_sub_groups.keys())[0]
            print(f"警告: 未指定 active_group，使用 '{active_group}'")
        base_sub_config = base_sub_groups[active_group]
        active_base_name = base_sub_config.get("name") or active_group
    elif single_base_sub:
        # Legacy format: flat base_sub + proxy_groups at top level
        active_base_name = "default"
        base_sub_config = {
            "url": single_base_sub,
            "user_agent": surge_config.get("user_agent"),
            "proxy_groups": surge_config.get("proxy_groups", {}),
        }
    else:
        print("错误: 没有找到基础订阅配置，请先运行 config_guide.py 生成 config_surge.yaml")
        return

    base_url = base_sub_config["url"]
    ua = base_sub_config.get("user_agent") or HEADERS["user-agent"]

    proxy_groups_cfg = base_sub_config.get("proxy_groups", {})
    main_select = proxy_groups_cfg.get("main_select")
    special_groups = proxy_groups_cfg.get("special_groups", {})

    # ── Download base config ──────────────────────────────────────────────
    print(f"正在下载基础配置: {active_base_name}")
    print(f"使用代理: {proxy_url or '未设置'}")
    transport = _make_transport(proxy_url)
    with httpx.Client(headers={"user-agent": ua}, transport=transport, timeout=30.0, follow_redirects=True) as client:
        r = client.get(base_url)
        r.raise_for_status()
        base_text = r.text

    # Two independent configs: standard (custom only) and extra (+ sources)
    surge_standard = SurgeConfig.from_text(base_text)
    surge_extra = SurgeConfig.from_text(base_text)

    # ── Custom proxies (INI strings) ──────────────────────────────────────
    raw_proxies = surge_config.get("proxies", {})
    if isinstance(raw_proxies, list):
        # Tolerate old list-of-dict format — skip with warning
        print("警告: proxies 格式已更改为 dict[name, surge_value]，忽略旧格式")
        raw_proxies = {}
    custom_proxies: dict[str, str] = {}
    for name, value in raw_proxies.items():
        new_name = _maybe_replace_flag_prefix(name)
        custom_proxies[new_name] = value

    # ── Rules ─────────────────────────────────────────────────────────────
    target_map: dict[str, str] = {}
    if main_select:
        target_map["proxy"] = main_select
    for key in ("domestic", "ai", "adblock"):
        if special_groups.get(key):
            target_map[key] = special_groups[key]

    custom_rules = surge_config.get("rules", [])
    custom_rules = _rewrite_rule_targets(custom_rules, target_map)

    for rule in custom_rules:
        if isinstance(rule, str) and rule.rstrip().endswith("}"):
            parts = [p.strip() for p in rule.split(",")]
            if parts and parts[-1].startswith("{") and parts[-1].endswith("}"):
                print(f"  警告: 规则占位符未解析: {rule}")

    # Prepend custom rules into both configs
    for cfg in (surge_standard, surge_extra):
        rule_section = _ensure_section(cfg, "Rule")
        if custom_rules:
            new_entries = [SurgeRawLine(content=rule) for rule in custom_rules]
            rule_section.entries = new_entries + rule_section.entries

    # ── Standard config: custom proxies only ──────────────────────────────
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

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(surge_standard.to_text())
    print(f"保存标准配置: {output}")

    # ── Download third-party sources ──────────────────────────────────────
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

    # ── Blacklist filter ──────────────────────────────────────────────────
    proxies_blacklist = common_config.get("proxies_blacklist", []) or []
    if proxies_blacklist and extra_proxy_entries:
        filtered = []
        for entry in extra_proxy_entries:
            if not any(keyword in entry.key for keyword in proxies_blacklist):
                filtered.append(entry)
            else:
                print(f"  黑名单过滤: {entry.key}")
        extra_proxy_entries = filtered

    # ── White filter & extra config ───────────────────────────────────────
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
        # No white keywords — all extra entries go directly into select groups
        if extra_proxy_entries:
            print(f"将 {len(extra_proxy_entries)} 个第三方节点添加到扩展配置...")
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

    with open(output_extra, "w", encoding="utf-8") as f:
        f.write(surge_extra.to_text())
    print(f"保存扩展配置: {output_extra}")

    print("\n完成!")
    print(f"  标准配置: {output}")
    print(f"  扩展配置: {output_extra}")


if __name__ == "__main__":
    main()
