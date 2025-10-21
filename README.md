# Clash & Surge 配置混合工具

统一管理 Clash 和 Surge 代理配置，支持从单一节点配置生成两种客户端的配置文件。

## ✨ 主要特性

- **统一节点配置**：只需配置一次节点信息，自动生成 Clash 和 Surge 两份配置
- **智能格式转换**：自动将 Clash 格式节点转换为 Surge 格式
- **订阅源整合**：支持从多个机场订阅源获取节点
- **黑白名单过滤**：灵活过滤和筛选节点
- **向后兼容**：完全兼容旧版配置格式

## 📦 支持的协议

| 协议 | Clash | Surge | 转换支持 |
|------|-------|-------|----------|
| Shadowsocks | ✅ | ✅ | ✅ 完美 |
| Trojan | ✅ | ✅ | ✅ 完美 |
| Snell | ✅ | ✅ | ✅ 完美 |
| HTTP/HTTPS | ✅ | ✅ | ✅ 完美 |
| VMess | ✅ | ⚠️ 部分 | ⚠️ 有限 |
| VLESS | ✅ | ❌ | ❌ 不支持 Reality/XTLS |

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install httpx ruamel.yaml
```

### 2. 配置文件

复制示例配置并修改：

```bash
cp custom_config_example.yaml custom_config.yaml
```

编辑 `custom_config.yaml`，使用新格式配置：

```yaml
# 统一节点配置（Clash格式）
proxies:
  - name: 🇭🇰 HK-SS
    type: ss
    server: 1.1.1.1
    port: 8388
    cipher: aes-256-gcm
    password: your-password

# Clash配置
clash:
  enabled: true
  output: /path/to/clash/config.yaml
  base_sub: https://your-clash-subscription-url

# Surge配置
surge:
  enabled: true
  output: /path/to/surge/config.conf
  base_sub: https://your-surge-subscription-url
```

### 3. 生成配置

```bash
# 生成 Clash 配置
python3 mix.py

# 生成 Surge 配置
python3 surge_mix.py
```

## 📝 配置说明

### 新格式（推荐）

新格式支持统一节点配置，一次定义，两处使用：

```yaml
# 统一节点配置
proxies:
  - name: 节点名称
    type: ss|trojan|snell|...
    server: 服务器地址
    port: 端口
    # 其他参数...

# Clash专属配置
clash:
  enabled: true                    # 是否启用
  output: /path/to/config.yaml     # 输出路径
  base_sub: https://...            # 基础订阅URL
  sources: [...]                   # 第三方订阅源（可选）
  proxies_blacklist: [...]         # 黑名单关键词（可选）
  proxies_superwhitelist: []       # 白名单关键词（可选）
  rules: [...]                     # 自定义规则（可选）

# Surge专属配置
surge:
  enabled: true                    # 是否启用
  output: /path/to/config.conf     # 输出路径
  base_sub: https://...            # 基础订阅URL
  rules: [...]                     # 自定义规则（可选）
```

### 旧格式（向后兼容）

如果不想使用统一配置，仍可使用旧格式：

```yaml
# Clash配置（顶层）
output: /path/to/config.yaml
base_sub: https://...
proxies: [...]
sources: [...]
rules: [...]

# Surge配置（独立块）
surge:
  output: /path/to/config.conf
  base_sub: https://...
  proxies: [...]        # Surge专用节点
  proxy_groups: [...]   # Surge代理组
  rules: [...]
```

## 🔧 高级功能

### 黑名单过滤

过滤掉包含特定关键词的节点：

```yaml
clash:
  proxies_blacklist:
    - 剩余流量
    - 过期时间
    - 官网
```

### 超级白名单

创建只包含特定关键词节点的 "SuperWhite" 代理组：

```yaml
clash:
  proxies_superwhitelist:
    - 香港
    - 台湾
    - IPLC
```

### 自定义规则

添加优先级最高的自定义规则：

```yaml
clash:
  rules:
    - DST-PORT,3478,DIRECT
    - DOMAIN-SUFFIX,local,DIRECT

surge:
  rules:
    - DOMAIN,example.com,DIRECT
    - IP-CIDR,192.168.0.0/16,DIRECT
```

## 🎯 工作原理

### Clash 配置生成流程

1. 从 `base_sub` 下载基础配置
2. 清空所有代理节点
3. 添加统一配置中的自定义节点
4. 从 `sources` 下载第三方订阅节点
5. 应用黑名单/白名单过滤
6. 添加自定义规则
7. 生成两份配置：
   - `config.yaml` - 仅包含自定义节点
   - `config_extra.yaml` - 包含所有节点

### Surge 配置生成流程

1. 从 `base_sub` 下载基础配置
2. 将统一配置中的节点转换为 Surge 格式
3. 添加转换后的节点到配置
4. 应用自定义规则（可选）
5. 生成配置文件

## 📚 节点转换说明

节点转换器会尽力将 Clash 格式转换为 Surge 格式：

- **Shadowsocks/Trojan/Snell**: 完美转换，100%兼容
- **HTTP/HTTPS**: 完美转换
- **VMess**: 基础转换，部分高级特性可能不支持
- **VLESS**: 如果包含 `flow` 或 `reality-opts`，则无法转换（会跳过）

### 建议

如果需要同时生成 Clash 和 Surge 配置：
- ✅ 推荐使用 Shadowsocks, Trojan, Snell
- ⚠️ 谨慎使用 VMess（可能需要额外配置）
- ❌ 避免使用 VLESS with Reality/XTLS（Surge不支持）

## 📄 文件说明

- `mix.py` - Clash 配置生成脚本
- `surge_mix.py` - Surge 配置生成脚本
- `surge_config.py` - Surge 配置解析库
- `converter.py` - 节点格式转换器
- `custom_config_example.yaml` - 配置文件示例

## 🛠️ 依赖

- Python 3.7+
- httpx - HTTP 客户端
- ruamel.yaml - YAML 处理

## 📝 License

MIT

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
