# SSL/TLS 证书过期处理与监控

## 问题现象

用户访问网站时浏览器提示 "您的连接不是私密连接"（NET::ERR_CERT_DATE_INVALID），或监控系统发出证书即将过期的告警。使用 `curl` 访问返回 SSL 证书验证错误。

## 排查步骤

### 1. 确认证书状态

```bash
# 查看证书的生效时间和过期时间
openssl s_client -connect example.com:443 -servername example.com </dev/null 2>/dev/null | openssl x509 -noout -dates

# 查看证书的完整信息（颁发者、SAN域名等）
openssl s_client -connect example.com:443 -servername example.com </dev/null 2>/dev/null | openssl x509 -noout -text

# 检查证书链是否完整
openssl s_client -connect example.com:443 -servername example.com -showcerts </dev/null
```

### 2. 测试不同域名和端口

```bash
# 测试主域名
curl -I https://example.com

# 测试带 www 的子域名（SAN 证书可能不包含）
curl -I https://www.example.com

# 忽略证书验证直接测试（仅调试用）
curl -k -I https://example.com
```

### 3. 检查本地证书文件

```bash
# 检查 Nginx/Apache 配置中的证书路径
grep -E "ssl_certificate|SSLCertificateFile" /etc/nginx/conf.d/*.conf

# 验证本地证书文件是否与线上一致
openssl x509 -in /etc/ssl/certs/example.crt -noout -dates

# 验证私钥和证书是否匹配
openssl x509 -noout -modulus -in /etc/ssl/certs/example.crt | md5sum
openssl rsa -noout -modulus -in /etc/ssl/private/example.key | md5sum
# 两个 md5 值应该相同
```

### 4. 检查证书链完整性

```bash
# 使用在线工具或命令行检查
openssl verify -CAfile /etc/ssl/certs/ca-bundle.crt /etc/ssl/certs/example.crt

# 使用 SSL Labs 在线检测（生产环境推荐）
# https://www.ssllabs.com/ssltest/
```

## 常见原因

### 原因一：证书已过期
最常见的原因。证书没有及时续期，过了 `notAfter` 日期。

### 原因二：证书链不完整
缺少中间证书（Intermediate CA），导致浏览器无法验证证书的信任链。

### 原因三：域名与证书不匹配
证书的 SAN（Subject Alternative Name）或 CN（Common Name）与实际访问的域名不一致。

### 原因四：Let's Encrypt 续期失败
自动续期脚本（certbot）因 80 端口不通、DNS 验证失败、webroot 路径变更等原因失败。

### 原因五：时钟不同步
服务器系统时间与标准时间偏差过大，导致浏览器认为证书未生效或已过期。

### 原因六：证书被吊销
证书私钥泄露或其他原因导致 CA 吊销了证书（通过 CRL 或 OCSP 检查）。

## 解决方案

### 临时止血

**Let's Encrypt 证书续期**：
```bash
# 测试续期是否正常（不会真正执行）
certbot renew --dry-run

# 执行续期
certbot renew

# 续期后重载 Nginx
nginx -t && nginx -s reload
```

**手动续期并替换**：
```bash
# 如果是付费证书，重新下载后替换文件，然后重载
cp new.crt /etc/ssl/certs/example.crt
cp new.key /etc/ssl/private/example.key
systemctl reload nginx
```

### 根本修复

- **配置 certbot 自动续期**：`certbot renew` 命令放入 crontab（建议每天凌晨执行）或使用 systemd timer
- **确保证书链完整**：Nginx 配置中 `ssl_certificate` 应包含完整的证书链（服务器证书 + 中间证书拼接在一起）
- **配置 Nginx 的 OCSP Stapling**：减少客户端验证证书吊销状态的时间
  ```nginx
  ssl_stapling on;
  ssl_stapling_verify on;
  ssl_trusted_certificate /etc/ssl/certs/chain.pem;
  resolver 8.8.8.8 valid=300s;
  ```
- **同步系统时钟**：配置 NTP 服务，`systemctl enable chronyd` 或 `ntpdate -u ntp.aliyun.com`

## 预防措施

### Prometheus Blackbox Exporter 监控

```yaml
# prometheus.yml
- job_name: 'ssl_cert_monitor'
  metrics_path: /probe
  params:
    module: [tcp_connect]
  static_configs:
    - targets:
      - example.com:443
```

### 告警规则

```yaml
- alert: SSLCertExpiringSoon
  expr: probe_ssl_earliest_cert_expiry - time() < 86400 * 14
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "SSL 证书将在 14 天内过期，请及时续期"
```

### 手动定期检查脚本

```bash
#!/bin/bash
# check_ssl.sh —— 每周 crontab 执行，检查指定域名的证书剩余天数
DOMAIN=$1
DAYS=$(echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2)
echo "$DOMAIN 证书到期: $DAYS"
```

- 将续期操作纳入 CI/CD 或运维日历，证书到期前 30 天自动提醒
- 使用 cert-manager（Kubernetes 环境）自动管理证书生命周期，自动续期和替换
