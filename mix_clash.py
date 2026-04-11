import os
import re
import subprocess
import httpx
import ruamel.yaml
from copy import deepcopy
from fakeip_convert import convert_fakeip_filters

yaml = ruamel.yaml.YAML()
yaml.indent(mapping=4)
yaml.encoding = "utf-8"
yaml.default_flow_style = False
yaml.allow_unicode = True

headers = {'user-agent': 'clash-verge/2.4.3'}
MIHOMO_PATH = "/usr/local/bin/mihomo-linux-amd64-v3-v1.19.19"


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
    # If it already starts with a flag emoji (two regional indicators), leave it.
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


def _validate_config(path: str, proxy_url: str | None = None) -> bool:
    cmd = [MIHOMO_PATH, "-t", "-f", path, "-d", MIHOMO_DIR]
    try:
        env = os.environ.copy()
        if proxy_url:
            env["HTTP_PROXY"] = proxy_url
            env["http_proxy"] = proxy_url
            env["HTTPS_PROXY"] = proxy_url
            env["https_proxy"] = proxy_url
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    except FileNotFoundError:
        print(f"错误: 未找到 mihomo 可执行文件: {MIHOMO_PATH}")
        return False
    if result.returncode != 0:
        print(f"错误: 配置校验失败 {path}")
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip())
        return False
    return True

# 读取配置
with open("config_common.yaml", "r", encoding="utf-8") as f:
    common_config = yaml.load(f) or {}

with open("config_clash.yaml", "r", encoding="utf-8") as f:
    clash_config = yaml.load(f) or {}

# 代理设置仅从配置读取
DEFAULT_PROXY = common_config.get("http_proxy")

# mihomo 数据目录（用于 MMDB 等数据文件）
MIHOMO_DIR = clash_config.get("mihomo_dir") or os.path.join(os.getcwd(), "cache", "mihomo")
os.makedirs(MIHOMO_DIR, exist_ok=True)

output = clash_config["output"]
output_extra = output.replace(".yaml", "_extra.yaml")

# 获取当前激活的基础订阅配置（支持新旧格式）
active_base_name = ""
base_sub_config = None

base_sub_groups = clash_config.get("base_sub_groups", {})
base_subs = clash_config.get("base_subs", {})
single_base_sub = clash_config.get("base_sub")

if base_sub_groups:
    active_group = clash_config.get("active_group", "")
    if not active_group or active_group not in base_sub_groups:
        active_group = list(base_sub_groups.keys())[0]
        print(f"警告: 未指定 active_group，使用 '{active_group}'")
    base_sub_config = base_sub_groups[active_group]
    active_base_name = base_sub_config.get("name") or active_group
elif base_subs:
    active_base_name = clash_config.get("active_base", "")
    if not active_base_name or active_base_name not in base_subs:
        active_base_name = list(base_subs.keys())[0]
        print(f"警告: 未指定 active_base，使用 '{active_base_name}'")
    base_sub_config = base_subs[active_base_name]
elif single_base_sub:
    active_base_name = "default"
    base_sub_config = {"url": single_base_sub, "proxy_groups": {}}
else:
    print("错误: 没有找到基础订阅配置，请先运行 config_guide.py")
    exit(1)

base_config_url = base_sub_config["url"]

# 使用订阅特定的 UA 或默认 UA
base_ua = base_sub_config.get("user_agent", headers['user-agent'])
base_headers = {'user-agent': base_ua}

# 获取该订阅的代理组配置
proxy_groups_config = base_sub_config.get("proxy_groups", {})
main_select_group = proxy_groups_config.get("main_select")
auto_test_template = proxy_groups_config.get("auto_test_template")
special_groups = proxy_groups_config.get("special_groups", {})

# 下载配置文件，保存到base.yaml
print(f"正在下载基础配置: {active_base_name}")
print(f"使用代理: {DEFAULT_PROXY or '未设置'}")
transport = httpx.HTTPTransport(proxy=httpx.Proxy(DEFAULT_PROXY)) if DEFAULT_PROXY else httpx.HTTPTransport()
with httpx.Client(headers=base_headers, transport=transport) as client:
    r = client.get(base_config_url)
    r.raise_for_status()
    with open("base.yaml", "wb") as f:
        f.write(r.content)

# 读取配置文件
with open("base.yaml", "r", encoding="utf-8") as f:
    base = yaml.load(f)
    if not isinstance(base, dict):
        print("错误: 基础订阅配置无效或为空")
        os.remove("base.yaml")
        exit(1)

# ── fake-ip-filter 转换为 rule 模式 ──
dns_section = base.get("dns", {})
original_filters = dns_section.get("fake-ip-filter")
original_filter_mode = dns_section.get("fake-ip-filter-mode")
force_proxy_domains = clash_config.get("fakeip_force_proxy_domains", [])

