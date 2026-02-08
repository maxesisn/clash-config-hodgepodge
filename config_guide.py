#!/usr/bin/env python3
"""
Clash 配置向导 - 交互式生成 custom_config.yaml
自动获取订阅配置，引导用户映射代理组
"""

import os
import re
import sys
import httpx
import ruamel.yaml

yaml = ruamel.yaml.YAML()
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.encoding = "utf-8"
yaml.default_flow_style = False
yaml.allow_unicode = True

# 默认代理设置（仅从配置读取）
DEFAULT_PROXY = ""

# 固定使用 Clash Verge 的 UA
USER_AGENT = "clash-verge/2.4.3"


def _make_transport(proxy_url: str | None) -> httpx.HTTPTransport:
    if proxy_url:
        return httpx.HTTPTransport(proxy=httpx.Proxy(proxy_url))
    return httpx.HTTPTransport()


def fetch_config(url: str, ua: str = USER_AGENT, proxy: str = None) -> dict:
    """获取订阅配置"""
    headers = {"user-agent": ua}
    proxy_url = proxy or DEFAULT_PROXY or None
    transport = _make_transport(proxy_url)

    with httpx.Client(headers=headers, timeout=30, follow_redirects=True, transport=transport) as client:
        r = client.get(url)
        r.raise_for_status()
        return yaml.load(r.text)


def detect_group_types(proxy_groups: list) -> dict:
    """分析代理组类型"""
    groups_by_type = {
        "select": [],
        "url-test": [],
        "load-balance": [],
        "fallback": [],
        "relay": [],
        "direct": [],
        "other": []
    }

    for group in proxy_groups:
        name = group.get("name", "Unknown")
        gtype = group.get("type", "unknown")
        if gtype in groups_by_type:
            groups_by_type[gtype].append(name)
        else:
            groups_by_type["other"].append(f"{name}({gtype})")

    return groups_by_type


def detect_surge_group_types(group_entries: list) -> dict:
    groups_by_type = {
        "select": [],
        "url-test": [],
        "load-balance": [],
        "fallback": [],
        "relay": [],
        "direct": [],
        "other": []
    }
    for name, value in group_entries:
        tokens = [token.strip() for token in value.split(",") if token.strip()]
        gtype = tokens[0] if tokens else "unknown"
        if gtype in groups_by_type:
            groups_by_type[gtype].append(name)
        else:
            groups_by_type["other"].append(f"{name}({gtype})")
    return groups_by_type


def detect_special_groups(proxy_groups: list) -> dict:
    """根据名称模式推测特殊组用途"""
    patterns = {
        "adblock": [r"(?i)ad.*block", r"(?i)广告", r"(?i)adguard", r"(?i)reject"],
        "domestic": [r"(?i)domestic", r"(?i)国内", r"(?i)direct", r"(?i)全球直连", r"(?i)大陆"],
        "ai": [r"(?i)ai", r"(?i)gpt", r"(?i)openai", r"(?i)chatgpt", r"(?i)bard", r"(?i)copilot", r"(?i)gemini"],
    }

    detected = {key: [] for key in patterns}

    for group in proxy_groups:
        name = group.get("name", "")
        for purpose, regex_list in patterns.items():
            for pattern in regex_list:
                if re.search(pattern, name):
                    detected[purpose].append(name)
                    break

    return detected


def print_header(text: str):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def print_section(text: str):
    print(f"\n{'─' * 50}")
    print(f"  {text}")
    print(f"{'─' * 50}")


def select_from_list(options: list, prompt: str, allow_none: bool = True) -> str:
    """让用户从列表中选择"""
    if not options:
        if allow_none:
            print(f"  (无可用选项)")
            return None
        else:
            print("错误：没有可用选项")
            sys.exit(1)

    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")
    if allow_none:
        print(f"  [0] 跳过/不设置")

    while True:
        try:
            choice = input(f"  请选择 [0-{len(options)}]: ").strip()
            idx = int(choice)
            if idx == 0 and allow_none:
                return None
            if 1 <= idx <= len(options):
                return options[idx - 1]
            print("  无效选择，请重试")
        except ValueError:
            print("  请输入数字")


