# Clash规则生成器

结合`Dler Cloud`与`Flower Cloud`的Clash配置文件格式，可配置自定义机场源/自定义节点/自定义规则。

## 如何使用

1. `cp mix_config_example.yaml mix_config.yaml`
2. 修改`config_dst`路径至生成最终配置文件的路径
3. 修改`proxy`使配置文件通过该http代理下载
4. 按`机场名: Clash订阅地址`格式修改`backends`
5. 在`custom_servers`中填入你自建的节点，格式与clash配置相同
6. 在`custom_rules`中加入你的自定义规则，这些规则会添加至`rule`部分头部

## 特殊处理

1. 对于`Domestic` `Asian TV` `Scholar` `Speedtest`策略组，使`DIRECT`作为第一选择
2. 对于`AdBlock`策略组，使`REJECT`作为第一选择
3. 对于`Google`策略组，填入所有自建服务器，便于规避人机验证