if original_filter_mode == "rule" and force_proxy_domains:
    # Case 3: 已经是 rule 模式，只需在最前面插入 force-proxy 例外
    existing_rules = original_filters if isinstance(original_filters, list) else []
    force_rules = [f"DOMAIN-SUFFIX,{d.strip()},fake-ip" for d in force_proxy_domains if d.strip()]
    dns_section["fake-ip-filter"] = force_rules + existing_rules
    print(f"fake-ip-filter 已是 rule 模式，插入 {len(force_rules)} 条 fake-ip 例外")
elif original_filters and isinstance(original_filters, list):
    # Case 2: 有 fake-ip-filter（blacklist 通配符格式），转换为 rule 模式
    print(f"转换 fake-ip-filter: {len(original_filters)} 条 → rule 模式")
    converted_rules = convert_fakeip_filters(original_filters, force_proxy_domains)
    dns_section["fake-ip-filter-mode"] = "rule"
    dns_section["fake-ip-filter"] = converted_rules
    print(f"  转换完成: {len(converted_rules)} 条规则"
          f"（含 {len(force_proxy_domains)} 条强制 fake-ip 例外）")
elif force_proxy_domains:
    # Case 1: 无 fake-ip-filter，用默认条目生成
    print("订阅无 fake-ip-filter，使用默认条目生成 rule 模式")
    converted_rules = convert_fakeip_filters(None, force_proxy_domains)
    dns_section["fake-ip-filter-mode"] = "rule"
    dns_section["fake-ip-filter"] = converted_rules
    base.setdefault("dns", {}).update(dns_section)
    print(f"  生成完成: {len(converted_rules)} 条规则")

# 系统保留代理（不会从 proxy-groups 中移除）
system_proxies = {"DIRECT", "REJECT"}

# 添加 special_groups 中的组到系统保留
for special_name in special_groups.values():
    if special_name:
        system_proxies.add(special_name)

# 添加主选择组和自动测试模板组
if main_select_group:
    system_proxies.add(main_select_group)
if auto_test_template:
    system_proxies.add(auto_test_template)
if common_config.get("white_keywords"):
    system_proxies.add("White")

# 确保基础结构存在
base.setdefault("proxy-groups", [])
base.setdefault("rules", [])

# 清空 proxies，准备重新填充
base["proxies"] = []

# 保留的代理名称集合（系统代理 + 后续添加的自定义代理 + White）
retained_proxy_names = set(system_proxies)

# 清理 proxy-groups：只保留系统代理，移除原机场节点
for group in base.get("proxy-groups", []):
    if 'proxies' in group:
        # 保留系统代理和 special groups
        group['proxies'] = [
            proxy for proxy in group['proxies']
            if proxy in retained_proxy_names or proxy in system_proxies
        ]

# 获取自定义代理和规则
custom_proxies = clash_config.get("proxies", [])
custom_rules = clash_config.get("rules", [])

# 规则目标组映射（仅支持占位符语法）
target_map: dict[str, str] = {}
if main_select_group:
    target_map["proxy"] = main_select_group
special_domestic = special_groups.get("domestic")
special_ai = special_groups.get("ai")
special_adblock = special_groups.get("adblock")
if special_domestic:
    target_map["domestic"] = special_domestic
if special_ai:
    target_map["ai"] = special_ai
if special_adblock:
    target_map["adblock"] = special_adblock

custom_rules = _rewrite_rule_targets(custom_rules, target_map)

# 提示未解析的占位符
for rule in custom_rules:
    if isinstance(rule, str) and rule.rstrip().endswith("}"):
        parts = [part.strip() for part in rule.split(",")]
        if parts and parts[-1].startswith("{") and parts[-1].endswith("}"):
            print(f"  警告: 规则占位符未解析: {rule}")

# 添加自定义规则到开头（保持顺序）
if custom_rules:
    base["rules"] = list(custom_rules) + list(base["rules"])

# 添加自定义代理到配置
for proxy in custom_proxies:
    if isinstance(proxy, dict):
        proxy_name = proxy.get("name")
        if proxy_name:
            proxy["name"] = _maybe_replace_flag_prefix(proxy_name)
            proxy_name = proxy["name"]
    else:
        proxy_name = proxy
    if proxy_name:
        base["proxies"].append(proxy)
        retained_proxy_names.add(proxy_name)

        # 将自定义代理添加到代理组
        if main_select_group:
            for group in base.get('proxy-groups', []):
                gname = group.get("name", "")
                gtype = group.get("type", "")
                if gname == "White":
                    continue
                # 添加到主选择组、所有 select 组、以及所有 url-test/fallback/load-balance 组
                if (gname == main_select_group
                        or gtype in ("select", "url-test", "fallback", "load-balance")):
                    if proxy_name not in group.get("proxies", []):
                        group.setdefault("proxies", []).append(proxy_name)

# 为 url-test 组设置较短的测试间隔（自定义节点更稳定）
for group in base.get("proxy-groups", []):
    if group.get("type") == "url-test":
        group["interval"] = 30

# 保存标准配置（只有自定义节点）
print(f"保存标准配置: {output}")
tmp_output = f"{output}.tmp"
with open(tmp_output, "w", encoding="utf-8") as f:
    yaml.dump(base, f)
