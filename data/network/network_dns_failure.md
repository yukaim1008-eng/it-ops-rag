# DNS 解析失败故障排查

## 问题现象

服务器无法解析域名，`ping www.baidu.com` 提示 "unknown host" 或 "Name or service not known"，但直接 ping IP 地址（如 `ping 8.8.8.8`）可以通，说明网络连通性正常但 DNS 解析链路有问题。

## 排查步骤

### 1. 确认 DNS 配置

```bash
# 查看当前 DNS 服务器配置
cat /etc/resolv.conf

# 使用 systemd-resolved 的系统查看
systemd-resolve --status

# 查看网卡 DNS（NetworkManager 管理时）
nmcli dev show | grep DNS
```

### 2. 手动测试 DNS 解析

```bash
# 使用 nslookup 测试
nslookup www.baidu.com

# 使用 dig 测试（输出更详细）
dig www.baidu.com

# 指定使用 Google DNS 测试（排除本地 DNS 服务器问题）
dig @8.8.8.8 www.baidu.com

# 追踪 DNS 解析全过程
dig +trace www.baidu.com
```

### 3. 检查 DNS 相关服务状态

```bash
# systemd-resolved 服务
systemctl status systemd-resolved
systemctl restart systemd-resolved

# nscd（Name Service Cache Daemon）
systemctl status nscd
nscd -i hosts          # 清除 hosts 缓存

# dnsmasq（如果使用本地 DNS 缓存）
systemctl status dnsmasq
```

### 4. 检查防火墙与端口

```bash
# DNS 使用 UDP 53 端口，检查防火墙规则
iptables -L -n -v | grep 53

# 测试 UDP 53 端口连通性
nc -zvu 8.8.8.8 53
```

## 常见原因

### 原因一：/etc/resolv.conf 配置错误
nameserver 地址不可达或未配置。常见于服务器迁移后 DNS 服务器 IP 变更但配置未更新。

### 原因二：systemd-resolved 故障
systemd-resolved 服务异常停止或配置冲突，导致 `/etc/resolv.conf` 软链接指向错误。

### 原因三：DNS 缓存中毒
本地 DNS 缓存中存在错误的解析记录。清除缓存即可恢复：`systemd-resolve --flush-caches`。

### 原因四：防火墙拦截 DNS 请求
安全组或 iptables 规则误拦截了 UDP 53 端口的出站请求。

### 原因五：上游 DNS 服务器故障
内网 DNS 服务器宕机或响应超时。测试方法：直接使用公共 DNS（`dig @8.8.8.8`）验证。

### 原因六：域名本身解析异常
域名过期、DNS 记录被误删、CDN 配置错误。通过 `dig +trace` 追踪权威 DNS 链路定位。

## 解决方案

### 临时止血

```bash
# 临时使用公共 DNS
echo "nameserver 8.8.8.8" >> /etc/resolv.conf
echo "nameserver 114.114.114.114" >> /etc/resolv.conf

# 清除本地 DNS 缓存
systemd-resolve --flush-caches
systemctl restart nscd

# 重启 DNS 相关服务
systemctl restart systemd-resolved
```

### 根本修复

- **配置多 DNS 服务器**：在 `/etc/resolv.conf` 或 NetworkManager 中配置主备 DNS，避免单点故障
- **搭建本地 DNS 缓存**：使用 dnsmasq 或 systemd-resolved 的缓存功能，减少对外部 DNS 的依赖
- **配置 DNS 解析超时与重试**：在 `/etc/resolv.conf` 中设置 `options timeout:1 attempts:2` 减少等待时间
- **监控 DNS 解析可用性**：使用 Prometheus Blackbox Exporter 监控 DNS 解析响应时间和成功率

## 预防措施

- 在 Prometheus 中添加 DNS 探活监控：`probe_dns_lookup_time_seconds`
- 告警规则：DNS 解析耗时 > 2 秒或解析失败率 > 1% 触发告警
- 定期检查 `/etc/resolv.conf` 配置一致性（使用配置管理工具如 Ansible）
- 记录所有 DNS 变更操作，便于回滚
