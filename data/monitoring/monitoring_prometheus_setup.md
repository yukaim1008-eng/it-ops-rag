# Prometheus + Grafana 监控系统搭建

## 架构概述

Prometheus 负责采集和存储时序指标数据，node_exporter 暴露主机级别的系统指标（CPU、内存、磁盘、网络），Grafana 进行可视化仪表盘展示，Alertmanager 负责告警路由和通知。

```
node_exporter → Prometheus → Grafana（可视化）
                          → Alertmanager → 企业微信/钉钉/邮件（告警通知）
```

## 安装部署

### 1. 安装 Prometheus

```bash
# 下载并解压
wget https://github.com/prometheus/prometheus/releases/download/v3.0.0/prometheus-3.0.0.linux-amd64.tar.gz
tar xzf prometheus-*.tar.gz
cd prometheus-*

# 配置 prometheus.yml（见下方）
vim prometheus.yml

# 启动
./prometheus --config.file=prometheus.yml &
```
默认监听 9090 端口，访问 `http://localhost:9090` 可查看 Prometheus Web UI。

### 2. 配置 prometheus.yml

```yaml
global:
  scrape_interval: 15s      # 采集间隔
  evaluation_interval: 15s  # 告警规则评估间隔

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']

rule_files:
  - "alerts/*.yml"

scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
        labels:
          env: 'production'
          team: 'ops'

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

### 3. 安装 node_exporter

```bash
# 下载并启动
wget https://github.com/prometheus/node_exporter/releases/download/v1.8.0/node_exporter-1.8.0.linux-amd64.tar.gz
tar xzf node_exporter-*.tar.gz
./node_exporter &
```
默认监听 9100 端口，提供 CPU、内存、磁盘、网络等主机级别指标。每个被监控的主机都需要安装一个 node_exporter。

### 4. 安装 Grafana

```bash
# Ubuntu/Debian
sudo apt-get install -y software-properties-common wget
sudo wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key
echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt-get update && sudo apt-get install -y grafana
sudo systemctl start grafana-server
```
默认监听 3000 端口，初始账号 `admin` / `admin`，首次登录需修改密码。

### 5. 导入 Grafana 仪表盘

- 登录 Grafana → Connections → Data Sources → 添加 Prometheus（URL 填 `http://localhost:9090`）
- Dashboards → Import → 输入 Dashboard ID `1860`（Node Exporter Full 面板，社区维护的经典仪表盘）
- 选择 Prometheus 数据源，导入

## 常用告警规则

```yaml
groups:
  - name: node_alerts
    rules:
      - alert: HighCPU
        expr: 100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "主机 {{ $labels.instance }} CPU 使用率 > 80%"

      - alert: HighMemory
        expr: (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "主机 {{ $labels.instance }} 内存使用率 > 90%"

      - alert: DiskFull
        expr: (node_filesystem_size_bytes{fstype!="tmpfs"} - node_filesystem_free_bytes{fstype!="tmpfs"}) / node_filesystem_size_bytes{fstype!="tmpfs"} * 100 > 85
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "主机 {{ $labels.instance }} 磁盘使用率 > 85%"

      - alert: NodeDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "主机 {{ $labels.instance }} 已下线超过1分钟"
```

### PromQL 常用查询

- CPU 使用率：`100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)`
- 内存使用率：`(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100`
- 磁盘使用率：`(node_filesystem_size_bytes - node_filesystem_free_bytes) / node_filesystem_size_bytes * 100`
- 网络流量：`rate(node_network_receive_bytes_total[5m])`
- 主机在线状态：`up`

## 常见问题

### Prometheus 不采集指标
- 检查 targets 页面（`http://localhost:9090/targets`）确认 target 状态是否为 UP
- 检查 node_exporter 是否在监听：`curl http://localhost:9100/metrics` 应返回大量指标
- 检查防火墙是否放行 9100 端口

### Grafana 无数据显示
- 检查 Data Source 配置中 Prometheus URL 是否正确
- 在 Grafana 的 Explore 页面中输入 `up` 查询，确认数据源连通
- 检查 Prometheus 的时间范围和 Grafana 仪表盘的时间范围是否匹配

### 告警不触发
- 在 Prometheus 的 Alerts 页面查看告警规则的状态（绿色=正常，红色=Firing）
- 检查 Alertmanager 是否运行：`curl http://localhost:9093/api/v2/status`
- 检查告警规则的 `for` 字段——条件需要持续满足指定时间才会触发

## 预防措施

- Prometheus 数据持久化：配置 `--storage.tsdb.path` 和 `--storage.tsdb.retention.time`（建议保留 30 天）
- Grafana 仪表盘备份：将 JSON 模型导出并存入 Git 仓库，实现 Infrastructure as Code
- 配置告警静默和路由：按严重级别（warning/critical）分组，critical 级别电话/短信通知
- 监控 Prometheus 自身：Prometheus 也暴露自身指标，可监控其采集延迟、存储使用率等
