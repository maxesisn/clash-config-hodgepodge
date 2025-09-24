import os
import httpx
import ruamel.yaml
from copy import deepcopy

yaml = ruamel.yaml.YAML()
yaml.indent(mapping=4)
yaml.encoding = "utf-8"
yaml.default_flow_style = False
yaml.allow_unicode = True

headers = {'user-agent': 'clash-ver/1.18.0'}

# 读取自定义配置
with open("custom_config.yaml", "r", encoding="utf-8") as f:
    custom_config = yaml.load(f)

base_config_url = custom_config["base_sub"]
output = custom_config["output"]
output_extra = output.replace(".yaml", "_extra.yaml")

# 下载配置文件，保存到base.yaml
with httpx.Client(headers=headers) as client:
    r = client.get(base_config_url)
    with open("base.yaml", "wb") as f:
        f.write(r.content)

# 读取配置文件
with open("base.yaml", "r", encoding="utf-8") as f:
    base = yaml.load(f)


# 清空proxies
base["proxies"] = []

allowed_proxies = ["DIRECT", "REJECT", "Auto - UrlTest", "Proxy"]

# 修改每个proxy-group的proxies部分
for group in base['proxy-groups']:
    if 'proxies' in group:
        group['proxies'] = [proxy for proxy in group['proxies'] if proxy in allowed_proxies]

custom_proxies: list = custom_config["proxies"]

custom_rules = custom_config["rules"]

for rule in custom_rules:
    base["rules"].insert(0, rule)
    
# 添加自定义配置
for proxy in custom_proxies:
    base["proxies"].append(proxy)
    for group in base["proxy-groups"]:
        group["proxies"].append(proxy["name"])
        if group["type"] == "url-test":
            group["interval"] = 30


# 保存配置文件
with open(output, "w", encoding="utf-8") as f:
    yaml.dump(base, f)

# 下载第三方订阅，取出其中的proxy部分
sub_custom_proxies = []
if "sources" in custom_config and custom_config["sources"] is not None and len(custom_config["sources"]) > 0:
    for source in custom_config["sources"]:
        with httpx.Client(headers=headers) as client:
            r = client.get(source)
            proxies = yaml.load(r.text)
            for proxy in proxies["proxies"]:
                sub_custom_proxies.append(proxy)

proxies_blacklist = custom_config["proxies_blacklist"]
proxies_superwhitelist = custom_config["proxies_superwhitelist"]

# 过滤节点名含有关键字的节点
for keyword in proxies_blacklist:
    sub_custom_proxies = [proxy for proxy in sub_custom_proxies if keyword not in proxy["name"]]

# 含有机场节点的改为600间隔
for proxy in sub_custom_proxies:
    for group in base["proxy-groups"]:
        group["proxies"].append(proxy["name"])
        if group["type"] == "url-test":
            group["interval"] = 600

if proxies_superwhitelist:
    base_proxy_pg = [pg for pg in base["proxy-groups"] if pg["name"] == "Auto - UrlTest"][0]
    base_sw_pg = deepcopy(base_proxy_pg)
    qualified_proxies = []
    for p_b in base_sw_pg["proxies"]:
        if any(p_sw in p_b for p_sw in proxies_superwhitelist):
            qualified_proxies.append(p_b)
    base_sw_pg["name"] = "SuperWhite"
    base_sw_pg["proxies"] = deepcopy(qualified_proxies)
    base["proxy-groups"].append(base_sw_pg)

# 重新生成base 保存额外proxies
base["proxies"].extend(sub_custom_proxies)

with open(output_extra, "w", encoding="utf-8") as f:
    yaml.dump(base, f)

# 删除base.yaml
os.remove("base.yaml")
