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

with open(os.path.join(self_path, "mix_config.yaml"), 'r') as f:
    mix_config = yaml.load(f)
    custom_servers = mix_config["custom_servers"]
    backends = mix_config["backends"]
    config_proxies = mix_config["proxy"]
    config_dst = mix_config["config_dst"]
    use_cache = mix_config["use_cache"]
    auto_group_whitelist = mix_config["auto_group_whitelist"]
    custom_rules = mix_config["custom_rules"]

proxies = None

# cache is mainly for debug porpose, should be disabled in production
def get_with_cache(url: str, filename: str) -> str:
    cache_dir = os.path.join(self_path, "cache")
    cached_list = os.listdir(cache_dir)
    if use_cache and filename in cached_list and time.time() - os.path.getmtime(os.path.join(cache_dir, filename)) < 3600:
        file_mod_time = os.path.getmtime(os.path.join(cache_dir, filename))
        with open(os.path.join(cache_dir, filename), "r") as f:
            return f.read()
    else:
        r = httpx.get(url, proxies=proxies).text
        if use_cache:
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


regions = {
    "HK": ["香港", "🇭🇰"],
    "JP": ["日本", "🇯🇵"],
    "SG": ["新加坡", "🇸🇬"],
    "TW": ["台湾", "🇹🇼"],
    "US": ["美国", "🇺🇸"],
    "CN": ["中国", "🇨🇳", "China"],
    "Worldwide": ["边缘"]
}

pg_template = '''
  - name: {{name}}
    type: select
    proxies:
      - HK
      - JP
      - SG
      - TW
      - US
      - CN
      - Worldwide
'''


def base_pg_gen(group_rules: list[str]) -> str:
    pg_str = "\nproxy-groups:\n"
    for rule in group_rules:
        pg_str += pg_template.replace("{{name}}", rule)
    pg_str += "\nproxies: []\n"
    return pg_str


backends_r = dict()

for back_name in backends:
    for i in range(5):
        try:
            resource = get_with_cache(backends[back_name], back_name)
            if resource is None:
                print(f"resource <{back_name}> corrupted")
                exit()
            backends_r[back_name] = yaml.load(resource)
            break
        except ConnectionException:
            print(f"Failed to fetch backend <{back_name}>, retrying..."+str(i+1))
        if i == 1:
            print(f"Failed to fetch backend <{back_name}> directly, try to use proxy")
            proxies = config_proxies




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

china_pg = ["Domestic", "Asian TV", "Scholar", "Speedtest"]

base_header = base_header.replace("{2,4}", "{2,5}")
base_header = yaml.load(base_header)
base_rule = yaml.load(base_rule)
base_rule["rules"] = custom_rules+base_rule["rules"]
rule_groups = rule_extractor(base_rule["rules"])
base_pg = yaml.load(base_pg_gen(rule_groups))
for pg in base_pg["proxy-groups"]:
    if pg["name"] in china_pg:
        pg["proxies"].insert(0, "DIRECT")
        pg["proxies"].insert(1, "Proxy")
    else:
        pg["proxies"].insert(0, "Proxy")
        pg["proxies"].insert(1, "DIRECT")

    if pg["name"] == "AdBlock":
        pg["proxies"].insert(0, "REJECT")
    elif pg["name"] == "Google":
        pg["proxies"].extend([x["name"] for x in custom_servers])
    
base_config = base_header | base_pg | base_rule

external_servers = list()

for n in backends_r:
    if "proxies" in backends_r[n]:
        for x in backends_r[n]["proxies"]:
            x["name"] = f"[{n}]{x['name']}"
            external_servers.append(x)
if len(external_servers) < 1:
    exit(1)


external_servers.extend(custom_servers)

for server in external_servers:
    base_config["proxies"].append(dict(server))


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
        "url": "http://cp.cloudflare.com/generate_204",
        "interval": "300",
        "proxies": ["Worldwide"]
    }

for server in external_servers:
    try:
        server_region = next(key for key, value in regions.items() if any(
            x in server["name"] for x in value))
        group_cata_regions[server_region]["proxies"].append(server["name"])
        for word in auto_group_whitelist:
            if word in server["name"]:
                group_cata_regions_auto[server_region]["proxies"].append(
                    server["name"])
    except StopIteration:
        group_cata_regions["Worldwide"]["proxies"].append(server["name"])
        group_cata_regions_auto["Worldwide"]["proxies"].append(server["name"])

for region in group_cata_regions:
    base_config["proxy-groups"] = [group_cata_regions[region]] + \
        base_config["proxy-groups"]

base_config["proxy-groups"] = [group_cata_proxy] + base_config["proxy-groups"]

auto_proxy_flag = 0
for region in group_cata_regions_auto:
    if len(group_cata_regions_auto[region]["proxies"]) != 0 and auto_proxy_flag == 0:
        auto_proxy_flag = 1
    base_config["proxy-groups"].append(group_cata_regions_auto[region])

    
if not auto_proxy_flag:
    print(f"Error: No auto proxy found")
    exit()

with open(config_dst, "w") as file:
    yaml.dump(base_config, file)
print("success")