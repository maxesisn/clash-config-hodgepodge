"""集成测试: 模拟真实订阅配置，验证 fake-ip-filter 转换在完整管道中的效果。"""
from __future__ import annotations
import ruamel.yaml
import io

from fakeip_convert import convert_fakeip_filters

yaml = ruamel.yaml.YAML()
yaml.indent(mapping=4)
yaml.default_flow_style = False
yaml.allow_unicode = True

# ── 模拟真实订阅 base.yaml 中的 dns 部分（典型机场配置）──
MOCK_BASE_DNS = {
    "enable": True,
    "listen": "0.0.0.0:7874",
    "ipv6": True,
    "enhanced-mode": "fake-ip",
    "fake-ip-range": "198.18.0.1/16",
    "fake-ip-filter": [
        # 本地/保留域名
        "*.lan",
        "*.localdomain",
        "*.example",
        "*.invalid",
        "*.localhost",
        "*.test",
        "*.local",
        "*.home.arpa",
        # NTP 时间同步
        "time.*.com",
        "time.*.gov",
        "time.*.edu.cn",
        "time.*.apple.com",
        "time1.*.com",
        "time2.*.com",
        "time3.*.com",
        "time4.*.com",
        "time5.*.com",
        "time6.*.com",
        "time7.*.com",
        "ntp.*.com",
        "ntp1.*.com",
        "ntp2.*.com",
        "ntp3.*.com",
        "ntp4.*.com",
        "*.time.edu.cn",
        "*.ntp.org.cn",
        "+.pool.ntp.org",
        "time1.cloud.tencent.com",
        # STUN/WebRTC
        "+.stun.*.*",
        "+.stun.*.*.*",
        "+.stun.*.*.*.*",
        "+.stun.*.*.*.*.*",
        # Microsoft 网络连接检测
        "lens.l.google.com",
        "stun.l.google.com",
        "stun.*.l.google.com",
        "+.neverssl.com",
        "+.msftconnecttest.com",
        "+.msftncsi.com",
        # QQ
        "localhost.ptlogin2.qq.com",
        "localhost.sec.qq.com",
        # 游戏平台
        "+.srv.nintendo.net",
        "*.n.n.srv.nintendo.net",
        "+.stun.playstation.net",
        "xbox.*.microsoft.com",
        "+.xboxlive.com",
        # 音乐平台
        "+.music.163.com",
        "+.126.net",
        "musicapi.taihe.com",
        "music.taihe.com",
        "songsearch.kugou.com",
        "trackercdn.kugou.com",
        "+.kuwo.cn",
        "api-jooxtt.sanook.com",
        "d1.music.126.net",
        "apc.*.musicloud.net",
        "+.y.qq.com",
        "+.music.tc.qq.com",
        "+.stream.qqmusic.qq.com",
        "amobile.music.tc.qq.com",
        # Bilibili
        "+.bilivideo.com",
        "+.bilivideo.cn",
        # 国内 CDN / 网络探测
        "+.hitv.com",
        "+.mcdn.bilivideo.cn",
        # GeoSite 规则
        "geosite:cn",
    ],
    "nameserver": [
        "https://223.5.5.5/dns-query",
        "https://223.6.6.6/dns-query",
    ],
    "nameserver-policy": {
        "geosite:private,cn": [
            "https://223.5.5.5/dns-query",
            "https://223.6.6.6/dns-query",
        ],
        "geosite:geolocation-!cn": [
            "https://1.1.1.1/dns-query",
            "https://8.8.8.8/dns-query",
        ],
    },
}

# ── 模拟用户的 config_clash.yaml 中的例外域名 ──
FORCE_PROXY_DOMAINS = ["bigo.tv"]


