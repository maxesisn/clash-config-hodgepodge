"""将 Mihomo fake-ip-filter 通配符格式批量转换为 fake-ip-filter-mode: rule 格式。"""
from __future__ import annotations
import re


def convert_fakeip_filter_entry(entry: str) -> str:
    """将单条 fake-ip-filter 通配符格式转为 fake-ip-filter-mode: rule 格式。"""
    entry = entry.strip()
    if not entry:
        return ""

    # geosite: / rule-set: 前缀直接映射
    if entry.startswith("geosite:"):
        return f"GEOSITE,{entry[len('geosite:'):]},real-ip"
    if entry.startswith("rule-set:"):
        return f"RULE-SET,{entry[len('rule-set:'):]},real-ip"

    has_wildcard = "*" in entry or "+" in entry.split(".")[0]

    if not has_wildcard:
        # 无通配符 → DOMAIN 精确匹配
        return f"DOMAIN,{entry},real-ip"

    # +.domain（剩余部分无 *）→ DOMAIN-SUFFIX
    if entry.startswith("+.") and "*" not in entry:
        return f"DOMAIN-SUFFIX,{entry[2:]},real-ip"

    # *.domain（剩余部分无 *）→ DOMAIN-SUFFIX
    if re.fullmatch(r"\*\.([^*+]+)", entry):
        return f"DOMAIN-SUFFIX,{entry[2:]},real-ip"

    # 复杂通配 (time.*.com, +.stun.*.*, *.n.n.srv.*.net) → DOMAIN-REGEX
    # 按 . 分段，将每段的通配符替换为正则
    parts = entry.split(".")
    regex_parts = []
    for part in parts:
        if part == "*":
            regex_parts.append("[^.]*")
        elif part == "+":
            regex_parts.append(".*")
        elif "*" in part:
            regex_parts.append(re.escape(part).replace(r"\*", "[^.]*"))
        else:
            regex_parts.append(re.escape(part))
    regex = r"\.".join(regex_parts)
    return f"DOMAIN-REGEX,^{regex}$,real-ip"


def convert_fakeip_filters(
    filters: list[str],
    force_proxy_domains: list[str] | None = None,
    append_geosite_cn: bool = True,
) -> list[str]:
    """批量转换 fake-ip-filter 列表为 rule 格式。

    force_proxy_domains 中的域名会以 DOMAIN-SUFFIX,xxx,fake-ip 形式
    插入到列表最前面，优先于后续的 real-ip / geosite:cn 规则。

    append_geosite_cn: 若原 filter 中不含 geosite:cn，自动追加到末尾
    作为兜底，确保国内域名返回 real-ip 走直连。
    """
    rules: list[str] = []

    # 第一部分: 强制 fake-ip 的例外域名（最高优先级）
    if force_proxy_domains:
        for domain in force_proxy_domains:
            domain = domain.strip()
            if domain:
                rules.append(f"DOMAIN-SUFFIX,{domain},fake-ip")

    # 第二部分: 原 filter 转换
    has_geosite_cn = False
    for entry in filters:
        stripped = entry.strip()
        if stripped in ("geosite:cn", "geosite:private,cn"):
            has_geosite_cn = True
        converted = convert_fakeip_filter_entry(stripped)
        if converted:
            rules.append(converted)

    # 第三部分: 兜底 geosite:cn（确保国内域名走直连，不影响 fasttrack）
    if append_geosite_cn and not has_geosite_cn:
        rules.append("GEOSITE,cn,real-ip")

    return rules
