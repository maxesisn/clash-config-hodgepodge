import httpx
import ruamel.yaml
import os
import time

yaml = ruamel.yaml.YAML()
yaml.indent(mapping=4)
yaml.encoding = "utf-8"
yaml.default_flow_style = False
yaml.allow_unicode = True

ConnectionException = (httpx.ConnectTimeout,
                       httpx.ReadTimeout, httpx.ConnectError)

self_path = os.path.dirname(os.path.realpath(__file__))

def get_with_cache(url: str, filename: str):
    cache_dir = os.path.join(self_path, "cache")
    cached_list = os.listdir(cache_dir)
    if filename in cached_list and time.time() - os.path.getmtime(os.path.join(cache_dir, filename)) < 3600:
        file_mod_time = os.path.getmtime(os.path.join(cache_dir, filename))
        with open(os.path.join(cache_dir, filename), "r") as f:
            return f.read()
    else:
        r = httpx.get(url).text
        with open(os.path.join(cache_dir, filename), "w") as f:
            f.write(r)
        return r


def rule_extractor(raw_rules: list) -> list[str]:
    group_rules = list()
    for rule in raw_rules:
        rule = rule.rsplit(',', 1)[1]
        group_rules.append(rule)
    group_rules = list(set(group_rules))
    blacklist = ["DIRECT", "REJECT", "Proxy", "GLOBAL"]
    for word in blacklist:
        if word in group_rules:
            group_rules.remove(word)
    return group_rules


pg_template = '''
  - name: {{name}}
    type: select
    proxies:
      - DIRECT
      - Proxy
      - HK
      - JP
      - SG
      - TW
      - US
      - Worldwide
'''


def base_pg_gen(group_rules: list[str]) -> str:
    pg_str = "\nproxy-groups:\n"
    for rule in group_rules:
        pg_str += pg_template.replace("{{name}}", rule)
    pg_str += "\nproxies: []\n"
    return pg_str


with open(os.path.join(self_path, "mix_config.yaml"), 'r') as f:
    mix_config = yaml.load(f)
    custom_servers = mix_config["custom_servers"]
    backends = mix_config["backends"]
    proxies = mix_config["proxy"]
    config_dst = mix_config["config_dst"]

backends_r = dict()

for i in range(10):
    try:
        for back_name in backends:
            resource = get_with_cache(backends[back_name], back_name)
            if resource is None or "eval" in resource:
                exit()
            backends_r[back_name] = yaml.load(resource)
        break
    except ConnectionException:
        print(f"Failed to fetch backend, retrying..."+str(i+1))


print("data downloaded")

base_config = dict()

for i in range(10):
    try:
        base_header = get_with_cache(
            "https://fastly.jsdelivr.net/gh/dler-io/Rules@main/Clash/Head_dns.yaml", "Head_dns.yaml")
        base_rule = get_with_cache(
            "https://fastly.jsdelivr.net/gh/dler-io/Rules@main/Clash/Rule.yaml", "Rule.yaml")
        base_rule = "rules:\n"+base_rule
        break
    except ConnectionException:
        print(f"Failed to fetch base config, retrying..."+str(i+1))

print("base config downloaded")

base_header = yaml.load(base_header)
base_rule = yaml.load(base_rule)
base_pg = yaml.load(base_pg_gen(rule_extractor(base_rule["rules"])))

base_config = base_header | base_pg | base_rule

external_servers = list()

for n in backends_r:
    external_servers.extend(list(backends_r[n]["proxies"]))


external_servers.extend(custom_servers)

for server in external_servers:
    base_config["proxies"].append(dict(server))


regions = {
    "HK": ["香港"],
    "JP": ["日本"],
    "SG": ["新加坡"],
    "TW": ["台湾"],
    "US": ["美国"],
    "Worldwide": ["边缘"]
}

group_cata_proxy = {
    "name": "Proxy",
    "type": "select",
    "proxies": [
        "DIRECT"
    ]
}

for k in regions.keys():
    group_cata_proxy["proxies"].append(k)
    group_cata_proxy["proxies"].append(k + " - Auto")

group_cata_google = {
    "name": "Google",
    "type": "select",
    "proxies": [
        "DIRECT"
    ]
}

group_cata_google["proxies"].extend(regions.keys())
group_cata_google["proxies"].extend([x["name"] for x in custom_servers])

group_cata_regions = dict()
for region in regions:
    group_cata_regions[region] = {
        "name": region,
        "type": "select",
        "proxies": []
    }

group_cata_regions_auto = dict()
for region in regions:
    group_cata_regions_auto[region] = {
        "name": region+" - Auto",
        "type": "url-test",
        "url": "http://cp.cloudflare.com//generate_204",
        "interval": "3600",
        "proxies": []
    }

for server in external_servers:
    auto_whitelist = ["实验性 IEPL 中继", "高级 IEPL 中继"]
    try:
        server_region = next(key for key, value in regions.items() if any(
            x in server["name"] for x in value))
        group_cata_regions[server_region]["proxies"].append(server["name"])
        for word in auto_whitelist:
            if word in server["name"]:
                group_cata_regions_auto[server_region]["proxies"].append(
                    server["name"])
    except StopIteration:
        group_cata_regions["Worldwide"]["proxies"].append(server["name"])
        group_cata_regions_auto["Worldwide"]["proxies"].append(server["name"])

for region in group_cata_regions:
    base_config["proxy-groups"] = [group_cata_regions[region]] + \
        base_config["proxy-groups"]

base_config["proxy-groups"] = [group_cata_google] + base_config["proxy-groups"]
base_config["proxy-groups"] = [group_cata_proxy] + base_config["proxy-groups"]

for region in group_cata_regions_auto:
    base_config["proxy-groups"].append(group_cata_regions_auto[region])


with open(config_dst, "w") as file:
    yaml.dump(base_config, file)
