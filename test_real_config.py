"""用真实 nexitally 订阅配置测试 fake-ip-filter 转换。"""
from __future__ import annotations
from fakeip_convert import convert_fakeip_filter_entry, convert_fakeip_filters

# 从服务器上 grep 出的真实 fake-ip-filter
REAL_FILTERS = [
    "*.lan",
    "*.localdomain",
    "*.example",
    "*.invalid",
    "*.localhost",
    "*.test",
    "*.local",
    "*.home.arpa",
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
    "ntp5.*.com",
    "ntp6.*.com",
    "ntp7.*.com",
    "*.time.edu.cn",
    "*.ntp.org.cn",
    "+.pool.ntp.org",
    "time1.cloud.tencent.com",
    "stun.*.*",
    "stun.*.*.*",
    "swscan.apple.com",
    "mesu.apple.com",
    "music.163.com",
    "*.music.163.com",
    "*.126.net",
    "musicapi.taihe.com",
    "music.taihe.com",
    "songsearch.kugou.com",
    "trackercdn.kugou.com",
    "*.kuwo.cn",
    "api-jooxtt.sanook.com",
    "api.joox.com",
    "y.qq.com",
    "*.y.qq.com",
    "streamoc.music.tc.qq.com",
    "mobileoc.music.tc.qq.com",
    "isure.stream.qqmusic.qq.com",
    "dl.stream.qqmusic.qq.com",
    "aqqmusic.tc.qq.com",
    "amobile.music.tc.qq.com",
    "localhost.ptlogin2.qq.com",
    "*.msftconnecttest.com",
    "*.msftncsi.com",
    "*.xiami.com",
    "*.music.migu.cn",
    "music.migu.cn",
    "+.wotgame.cn",
    "+.wggames.cn",
    "+.wowsgame.cn",
    "+.wargaming.net",
    "*.*.*.srv.nintendo.net",
    "*.*.stun.playstation.net",
    "xbox.*.*.microsoft.com",
    "*.*.xboxlive.com",
    "*.ipv6.microsoft.com",
    "teredo.*.*.*",
    "teredo.*.*",
    "speedtest.cros.wr.pvp.net",
    "+.jjvip8.com",
    "www.douyu.com",
    "activityapi.huya.com",
    "activityapi.huya.com.w.cdngslb.com",
    "www.bilibili.com",
    "api.bilibili.com",
    "a.w.bilicdn1.com",
]

FORCE_PROXY = ["bigo.tv"]


def test_real_conversion():
    print(f"原始 fake-ip-filter: {len(REAL_FILTERS)} 条")
    print(f"强制 fake-ip 域名: {FORCE_PROXY}")
    print()

    converted = convert_fakeip_filters(REAL_FILTERS, FORCE_PROXY)

    print(f"转换后规则: {len(converted)} 条")
    print()

    # 逐条打印，标注类型
    type_counts = {}
    errors = []
    for i, rule in enumerate(converted):
        parts = rule.split(",")
        rtype = parts[0]
        action = parts[-1]
        type_counts[rtype] = type_counts.get(rtype, 0) + 1

        marker = ""
        if action == "fake-ip":
            marker = "  <-- FAKE-IP (走代理)"

        print(f"  [{i:2d}] {rule}{marker}")

        # 基本格式校验
        if action not in ("real-ip", "fake-ip"):
            errors.append(f"[{i}] 无效action: {rule}")
        if rtype not in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-REGEX", "GEOSITE", "RULE-SET"):
            errors.append(f"[{i}] 无效类型: {rule}")

    print()
    print("类型统计:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")

    if errors:
        print()
        print("!! 格式错误:")
        for e in errors:
            print(f"  {e}")
        return False

    # 验证关键点
    print()
    assert converted[0] == "DOMAIN-SUFFIX,bigo.tv,fake-ip", f"首条应为 bigo.tv fake-ip: {converted[0]}"
    print("[PASS] bigo.tv fake-ip 在首位")

    # 验证一些关键转换
    checks = [
        ("DOMAIN-SUFFIX,lan,real-ip", "*.lan"),
        ("DOMAIN-SUFFIX,pool.ntp.org,real-ip", "+.pool.ntp.org"),
        ("DOMAIN,time1.cloud.tencent.com,real-ip", "time1.cloud.tencent.com"),
        ("DOMAIN,swscan.apple.com,real-ip", "swscan.apple.com"),
        ("DOMAIN,music.163.com,real-ip", "music.163.com"),
        ("DOMAIN-SUFFIX,music.163.com,real-ip", "*.music.163.com"),
        ("DOMAIN,y.qq.com,real-ip", "y.qq.com"),
        ("DOMAIN-SUFFIX,y.qq.com,real-ip", "*.y.qq.com"),
        ("DOMAIN-SUFFIX,wotgame.cn,real-ip", "+.wotgame.cn"),
        ("DOMAIN,www.bilibili.com,real-ip", "www.bilibili.com"),
        ("DOMAIN,a.w.bilicdn1.com,real-ip", "a.w.bilicdn1.com"),
    ]
    for expected, orig in checks:
        assert expected in converted, f"缺失: {expected} (原: {orig})"
        print(f"[PASS] {orig} -> {expected}")

    # 验证复杂通配符
    print()
    print("复杂通配符转换验证:")
    complex_patterns = [
        "stun.*.*",
        "stun.*.*.*",
        "*.*.*.srv.nintendo.net",
        "*.*.stun.playstation.net",
        "xbox.*.*.microsoft.com",
        "*.*.xboxlive.com",
        "teredo.*.*.*",
        "teredo.*.*",
        "time.*.com",
    ]
    for pat in complex_patterns:
        result = convert_fakeip_filter_entry(pat)
        assert result.startswith("DOMAIN-REGEX,"), f"{pat} 应转为 DOMAIN-REGEX: {result}"
        # 提取正则部分，验证格式
        regex_part = result.split(",")[1]
        assert regex_part.startswith("^") and regex_part.endswith("$"), f"正则应有锚点: {regex_part}"
        print(f"  [PASS] {pat:40s} -> {result}")

    return True


if __name__ == "__main__":
    ok = test_real_conversion()
    if ok:
        print("\n所有测试通过!")
    else:
        print("\n测试失败!")
        exit(1)