def test_full_pipeline():
    """模拟 mix_clash.py 中的 fake-ip-filter 转换管道。"""
    # 复制模拟数据
    dns_section = dict(MOCK_BASE_DNS)
    original_filters = dns_section["fake-ip-filter"]

    print(f"原始 fake-ip-filter 条目数: {len(original_filters)}")
    print(f"强制 fake-ip 域名: {FORCE_PROXY_DOMAINS}")
    print()

    # ── 执行转换（与 mix_clash.py 中的逻辑一致）──
    converted_rules = convert_fakeip_filters(original_filters, FORCE_PROXY_DOMAINS)
    dns_section["fake-ip-filter-mode"] = "rule"
    dns_section["fake-ip-filter"] = converted_rules

    print(f"转换后规则数: {len(converted_rules)}")
    print()

    # ── 验证 1: 结构正确性 ──
    assert dns_section["fake-ip-filter-mode"] == "rule"
    assert isinstance(dns_section["fake-ip-filter"], list)
    assert len(dns_section["fake-ip-filter"]) > 0
    print("[PASS] 结构正确: fake-ip-filter-mode=rule")

    # ── 验证 2: bigo.tv 在最前面，且是 fake-ip ──
    first_rule = converted_rules[0]
    assert first_rule == "DOMAIN-SUFFIX,bigo.tv,fake-ip", f"首条规则应为 bigo.tv fake-ip，实际: {first_rule}"
    print(f"[PASS] 首条规则: {first_rule}")

    # ── 验证 3: geosite:cn 被正确转换且在 bigo.tv 之后 ──
    cn_rules = [r for r in converted_rules if "GEOSITE,cn" in r]
    assert len(cn_rules) > 0, "应包含 GEOSITE,cn,real-ip"
    cn_index = converted_rules.index(cn_rules[0])
    bigo_index = converted_rules.index(first_rule)
    assert bigo_index < cn_index, f"bigo.tv({bigo_index}) 应在 geosite:cn({cn_index}) 之前"
    print(f"[PASS] 优先级正确: bigo.tv(idx={bigo_index}) < geosite:cn(idx={cn_index})")

    # ── 验证 4: 各种模式转换正确 ──
    checks = {
        "DOMAIN-SUFFIX,lan,real-ip": "*.lan → DOMAIN-SUFFIX",
        "DOMAIN-SUFFIX,local,real-ip": "*.local → DOMAIN-SUFFIX",
        "DOMAIN-SUFFIX,pool.ntp.org,real-ip": "+.pool.ntp.org → DOMAIN-SUFFIX",
        "DOMAIN,lens.l.google.com,real-ip": "精确域名 → DOMAIN",
        "DOMAIN,localhost.ptlogin2.qq.com,real-ip": "QQ 精确域名 → DOMAIN",
        "DOMAIN,time1.cloud.tencent.com,real-ip": "腾讯时间 → DOMAIN",
        "GEOSITE,cn,real-ip": "geosite:cn → GEOSITE",
    }
    for expected, desc in checks.items():
        assert expected in converted_rules, f"缺失: {expected} ({desc})"
        print(f"[PASS] {desc}: {expected}")

    # ── 验证 5: 中间通配符转正则 ──
    time_regex_rules = [r for r in converted_rules if r.startswith("DOMAIN-REGEX") and "time" in r]
    assert len(time_regex_rules) > 0, "time.*.com 应转为 DOMAIN-REGEX"
    print(f"[PASS] 中间通配符 → 正则: 共 {len(time_regex_rules)} 条")
    for r in time_regex_rules[:3]:
        print(f"       {r}")

    # ── 验证 6: STUN 多级通配符 ──
    stun_rules = [r for r in converted_rules if "stun" in r]
    assert len(stun_rules) > 0
    print(f"[PASS] STUN 规则: 共 {len(stun_rules)} 条")
    for r in stun_rules[:3]:
        print(f"       {r}")

    # ── 验证 7: 没有残留的原始通配符格式 ──
    for r in converted_rules:
        assert not r.startswith("*."), f"残留原始格式: {r}"
        assert not r.startswith("+.") or r.startswith("DOMAIN"), f"残留原始格式: {r}"
    print("[PASS] 无残留通配符格式")

    # ── 验证 8: 生成 YAML 输出可序列化 ──
    output = io.StringIO()
    yaml.dump({"dns": dns_section}, output)
    yaml_text = output.getvalue()
    assert "fake-ip-filter-mode: rule" in yaml_text
    assert "DOMAIN-SUFFIX,bigo.tv,fake-ip" in yaml_text
    assert "GEOSITE,cn,real-ip" in yaml_text
    print("[PASS] YAML 序列化正常")

    # ── 打印完整转换结果 ──
    print("\n" + "=" * 60)
    print("完整转换结果:")
    print("=" * 60)
    for i, rule in enumerate(converted_rules):
        marker = " ◀ FAKE-IP" if rule.endswith(",fake-ip") else ""
        print(f"  [{i:2d}] {rule}{marker}")

    print(f"\n总计: {len(converted_rules)} 条规则")
    print(f"  fake-ip (走代理): {sum(1 for r in converted_rules if r.endswith(',fake-ip'))} 条")
    print(f"  real-ip (直连):   {sum(1 for r in converted_rules if r.endswith(',real-ip'))} 条")


def test_bigo_resolution_scenario():
    """模拟 agent-oss.bigo.tv 的解析场景。

    验证: 在 rule 模式下，bigo.tv 的 DOMAIN-SUFFIX fake-ip 规则
    优先于 GEOSITE,cn,real-ip，确保该域名获得 Fake-IP。
    """
    print("\n" + "=" * 60)
    print("场景模拟: agent-oss.bigo.tv DNS 解析")
    print("=" * 60)

    converted = convert_fakeip_filters(
        MOCK_BASE_DNS["fake-ip-filter"],
        FORCE_PROXY_DOMAINS,
    )

    # 模拟 Mihomo 的 rule 匹配逻辑（从上到下，首次匹配）
    domain = "agent-oss.bigo.tv"
    result = None
    matched_rule = None

    for rule in converted:
        parts = rule.split(",")
        rule_type = parts[0]
        action = parts[-1]  # fake-ip 或 real-ip

        if rule_type == "DOMAIN-SUFFIX":
            suffix = parts[1]
            if domain == suffix or domain.endswith("." + suffix):
                result = action
                matched_rule = rule
                break
        elif rule_type == "DOMAIN":
            if domain == parts[1]:
                result = action
                matched_rule = rule
                break
        elif rule_type == "GEOSITE":
            # geosite:cn 包含 bigo.tv（中国公司）
            # 这里模拟：如果前面没匹配到，geosite:cn 会匹配
            geo_name = parts[1]
            if geo_name == "cn":
                result = action
                matched_rule = rule
                break

    print(f"  域名: {domain}")
    print(f"  匹配规则: {matched_rule}")
    print(f"  结果: {result}")

    assert result == "fake-ip", f"bigo.tv 应返回 fake-ip，实际: {result}"
    print(f"\n[PASS] agent-oss.bigo.tv → fake-ip (198.18.x.x) → 走旁路由代理")
    print(f"[PASS] 不会匹配到 GEOSITE,cn,real-ip（被 DOMAIN-SUFFIX,bigo.tv,fake-ip 优先拦截）")


if __name__ == "__main__":
    test_full_pipeline()
    test_bigo_resolution_scenario()
    print("\n✅ 所有集成测试通过!")
