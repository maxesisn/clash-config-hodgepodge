"""测试 fake-ip-filter 通配符到 rule 模式的转换。"""
from fakeip_convert import convert_fakeip_filter_entry, convert_fakeip_filters


def test_suffix_patterns():
    """+.xxx 和 *.xxx 都应转为 DOMAIN-SUFFIX"""
    assert convert_fakeip_filter_entry("+.lan") == "DOMAIN-SUFFIX,lan,real-ip"
    assert convert_fakeip_filter_entry("+.local") == "DOMAIN-SUFFIX,local,real-ip"
    assert convert_fakeip_filter_entry("*.lan") == "DOMAIN-SUFFIX,lan,real-ip"
    assert convert_fakeip_filter_entry("*.pool.ntp.org") == "DOMAIN-SUFFIX,pool.ntp.org,real-ip"
    assert convert_fakeip_filter_entry("+.music.163.com") == "DOMAIN-SUFFIX,music.163.com,real-ip"


def test_exact_domain():
    """无通配符 → DOMAIN 精确匹配"""
    assert convert_fakeip_filter_entry("lens.l.google.com") == "DOMAIN,lens.l.google.com,real-ip"
    assert convert_fakeip_filter_entry("localhost.ptlogin2.qq.com") == "DOMAIN,localhost.ptlogin2.qq.com,real-ip"
    assert convert_fakeip_filter_entry("musicapi.taihe.com") == "DOMAIN,musicapi.taihe.com,real-ip"


def test_middle_wildcard():
    """中间通配符 → DOMAIN-REGEX"""
    result = convert_fakeip_filter_entry("time.*.com")
    assert result == r"DOMAIN-REGEX,^time\.[^.]*\.com$,real-ip"

    result = convert_fakeip_filter_entry("time.*.edu.cn")
    assert result == r"DOMAIN-REGEX,^time\.[^.]*\.edu\.cn$,real-ip"

    result = convert_fakeip_filter_entry("ntp.*.com")
    assert result == r"DOMAIN-REGEX,^ntp\.[^.]*\.com$,real-ip"


def test_multi_level_wildcard():
    """+.stun.*.* 等多级通配"""
    result = convert_fakeip_filter_entry("+.stun.*.*")
    assert result == r"DOMAIN-REGEX,^.*\.stun\.[^.]*\.[^.]*$,real-ip"

    result = convert_fakeip_filter_entry("+.stun.*.*.*")
    assert result == r"DOMAIN-REGEX,^.*\.stun\.[^.]*\.[^.]*\.[^.]*$,real-ip"

    result = convert_fakeip_filter_entry("*.n.n.srv.nintendo.net")
    assert result == "DOMAIN-SUFFIX,n.n.srv.nintendo.net,real-ip"


def test_geosite_and_ruleset():
    """geosite: 和 rule-set: 前缀"""
    assert convert_fakeip_filter_entry("geosite:cn") == "GEOSITE,cn,real-ip"
    assert convert_fakeip_filter_entry("geosite:private,cn") == "GEOSITE,private,cn,real-ip"
    assert convert_fakeip_filter_entry("rule-set:my-cn-rules") == "RULE-SET,my-cn-rules,real-ip"


def test_batch_with_force_proxy():
    """批量转换 + 强制 fake-ip 例外域名"""
    filters = [
        "+.lan",
        "+.local",
        "time.*.com",
        "lens.l.google.com",
        "geosite:cn",
    ]
    force = ["bigo.tv", "some-service.com"]

    result = convert_fakeip_filters(filters, force)

    # 强制 fake-ip 的域名在最前面
    assert result[0] == "DOMAIN-SUFFIX,bigo.tv,fake-ip"
    assert result[1] == "DOMAIN-SUFFIX,some-service.com,fake-ip"

    # 后续是转换后的 real-ip 规则
    assert result[2] == "DOMAIN-SUFFIX,lan,real-ip"
    assert result[3] == "DOMAIN-SUFFIX,local,real-ip"
    assert result[4] == r"DOMAIN-REGEX,^time\.[^.]*\.com$,real-ip"
    assert result[5] == "DOMAIN,lens.l.google.com,real-ip"
    assert result[6] == "GEOSITE,cn,real-ip"


def test_batch_without_force():
    """无例外域名时也正常工作"""
    filters = ["+.lan", "*.local"]
    result = convert_fakeip_filters(filters)
    assert result == ["DOMAIN-SUFFIX,lan,real-ip", "DOMAIN-SUFFIX,local,real-ip"]


def test_empty_and_edge_cases():
    assert convert_fakeip_filter_entry("") == ""
    assert convert_fakeip_filter_entry("  ") == ""
    assert convert_fakeip_filters([], []) == []
    assert convert_fakeip_filters([], None) == []


if __name__ == "__main__":
    test_suffix_patterns()
    test_exact_domain()
    test_middle_wildcard()
    test_multi_level_wildcard()
    test_geosite_and_ruleset()
    test_batch_with_force_proxy()
    test_batch_without_force()
    test_empty_and_edge_cases()
    print("所有测试通过!")
