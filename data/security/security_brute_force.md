# 暴力破解 / 异常登录诊断与处理

## 问题现象

认证日志出现大量失败登录（同一 IP 反复试、或一个 IP 撞多个账号）；SSH / 后台管理 / 数据库被持续爆破；账号偶发被锁定；出现异常地点 / 异常时间的登录成功记录。

## 排查步骤

### 1. 统计失败登录与来源 IP

```bash
# Linux SSH 失败登录
grep "Failed password" /var/log/auth.log | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head
lastb | head -20                 # 最近失败登录记录
# 是否有失败后又成功的可疑 IP
grep "Accepted password" /var/log/auth.log
```

### 2. 看暴露面

```bash
ss -lntp | grep -E ':22|:3306|:6379'   # 敏感服务是否直接暴露公网
# 云控制台检查安全组是否对 0.0.0.0/0 开放了 SSH / DB 端口
```

## 常见原因

- **弱口令** + 公网直接暴露 SSH / 数据库 / 后台。
- 未限制登录失败次数，可无限尝试。
- 使用默认端口、默认账号（root / admin）。
- 无多因素认证（MFA）。

## 解决方案

### 临时止血

```bash
# 用 fail2ban 自动封禁高频失败 IP
systemctl status fail2ban
# 临时手动封禁
iptables -A INPUT -s <恶意IP> -j DROP
```

### 根本修复

- SSH 改**密钥登录、禁用密码、禁 root 直登**，改非默认端口。
- 敏感服务**不暴露公网**：走 VPN / 堡垒机 / 内网，安全组最小放行。
- 启用 **MFA / 多因素认证**，强口令策略 + 登录失败锁定。
- 部署 fail2ban / WAF 自动封禁爆破源。

## 预防措施

- 登录失败率、异常地点登录监控告警。
- 定期巡检暴露端口与登录日志。
- 最小权限 + 定期轮换凭据，关键系统强制 MFA。