def multi_select_from_list(options: list, prompt: str) -> list:
    """多选"""
    if not options:
        print(f"  (无可用选项)")
        return []

    print(f"\n{prompt}")
    print("  (输入多个数字用空格分隔，如: 1 3 5，输入 0 表示全选)")
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")

    while True:
        choice = input(f"  请选择: ").strip()
        if choice == "0":
            return options
        try:
            indices = [int(x) for x in choice.split()]
            result = []
            for idx in indices:
                if 1 <= idx <= len(options):
                    result.append(options[idx - 1])
            if result:
                return result
            print("  无效选择，请重试")
        except ValueError:
            print("  请输入数字")


def _choose_mode() -> str:
    print_header("配置向导")
    print("\n请选择要配置的目标：")
    print("  [1] Clash")
    print("  [2] Surge")
    while True:
        choice = input("  请选择 [1-2]: ").strip()
        if choice == "1":
            return "clash"
        if choice == "2":
            return "surge"
        print("  无效选择，请重试")


def run_guide():
    mode = _choose_mode()
    if mode == "surge":
        run_surge_guide()
        return
    print_header("Clash 配置向导")
    print("\n本向导将帮助你：")
    print("  1. 添加机场订阅分组")
    print("  2. 自动识别代理组结构")
    print("  3. 映射特殊用途的代理组")
    print("  4. 生成/更新 custom_config.yaml")

    common_data = {
        "http_proxy": "",
        "proxies_blacklist": [],
        "white_keywords": [],
    }
    clash_data = {
        "output": "/home/maxesisn/wlan/wowsuchhidden/config.yaml",
        "base_sub_groups": {},
        "active_group": "",
        "proxies": [],
        "rules": [],
    }

    # 检查是否存在现有配置
    if os.path.exists("config_clash.yaml") or os.path.exists("config_common.yaml"):
        print_section("发现现有配置")
        choice = input("  是否导入现有配置? [Y/n]: ").strip().lower()
        if choice != "n":
            if os.path.exists("config_common.yaml"):
                with open("config_common.yaml", "r", encoding="utf-8") as f:
                    existing_common = yaml.load(f) or {}
                    common_data.update(existing_common)
            if os.path.exists("config_clash.yaml"):
                with open("config_clash.yaml", "r", encoding="utf-8") as f:
                    existing_clash = yaml.load(f) or {}
                    clash_data.update(existing_clash)
            # Legacy fallback: custom_config.yaml if still present
            if os.path.exists("custom_config.yaml"):
                with open("custom_config.yaml", "r", encoding="utf-8") as f:
                    existing = yaml.load(f)
                    if existing and "clash" not in existing and "common" not in existing:
                        common_data.update({
                            "http_proxy": existing.get("http_proxy", ""),
                            "proxies_blacklist": existing.get("proxies_blacklist", []),
                            "white_keywords": existing.get("white_keywords", []),
                        })
                        clash_data.update({
                            "output": existing.get("output", "/home/maxesisn/wlan/wowsuchhidden/config.yaml"),
                            "base_sub_groups": existing.get("base_sub_groups", {}),
                            "active_group": existing.get("active_group", ""),
                            "proxies": existing.get("proxies", []),
                            "rules": existing.get("rules", []),
                            "sources": existing.get("sources", []),
                        })

    # 步骤 1: 添加订阅
    print_section("步骤 1: 添加机场订阅分组")

    while True:
        group_name = input("\n  订阅分组名称 (如: dler, nexitally): ").strip()
        if not group_name:
            if not clash_data["base_sub_groups"]:
                print("  至少需要添加一个订阅分组")
                continue
            break

        if group_name in clash_data["base_sub_groups"]:
            overwrite = input("  该分组已存在，是否覆盖? [y/N]: ").strip().lower()
            if overwrite != "y":
                continue

        sub_name = input("  订阅名称 (展示用，可留空): ").strip() or group_name
        sub_url = input("  订阅链接: ").strip()

        print(f"\n  正在获取配置 (UA: {USER_AGENT})...")
        try:
            proxy_override = common_data.get("http_proxy") or DEFAULT_PROXY or None
            clash_config = fetch_config(sub_url, USER_AGENT, proxy=proxy_override)
            proxy_groups = clash_config.get("proxy-groups", [])

            if not proxy_groups:
                print("  警告: 配置中没有找到 proxy-groups")
                continue

            print(f"  成功! 发现 {len(proxy_groups)} 个代理组")

            # 分析组类型
            groups_by_type = detect_group_types(proxy_groups)

            print_section(f"'{sub_name}' 的代理组分析")

            for gtype, names in groups_by_type.items():
                if names:
                    print(f"\n  {gtype.upper()} 类型 ({len(names)}个):")
                    for name in names[:5]:
                        print(f"    - {name}")
                    if len(names) > 5:
                        print(f"    ... 还有 {len(names) - 5} 个")

            # 检测可能的特殊组
            detected_special = detect_special_groups(proxy_groups)

            print_section("配置代理组映射")
            print("  请为以下用途选择对应的代理组:\n")

            sub_config = {
                "name": sub_name,
                "url": sub_url,
                "user_agent": USER_AGENT,
                "proxy_groups": {}
            }

            # 1. 主选择组（添加自定义节点的目标）
            select_groups = groups_by_type["select"]
            suggested = select_groups[0] if select_groups else None

            print(f"  【主选择组】- 自定义节点将添加到这里")
            print(f"  建议: {suggested or '无'}")
            main_select = select_from_list(
                select_groups,
                "选择主选择组 (通常是 'Proxy' 或 '手动选择'):",
                allow_none=False
            )
            sub_config["proxy_groups"]["main_select"] = main_select

            # 2. 特殊组映射
            print_section("特殊用途组映射 (可选)")
            print("  这些组用于规则分流，如广告拦截、国内直连等\n")

            sub_config["proxy_groups"]["special_groups"] = {}

            special_purposes = [
                ("adblock", "广告拦截 (AdBlock)", detected_special["adblock"]),
                ("domestic", "国内直连 (Domestic/Direct)", detected_special["domestic"]),
                ("ai", "AI 服务 (ChatGPT/Claude等)", detected_special["ai"]),
            ]

            for key, label, suggestions in special_purposes:
                all_groups = []
                for groups in groups_by_type.values():
                    all_groups.extend(groups)

                print(f"\n  【{label}】")
                if suggestions:
                    print(f"  检测到可能选项: {', '.join(suggestions[:3])}")

                selected = select_from_list(all_groups, f"选择 {label} 对应的组:", allow_none=True)
                if selected:
                    sub_config["proxy_groups"]["special_groups"][key] = selected

            clash_data["base_sub_groups"][group_name] = sub_config

            if not clash_data["active_group"]:
                clash_data["active_group"] = group_name

            print(f"\n  ✓ 订阅分组 '{group_name}' 配置完成")

        except Exception as e:
            print(f"  错误: 获取配置失败 - {e}")
            continue

        more = input("\n  是否继续添加其他订阅? [y/N]: ").strip().lower()
        if more != "y":
            break

    # 步骤 2: 选择默认使用的订阅分组
    if len(clash_data["base_sub_groups"]) > 1:
        print_section("步骤 2: 选择默认使用的订阅分组")
        group_names = list(clash_data["base_sub_groups"].keys())
        active = select_from_list(group_names, "选择默认激活的订阅分组:", allow_none=False)
        clash_data["active_group"] = active

    # 步骤 3: 代理与节点过滤配置
    print_section("步骤 3: 代理与节点过滤配置 (可选)")

    print("\n  【HTTP 代理】- 获取订阅时使用 (留空表示不设置)")
    print(f"  当前默认: {common_data.get('http_proxy') or '未设置'}")
    proxy_input = input("  输入代理地址 (例如 http://127.0.0.1:8888): ").strip()
    if proxy_input:
        common_data["http_proxy"] = proxy_input

    print("\n  【黑名单】- 排除包含特定关键词的节点")
    print("  示例: 广告, 官网, 剩余流量, 到期")
    blacklist_input = input("  输入黑名单关键词 (用空格分隔，直接回车跳过): ").strip()
    if blacklist_input:
        common_data["proxies_blacklist"] = [k.strip() for k in blacklist_input.split() if k.strip()]

    print("\n  【White 白名单】- 这些关键词的节点放入独立分组")
    print("  示例: IEPL, Premium, Ultra, AC")
    whitelist_input = input("  输入白名单关键词 (用空格分隔，直接回车跳过): ").strip()
    if whitelist_input:
        common_data["white_keywords"] = [k.strip() for k in whitelist_input.split() if k.strip()]

    # 步骤 4: 自定义节点和规则
    print_section("步骤 4: 自定义配置")

    if clash_data.get("proxies"):
        print(f"\n  现有 {len(clash_data['proxies'])} 个自定义代理节点")
    else:
        print("\n  暂无自定义代理节点")

    print("\n  提示: 自定义节点和规则请在生成的文件中手动编辑")

    # 输出配置
    print_section("配置完成")
    print(f"\n  订阅分组: {len(clash_data['base_sub_groups'])} 个")
    for name, sub in clash_data["base_sub_groups"].items():
        active_mark = " ✓ 默认" if name == clash_data["active_group"] else ""
        display_name = sub.get("name") or name
        print(f"    - {name} ({display_name}){active_mark}")
        pg = sub.get("proxy_groups", {})
        print(f"      主选择组: {pg.get('main_select', 'N/A')}")
        special = pg.get("special_groups", {})
        if special:
            print(f"      特殊组映射: {', '.join(special.keys())}")

    # 生成配置文件
    print("\n  生成配置: config_common.yaml + config_clash.yaml")

    with open("config_common.yaml", "w", encoding="utf-8") as f:
        yaml.dump(common_data, f)
    with open("config_clash.yaml", "w", encoding="utf-8") as f:
        yaml.dump(clash_data, f)


