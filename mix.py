import os
import httpx
import ruamel.yaml

yaml = ruamel.yaml.YAML()
yaml.indent(mapping=4)
yaml.encoding = "utf-8"
yaml.default_flow_style = False
yaml.allow_unicode = True

# 读取自定义配置
with open("custom_config.yaml", "r", encoding="utf-8") as f:
    custom_config = yaml.load(f)

base_config_url = custom_config["base_sub"]
output = custom_config["output"]

# 下载配置文件，保存到base.yaml
with httpx.Client() as client:
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

custom_proxies = custom_config["proxies"]

# 添加自定义配置
for proxy in custom_proxies:
    base["proxies"].append(proxy)
    for group in base["proxy-groups"]:
        group["proxies"].append(proxy["name"])

# 保存配置文件
with open(output, "w", encoding="utf-8") as f:
    yaml.dump(base, f)

# 删除base.yaml
os.remove("base.yaml")