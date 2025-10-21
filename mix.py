import os
import httpx
import ruamel.yaml
from copy import deepcopy
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

yaml = ruamel.yaml.YAML()
yaml.indent(mapping=4)
yaml.encoding = "utf-8"
yaml.default_flow_style = False
yaml.allow_unicode = True

headers = {'user-agent': 'clash-ver/1.18.0'}


def load_config():
    """
    加载配置文件，支持新旧两种格式

    新格式：
    proxies: [...]  # 统一节点配置
    clash:
      enabled: true
      output: xxx
      base_sub: xxx
      ...

    旧格式（向后兼容）：
    output: xxx
    base_sub: xxx
    proxies: [...]
    ...
    """
    with open("custom_config.yaml", "r", encoding="utf-8") as f:
        config = yaml.load(f)

    # 检测配置格式
    if "clash" in config and isinstance(config["clash"], dict):
        logger.info("检测到新格式配置（clash配置块）")
        return config, True
    else:
        logger.info("检测到旧格式配置（向后兼容模式）")
        return config, False


def get_clash_config(config, is_new_format):
    """
    获取Clash配置参数

    Args:
        config: 完整配置
        is_new_format: 是否为新格式

    Returns:
        dict: Clash配置参数
    """
    if is_new_format:
        clash_config = config.get("clash", {})

        # 检查是否启用
        if not clash_config.get("enabled", True):
            logger.info("Clash配置已禁用")
            return None

        # 获取统一节点配置
        unified_proxies = config.get("proxies", [])

        return {
            "output": clash_config.get("output"),
            "base_sub": clash_config.get("base_sub"),
            "proxies": unified_proxies,  # 使用统一节点配置
            "sources": clash_config.get("sources", []),
            "proxies_blacklist": clash_config.get("proxies_blacklist", []),
            "proxies_superwhitelist": clash_config.get("proxies_superwhitelist", []),
            "rules": clash_config.get("rules", []),
        }
    else:
        # 旧格式兼容
        return {
            "output": config.get("output"),
            "base_sub": config.get("base_sub"),
            "proxies": config.get("proxies", []),
            "sources": config.get("sources", []),
            "proxies_blacklist": config.get("proxies_blacklist", []),
            "proxies_superwhitelist": config.get("proxies_superwhitelist", []),
            "rules": config.get("rules", []),
        }


# 读取自定义配置
custom_config, is_new_format = load_config()

# 获取Clash配置
clash_config = get_clash_config(custom_config, is_new_format)

if not clash_config:
    logger.info("跳过Clash配置生成")
    exit(0)

# 检查必要参数
if not clash_config["output"] or not clash_config["base_sub"]:
    logger.error("缺少必要的Clash配置参数: output 或 base_sub")
    exit(1)

base_config_url = clash_config["base_sub"]
output = clash_config["output"]
output_extra = output.replace(".yaml", "_extra.yaml")

logger.info(f"Clash输出路径: {output}")
logger.info(f"Clash额外输出路径: {output_extra}")

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

custom_proxies: list = clash_config["proxies"]
custom_rules = clash_config["rules"]

logger.info(f"添加 {len(custom_proxies)} 个自定义代理节点")
logger.info(f"添加 {len(custom_rules)} 条自定义规则")

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
sources = clash_config["sources"]
if sources and len(sources) > 0:
    logger.info(f"从 {len(sources)} 个订阅源下载节点")
    for source in sources:
        try:
            with httpx.Client(headers=headers) as client:
                r = client.get(source)
                proxies = yaml.load(r.text)
                count = len(proxies["proxies"])
                for proxy in proxies["proxies"]:
                    sub_custom_proxies.append(proxy)
                logger.info(f"  从 {source[:50]}... 获取 {count} 个节点")
        except Exception as e:
            logger.error(f"  下载订阅源失败: {source[:50]}... - {e}")

proxies_blacklist = clash_config["proxies_blacklist"]
proxies_superwhitelist = clash_config["proxies_superwhitelist"]

# 过滤节点名含有关键字的节点
original_count = len(sub_custom_proxies)
for keyword in proxies_blacklist:
    sub_custom_proxies = [proxy for proxy in sub_custom_proxies if keyword not in proxy["name"]]
filtered_count = original_count - len(sub_custom_proxies)
if filtered_count > 0:
    logger.info(f"黑名单过滤: 移除 {filtered_count} 个节点")

# 含有机场节点的改为600间隔
for proxy in sub_custom_proxies:
    for group in base["proxy-groups"]:
        group["proxies"].append(proxy["name"])
        if group["type"] == "url-test":
            group["interval"] = 600

if proxies_superwhitelist:
    logger.info(f"创建SuperWhite代理组，白名单关键词: {proxies_superwhitelist}")
    base_proxy_pg = [pg for pg in base["proxy-groups"] if pg["name"] == "Auto - UrlTest"][0]
    base_sw_pg = deepcopy(base_proxy_pg)
    qualified_proxies = []
    for p_b in base_sw_pg["proxies"]:
        if any(p_sw in p_b for p_sw in proxies_superwhitelist):
            qualified_proxies.append(p_b)
    base_sw_pg["name"] = "SuperWhite"
    base_sw_pg["proxies"] = deepcopy(qualified_proxies)
    base["proxy-groups"].append(base_sw_pg)
    logger.info(f"SuperWhite代理组包含 {len(qualified_proxies)} 个节点")

# 重新生成base 保存额外proxies
base["proxies"].extend(sub_custom_proxies)

logger.info(f"总计 {len(base['proxies'])} 个代理节点")
logger.info(f"总计 {len(base['proxy-groups'])} 个代理组")
logger.info(f"总计 {len(base['rules'])} 条规则")

with open(output_extra, "w", encoding="utf-8") as f:
    yaml.dump(base, f)

logger.info(f"✓ Clash配置已生成: {output_extra}")

# 删除base.yaml
os.remove("base.yaml")

logger.info("✓ Clash配置处理完成")