if _validate_config(tmp_output, proxy_url=DEFAULT_PROXY):
    os.replace(tmp_output, output)
else:
    print(f"保留未通过校验的临时文件: {tmp_output}")

# 下载第三方订阅，取出其中的proxy部分
sub_custom_proxies = []
sources = clash_config.get("sources", [])

if sources:
    print(f"正在下载 {len(sources)} 个第三方订阅...")
    for source in sources:
        try:
            transport = httpx.HTTPTransport(proxy=httpx.Proxy(DEFAULT_PROXY)) if DEFAULT_PROXY else httpx.HTTPTransport()
            with httpx.Client(headers=headers, transport=transport) as client:
                r = client.get(source)
                r.raise_for_status()
                proxies_data = yaml.load(r.text)
                if proxies_data and "proxies" in proxies_data:
                    for proxy in proxies_data["proxies"]:
                        if isinstance(proxy, dict) and "name" in proxy:
                            sub_custom_proxies.append(proxy)
                    print(f"  从 {source[:50]}... 获取了 {len(proxies_data['proxies'])} 个节点")
        except Exception as e:
            print(f"  警告: 获取订阅失败 {source[:50]}... - {e}")

# 应用黑名单过滤
proxies_blacklist = common_config.get("proxies_blacklist", [])
if proxies_blacklist:
    filtered = []
    for proxy in sub_custom_proxies:
        name = proxy.get("name", "")
        if not any(keyword in name for keyword in proxies_blacklist):
            filtered.append(proxy)
        else:
            print(f"  黑名单过滤: {name}")
    sub_custom_proxies = filtered

# 应用 White 白名单
white_keywords = common_config.get("white_keywords", [])

if white_keywords:
    print("处理 White 节点...")

    # 筛选符合 white 的节点
    white_proxies = []
    for proxy in sub_custom_proxies:
        name = proxy.get("name", "")
        if any(sw_keyword in name for sw_keyword in white_keywords):
            proxy["name"] = _maybe_replace_flag_prefix(name)
            white_proxies.append(proxy)

    if white_proxies:
        print(f"  找到 {len(white_proxies)} 个 White 节点")

        # 创建 White 组（固定使用 url-test）
        base_sw_pg = {
            "name": "White",
            "type": "url-test",
            "url": "http://www.gstatic.com/generate_204",
            "interval": 600,  # 机场节点使用较长间隔
            "proxies": [proxy.get("name") for proxy in white_proxies],
        }

        # 检查是否已存在 White 组
        existing_sw = None
        for i, pg in enumerate(base.get("proxy-groups", [])):
            if pg.get("name") == "White":
                existing_sw = i
                break

        if existing_sw is not None:
            base["proxy-groups"][existing_sw] = base_sw_pg
        else:
            base["proxy-groups"].append(base_sw_pg)

        # 将 White 组添加到所有 select 类型的分组
        for group in base.get("proxy-groups", []):
            if (group.get("type") == "select" and
                group.get("name") != "White" and
                "White" not in group.get("proxies", [])):
                group["proxies"].append("White")

        # 添加 White 节点到 proxies 列表
        base["proxies"].extend(white_proxies)
        for proxy in white_proxies:
            retained_proxy_names.add(proxy.get("name"))

        # 非 White 的节点不添加到主配置
        sub_custom_proxies = []

else:
    # 无 White 时：所有非黑名单的机场节点都添加到主配置
    print(f"将 {len(sub_custom_proxies)} 个第三方节点添加到主配置...")
    for proxy in sub_custom_proxies:
        proxy_name = proxy.get("name")
        if proxy_name:
            proxy["name"] = _maybe_replace_flag_prefix(proxy_name)
            proxy_name = proxy["name"]
            retained_proxy_names.add(proxy_name)

    # 添加到所有 select 类型的组
    for group in base.get("proxy-groups", []):
        if group.get("type") == "select":
            for proxy in sub_custom_proxies:
                proxy_name = proxy.get("name")
                if proxy_name and proxy_name not in group.get("proxies", []):
                    group["proxies"].append(proxy_name)

        # 为 url-test 组设置较长的测试间隔（机场节点）
        if group.get("type") == "url-test":
            group["interval"] = 600

    # 添加所有节点到 proxies 列表
    base["proxies"].extend(sub_custom_proxies)

# 保存扩展配置
print(f"保存扩展配置: {output_extra}")
tmp_output_extra = f"{output_extra}.tmp"
with open(tmp_output_extra, "w", encoding="utf-8") as f:
    yaml.dump(base, f)
if _validate_config(tmp_output_extra, proxy_url=DEFAULT_PROXY):
    os.replace(tmp_output_extra, output_extra)
else:
    print(f"保留未通过校验的临时文件: {tmp_output_extra}")

# 删除临时文件
os.remove("base.yaml")

print("\n完成!")
print(f"  标准配置: {output}")
print(f"  扩展配置: {output_extra}")