def run_surge_guide():
    print_header("Surge 配置向导")
    print("\n本向导将帮助你：")
    print("  1. 添加机场 Surge 订阅分组")
    print("  2. 映射代理组")
    print("  3. 生成/更新 config_surge.yaml")

    common_data = {
        "http_proxy": "",
        "proxies_blacklist": [],
        "white_keywords": [],
    }
    surge_data = {
        "output": "/home/maxesisn/wlan/wowsuchhidden/surge.conf",
        "base_sub_groups": {},
        "active_group": "",
        "proxies": {},
        "rules": [],
        "sources": [],
    }

    if os.path.exists("config_surge.yaml") or os.path.exists("config_common.yaml"):
        print_section("发现现有配置")
        choice = input("  是否导入现有配置? [Y/n]: ").strip().lower()
        if choice != "n":
            if os.path.exists("config_common.yaml"):
                with open("config_common.yaml", "r", encoding="utf-8") as f:
                    existing_common = yaml.load(f) or {}
                    common_data.update(existing_common)
            if os.path.exists("config_surge.yaml"):
                with open("config_surge.yaml", "r", encoding="utf-8") as f:
                    existing_surge = yaml.load(f) or {}
                    surge_data.update(existing_surge)

    print_section("步骤 1: 添加机场 Surge 订阅分组")

    while True:
        group_name = input("\n  订阅分组名称 (如: dler, nexitally): ").strip()
        if not group_name:
            if not surge_data["base_sub_groups"]:
                print("  至少需要添加一个订阅分组")
                continue
            break

        if group_name in surge_data["base_sub_groups"]:
            overwrite = input("  该分组已存在，是否覆盖? [y/N]: ").strip().lower()
            if overwrite != "y":
                continue

        sub_name = input("  订阅名称 (展示用，可留空): ").strip() or group_name
        sub_url = input("  Surge 订阅链接: ").strip()
        ua_input = input("  User-Agent (默认 surge/5.0): ").strip() or "surge/5.0"

        print(f"\n  正在获取配置 (UA: {ua_input})...")
        try:
            proxy_override = common_data.get("http_proxy") or None
            transport = _make_transport(proxy_override)
            with httpx.Client(headers={"user-agent": ua_input}, timeout=30, follow_redirects=True, transport=transport) as client:
                r = client.get(sub_url)
                r.raise_for_status()
                base_text = r.text

            from surge_config import SurgeConfig, SurgeKeyValue

            surge_cfg = SurgeConfig.from_text(base_text)
            group_section = surge_cfg.get_section("Proxy Group")
            group_entries = []
            if group_section:
                for entry in group_section.entries:
                    if isinstance(entry, SurgeKeyValue):
                        group_entries.append((entry.key, entry.value))

            if not group_entries:
                print("  警告: 配置中没有找到 Proxy Group")
                continue

            print(f"  成功! 发现 {len(group_entries)} 个代理组")
            groups_by_type = detect_surge_group_types(group_entries)

            print_section(f"'{sub_name}' 的代理组分析")
            for gtype, names in groups_by_type.items():
                if names:
                    print(f"\n  {gtype.upper()} 类型 ({len(names)}个):")
                    for name in names[:5]:
                        print(f"    - {name}")
                    if len(names) > 5:
                        print(f"    ... 还有 {len(names) - 5} 个")

            print_section("配置代理组映射")
            select_groups = groups_by_type["select"]
            suggested = select_groups[0] if select_groups else None

            print(f"  【主选择组】- 自定义节点将添加到这里")
            print(f"  建议: {suggested or '无'}")
            main_select = select_from_list(
                select_groups,
                "选择主选择组 (通常是 'Proxy' 或 '手动选择'):",
                allow_none=False
            )

            sub_config = {
                "name": sub_name,
                "url": sub_url,
                "user_agent": ua_input,
                "proxy_groups": {
                    "main_select": main_select,
                    "special_groups": {},
                }
            }

            print_section("特殊用途组映射 (可选)")
            detected_special = detect_special_groups([{"name": name} for name, _ in group_entries])
            special_purposes = [
                ("adblock", "广告拦截 (AdBlock)", detected_special["adblock"]),
                ("domestic", "国内直连 (Domestic/Direct)", detected_special["domestic"]),
                ("ai", "AI 服务 (ChatGPT/Claude等)", detected_special["ai"]),
            ]
            for key, label, suggestions in special_purposes:
                all_groups = []
                for groups in groups_by_type.values():
                    all_groups.extend(groups)
                print(f"\n  【{label}】")
                if suggestions:
                    print(f"  检测到可能选项: {', '.join(suggestions[:3])}")
                selected = select_from_list(all_groups, f"选择 {label} 对应的组:", allow_none=True)
                if selected:
                    sub_config["proxy_groups"]["special_groups"][key] = selected

            surge_data["base_sub_groups"][group_name] = sub_config

            if not surge_data["active_group"]:
                surge_data["active_group"] = group_name

            print(f"\n  ✓ 订阅分组 '{group_name}' 配置完成")

        except Exception as e:
            print(f"  错误: 获取配置失败 - {e}")
            continue

        more = input("\n  是否继续添加其他订阅? [y/N]: ").strip().lower()
        if more != "y":
            break

    # 选择默认使用的订阅分组
    if len(surge_data["base_sub_groups"]) > 1:
        print_section("步骤 2: 选择默认使用的订阅分组")
        group_names = list(surge_data["base_sub_groups"].keys())
        active = select_from_list(group_names, "选择默认激活的订阅分组:", allow_none=False)
        surge_data["active_group"] = active

    print_section("代理与节点过滤配置 (可选)")
    print("\n  【HTTP 代理】- 获取订阅时使用 (留空表示不设置)")
    print(f"  当前默认: {common_data.get('http_proxy') or '未设置'}")
    proxy_input = input("  输入代理地址 (例如 http://127.0.0.1:8888): ").strip()
    if proxy_input:
        common_data["http_proxy"] = proxy_input

    print("\n  【黑名单】- 排除包含特定关键词的节点")
    print("  示例: 广告, 官网, 剩余流量, 到期")
    blacklist_input = input("  输入黑名单关键词 (用空格分隔，直接回车跳过): ").strip()
    if blacklist_input:
        common_data["proxies_blacklist"] = [k.strip() for k in blacklist_input.split() if k.strip()]

    print("\n  【White 白名单】- 这些关键词的节点放入独立分组")
    print("  示例: IEPL, Premium, Ultra, AC")
    whitelist_input = input("  输入白名单关键词 (用空格分隔，直接回车跳过): ").strip()
    if whitelist_input:
        common_data["white_keywords"] = [k.strip() for k in whitelist_input.split() if k.strip()]

    print_section("配置完成")
    print(f"\n  订阅分组: {len(surge_data['base_sub_groups'])} 个")
    for name, sub in surge_data["base_sub_groups"].items():
        active_mark = " ✓ 默认" if name == surge_data["active_group"] else ""
        display_name = sub.get("name") or name
        print(f"    - {name} ({display_name}){active_mark}")
        pg = sub.get("proxy_groups", {})
        print(f"      主选择组: {pg.get('main_select', 'N/A')}")
        special = pg.get("special_groups", {})
        if special:
            print(f"      特殊组映射: {', '.join(special.keys())}")

    print("\n  生成配置: config_common.yaml + config_surge.yaml")

    with open("config_common.yaml", "w", encoding="utf-8") as f:
        yaml.dump(common_data, f)
    with open("config_surge.yaml", "w", encoding="utf-8") as f:
        yaml.dump(surge_data, f)

    print("\n  ✓ 配置生成完成!")
    print("\n  你可以手动编辑 config_surge.yaml 添加:")
    print("    - 自定义代理节点 (proxies: {name: surge_value})")
    print("    - 自定义规则 (rules)")
    print("    - 第三方订阅源 (sources)")


if __name__ == "__main__":
    try:
        run_guide()
    except KeyboardInterrupt:
        print("\n\n  已取消")
        sys.exit(1)
