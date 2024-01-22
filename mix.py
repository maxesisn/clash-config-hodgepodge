import os
import httpx
import ruamel.yaml

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

# 下载第三方订阅，取出其中的proxy部分
for source in custom_config["sources"]:
    with httpx.Client(headers=headers) as client:
        r = client.get(source)
        proxies = yaml.load(r.text)
        for proxy in proxies["proxies"]:
            if proxy["name"] not in allowed_proxies:
                custom_proxies.append(proxy)
                
proxies_blacklist = custom_config["proxies_blacklist"]

# 过滤节点名含有关键字的节点
for proxy in custom_proxies:
    for keyword in proxies_blacklist:
        if keyword in proxy["name"]:
            custom_proxies.remove(proxy)
            break
        
# 修改url-test类型的节点interval为300
for proxy in custom_proxies:
    if proxy["type"] == "url-test":
        proxy["interval"] = 300

# 添加自定义配置
for proxy in custom_proxies:
    base["proxies"].append(proxy)
    for group in base["proxy-groups"]:
        group["proxies"].append(proxy["name"])

custom_rules = custom_config["rules"]

for rule in custom_rules:
    base["rules"].insert(0, rule)

# 保存配置文件
with open(output, "w", encoding="utf-8") as f:
    yaml.dump(base, f)

# 删除base.yaml
os.remove("base.yaml")
