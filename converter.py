"""
节点格式转换器：Clash -> Surge

支持的协议转换：
- Shadowsocks (ss) -> Shadowsocks
- Snell -> Snell
- HTTP/HTTPS -> HTTP/HTTPS
- Trojan -> Trojan
- VLESS -> Trojan (尽力转换)
- VMess -> 部分支持
"""

from typing import Dict, Any, Optional, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProxyConverter:
    """代理节点格式转换器"""

    @staticmethod
    def clash_to_surge(clash_proxy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        将Clash格式的代理转换为Surge格式

        Args:
            clash_proxy: Clash格式的代理配置

        Returns:
            Surge格式的代理配置，如果无法转换则返回None
        """
        proxy_type = clash_proxy.get("type", "").lower()
        name = clash_proxy.get("name", "")

        if not name or not proxy_type:
            logger.warning(f"代理缺少必要字段: {clash_proxy}")
            return None

        # 根据不同协议类型进行转换
        converter_map = {
            "ss": ProxyConverter._convert_shadowsocks,
            "snell": ProxyConverter._convert_snell,
            "http": ProxyConverter._convert_http,
            "https": ProxyConverter._convert_https,
            "trojan": ProxyConverter._convert_trojan,
            "vless": ProxyConverter._convert_vless,
            "vmess": ProxyConverter._convert_vmess,
        }

        converter = converter_map.get(proxy_type)
        if converter:
            try:
                return converter(clash_proxy)
            except Exception as e:
                logger.error(f"转换代理 '{name}' ({proxy_type}) 失败: {e}")
                return None
        else:
            logger.warning(f"不支持的代理类型: {proxy_type} (节点: {name})")
            return None

    @staticmethod
    def _convert_shadowsocks(clash_proxy: Dict[str, Any]) -> Dict[str, Any]:
        """转换Shadowsocks节点"""
        surge_proxy = {
            "name": clash_proxy["name"],
            "type": "ss",
            "server": clash_proxy["server"],
            "port": clash_proxy["port"],
            "cipher": clash_proxy.get("cipher", "aes-256-gcm"),
            "password": clash_proxy.get("password", ""),
        }

        # 可选字段
        if "udp" in clash_proxy:
            surge_proxy["udp-relay"] = clash_proxy["udp"]

        if "plugin" in clash_proxy and clash_proxy["plugin"] == "obfs":
            opts = clash_proxy.get("plugin-opts", {})
            surge_proxy["obfs"] = opts.get("mode", "http")
            if "host" in opts:
                surge_proxy["obfs-host"] = opts["host"]

        return surge_proxy

    @staticmethod
    def _convert_snell(clash_proxy: Dict[str, Any]) -> Dict[str, Any]:
        """转换Snell节点"""
        surge_proxy = {
            "name": clash_proxy["name"],
            "type": "snell",
            "server": clash_proxy["server"],
            "port": clash_proxy["port"],
            "psk": clash_proxy.get("psk", ""),
            "version": clash_proxy.get("version", 4),
        }

        # 可选字段
        if "obfs-opts" in clash_proxy:
            obfs_opts = clash_proxy["obfs-opts"]
            if "mode" in obfs_opts:
                surge_proxy["obfs"] = obfs_opts["mode"]
            if "host" in obfs_opts:
                surge_proxy["obfs-host"] = obfs_opts["host"]

        return surge_proxy

    @staticmethod
    def _convert_http(clash_proxy: Dict[str, Any]) -> Dict[str, Any]:
        """转换HTTP代理"""
        surge_proxy = {
            "name": clash_proxy["name"],
            "type": "http",
            "server": clash_proxy["server"],
            "port": clash_proxy["port"],
        }

        # 认证信息
        if "username" in clash_proxy:
            surge_proxy["username"] = clash_proxy["username"]
        if "password" in clash_proxy:
            surge_proxy["password"] = clash_proxy["password"]

        # TLS
        if clash_proxy.get("tls"):
            surge_proxy["tls"] = True
            if "sni" in clash_proxy:
                surge_proxy["sni"] = clash_proxy["sni"]
            if "skip-cert-verify" in clash_proxy:
                surge_proxy["skip-cert-verify"] = clash_proxy["skip-cert-verify"]

        return surge_proxy

    @staticmethod
    def _convert_https(clash_proxy: Dict[str, Any]) -> Dict[str, Any]:
        """转换HTTPS代理"""
        surge_proxy = ProxyConverter._convert_http(clash_proxy)
        surge_proxy["tls"] = True
        return surge_proxy

    @staticmethod
    def _convert_trojan(clash_proxy: Dict[str, Any]) -> Dict[str, Any]:
        """转换Trojan节点"""
        surge_proxy = {
            "name": clash_proxy["name"],
            "type": "trojan",
            "server": clash_proxy["server"],
            "port": clash_proxy["port"],
            "password": clash_proxy.get("password", ""),
        }

        # SNI
        if "sni" in clash_proxy:
            surge_proxy["sni"] = clash_proxy["sni"]

        # 跳过证书验证
        if "skip-cert-verify" in clash_proxy:
            surge_proxy["skip-cert-verify"] = clash_proxy["skip-cert-verify"]

        # UDP
        if "udp" in clash_proxy:
            surge_proxy["udp-relay"] = clash_proxy["udp"]

        return surge_proxy

    @staticmethod
    def _convert_vless(clash_proxy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        转换VLESS节点
        注意：Surge不原生支持VLESS，这里尽力转换为相似的配置
        如果使用了XTLS等特性，可能无法完美转换
        """
        # VLESS with reality通常无法转换，记录警告
        if "reality-opts" in clash_proxy or "flow" in clash_proxy:
            logger.warning(
                f"VLESS节点 '{clash_proxy['name']}' 使用了Reality/XTLS特性，"
                "Surge不支持，跳过此节点"
            )
            return None

        # 尝试转换为Trojan（如果配置足够简单）
        logger.info(f"尝试将VLESS节点 '{clash_proxy['name']}' 转换为Trojan")
        surge_proxy = {
            "name": clash_proxy["name"],
            "type": "trojan",
            "server": clash_proxy["server"],
            "port": clash_proxy["port"],
            "password": clash_proxy.get("uuid", ""),  # UUID作为password
        }

        if "servername" in clash_proxy:
            surge_proxy["sni"] = clash_proxy["servername"]
        elif "sni" in clash_proxy:
            surge_proxy["sni"] = clash_proxy["sni"]

        if "skip-cert-verify" in clash_proxy:
            surge_proxy["skip-cert-verify"] = clash_proxy["skip-cert-verify"]

        logger.warning(
            f"VLESS节点 '{clash_proxy['name']}' 已转换为Trojan，"
            "但可能无法正常工作，建议使用原生Surge支持的协议"
        )

        return surge_proxy

    @staticmethod
    def _convert_vmess(clash_proxy: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换VMess节点
        注意：Surge对VMess的支持有限，仅支持基础配置
        """
        logger.warning(
            f"VMess节点 '{clash_proxy['name']}' 在Surge中支持有限，"
            "可能需要额外配置"
        )

        surge_proxy = {
            "name": clash_proxy["name"],
            "type": "vmess",
            "server": clash_proxy["server"],
            "port": clash_proxy["port"],
            "uuid": clash_proxy.get("uuid", ""),
            "alterId": clash_proxy.get("alterId", 0),
        }

        # 加密方式
        if "cipher" in clash_proxy:
            surge_proxy["cipher"] = clash_proxy["cipher"]

        # TLS
        if clash_proxy.get("tls"):
            surge_proxy["tls"] = True
            if "servername" in clash_proxy:
                surge_proxy["sni"] = clash_proxy["servername"]
            if "skip-cert-verify" in clash_proxy:
                surge_proxy["skip-cert-verify"] = clash_proxy["skip-cert-verify"]

        return surge_proxy


def convert_proxies_to_surge(clash_proxies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    批量转换Clash代理列表为Surge格式

    Args:
        clash_proxies: Clash格式的代理列表

    Returns:
        成功转换的Surge格式代理列表
    """
    surge_proxies = []

    for clash_proxy in clash_proxies:
        surge_proxy = ProxyConverter.clash_to_surge(clash_proxy)
        if surge_proxy:
            surge_proxies.append(surge_proxy)

    logger.info(f"成功转换 {len(surge_proxies)}/{len(clash_proxies)} 个代理节点")

    return surge_proxies


def render_surge_proxy(surge_proxy: Dict[str, Any]) -> str:
    """
    将Surge代理配置渲染为配置文件格式

    格式: name = type, server, port, key1=value1, key2=value2

    Args:
        surge_proxy: Surge格式的代理配置

    Returns:
        Surge配置文件格式的字符串
    """
    name = surge_proxy.pop("name")
    proxy_type = surge_proxy.pop("type")
    server = surge_proxy.pop("server")
    port = surge_proxy.pop("port")

    # 基础部分: name = type, server, port
    parts = [proxy_type, server, str(port)]

    # 其他参数按key=value格式添加
    for key, value in surge_proxy.items():
        if isinstance(value, bool):
            # 布尔值转为true/false
            parts.append(f"{key}={str(value).lower()}")
        elif isinstance(value, (int, float)):
            parts.append(f"{key}={value}")
        else:
            parts.append(f"{key}={value}")

    return f"{name} = {', '.join(parts)}"


if __name__ == "__main__":
    # 测试转换
    test_proxies = [
        {
            "name": "🇭🇰 HK-SS",
            "type": "ss",
            "server": "1.1.1.1",
            "port": 8388,
            "cipher": "aes-256-gcm",
            "password": "password123",
            "udp": True
        },
        {
            "name": "🇭🇰 HK-Snell",
            "type": "snell",
            "server": "2.2.2.2",
            "port": 4443,
            "psk": "example-psk",
            "version": 4,
        },
        {
            "name": "🇺🇸 US-Trojan",
            "type": "trojan",
            "server": "3.3.3.3",
            "port": 443,
            "password": "trojan-pass",
            "sni": "example.com",
            "udp": True
        },
    ]

    print("=== 测试Clash -> Surge转换 ===\n")
    surge_proxies = convert_proxies_to_surge(test_proxies)

    for surge_proxy in surge_proxies:
        print(render_surge_proxy(surge_proxy.copy()))
        print()
