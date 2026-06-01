# Nginx 502 Bad Gateway 错误排查

## 问题现象

用户访问网站时浏览器返回 "502 Bad Gateway" 错误页面。Nginx 作为反向代理，无法从上游服务器（如 PHP-FPM、Gunicorn、uWSGI、Node.js）获取有效响应。

## 排查步骤

### 1. 查看 Nginx 错误日志

```bash
tail -f /var/log/nginx/error.log
```

常见错误信息及对应方向：
- `connect() failed (111: Connection refused)` —— 上游服务未启动或端口错误
- `upstream timed out (110: Connection timed out)` —— 上游响应超时
- `recv() failed (104: Connection reset by peer)` —— 上游在处理请求时崩溃或主动断开

### 2. 检查上游服务状态

```bash
# PHP-FPM
systemctl status php-fpm
ps aux | grep php-fpm
# 检查 socket 文件
ls -la /var/run/php-fpm.sock

# Gunicorn（Python）
systemctl status gunicorn
ps aux | grep gunicorn

# Node.js
systemctl status node-app
pm2 status
```

### 3. 检查端口与监听

```bash
# 确认上游端口在监听
netstat -tlnp | grep <upstream_port>
ss -tlnp | grep <upstream_port>

# 查看 Nginx 配置中代理指向
grep -E "proxy_pass|fastcgi_pass|uwsgi_pass" /etc/nginx/conf.d/*.conf
```

### 4. 直接测试上游服务

```bash
# 如果上游是 HTTP 服务（如 Gunicorn、Node.js）
curl -v http://127.0.0.1:<upstream_port>/health

# 如果上游是 FastCGI（PHP-FPM），用 cgi-fcgi 测试
echo "<?php echo 'ok'; ?>" | cgi-fcgi -bind -connect /var/run/php-fpm.sock
```

### 5. 检查资源使用

```bash
# 查看上游进程数是否达到上限
systemctl status php-fpm | grep "active processes"

# 检查系统文件描述符限制（上游连接数可能超过限制）
ulimit -n
cat /proc/<nginx_pid>/limits | grep "open files"
```

## 常见原因

### 原因一：上游服务未启动
最常见的原因。PHP-FPM、Gunicorn 等服务因配置错误、重启失败等原因没有运行。

### 原因二：上游服务端口或 Socket 配置不匹配
Nginx 配置中的 `fastcgi_pass` 或 `proxy_pass` 指向的端口与实际监听的不一致，或 socket 文件路径错误、权限不对。

### 原因三：上游连接池耗尽
所有 worker 进程都在处理慢请求，新请求排队等待超过阈值。php-fpm 的 `pm.max_children` 或 gunicorn 的 `--workers` 设置过小。

### 原因四：超时配置不合理
`proxy_read_timeout` 或 `fastcgi_read_timeout` 设置过短，上游处理大请求或慢查询时未完成就被 Nginx 断开。

### 原因五：上游服务 crash
上游进程因内存溢出、段错误等原因崩溃，Nginx 尝试连接时收到 Connection refused。

### 原因六：文件描述符耗尽
Nginx 或上游服务的文件描述符达到系统限制（ulimit -n），无法接受新连接。

## 解决方案

### 临时止血

```bash
# 重启上游服务
systemctl restart php-fpm
systemctl restart gunicorn

# 如果端口冲突，临时更换端口并更新 Nginx 配置
nginx -s reload
```

### 根本修复

- **增加上游进程数**：PHP-FPM 调整 `pm.max_children`（动态模式还需调整 `pm.start_servers`、`pm.min/max_spare_servers`）
- **调整超时参数**：在 Nginx 的 location 块中增加 `proxy_read_timeout 300s` 和 `fastcgi_read_timeout 300s`
- **增加系统限制**：`ulimit -n 65535` 或修改 `/etc/security/limits.conf` 提高文件描述符上限
- **配置健康检查**：Nginx Plus 支持 `health_check` 指令，开源版可用 `ngx_http_healthcheck_module` 或 upstream 的 `max_fails` + `fail_timeout`
- **上游优雅重启**：避免 kill -9，使用 `systemctl reload` 或发送 SIGTERM 让进程处理完当前请求再退出

## 预防措施

- 监控 Nginx 错误日志中 502 数量：`grep "502" /var/log/nginx/access.log | wc -l` 超过阈值告警
- 配置 Nginx upstream 的 `backup` 服务器：主 upstream 故障时自动切换到备用
- 使用 supervisor 或 systemd 的 `Restart=always` 确保上游服务挂掉后自动拉起
- 在上游服务前加健康检查端点（如 `/health`），由负载均衡器定期探测
