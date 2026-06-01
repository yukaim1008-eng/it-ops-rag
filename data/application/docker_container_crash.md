# Docker 容器异常退出排查

## 问题现象

Docker 容器频繁重启或异常退出，`docker ps -a` 显示容器状态为 "Exited"，退出码为非零值。`docker logs` 中可能没有足够的信息说明退出原因，或者日志直接截断。

## 排查步骤

### 1. 查看容器状态与退出码

```bash
# 查看所有容器（包括已退出）
docker ps -a

# 查看特定容器的详细信息和退出码
docker inspect <容器名> | grep -A 5 "State"

# 退出码含义速查
# Exit 0  —— 正常退出（容器内主进程结束）
# Exit 1  —— 应用错误
# Exit 137 —— 被 SIGKILL 杀死（最常见是 OOM）
# Exit 139 —— 段错误（SIGSEGV）
# Exit 143 —— 收到 SIGTERM 信号（正常终止）
```

### 2. 查看容器日志

```bash
# 查看最后100行日志
docker logs --tail 100 <容器名>

# 查看带时间戳的日志（排查时间线）
docker logs --timestamps <容器名>

# 查看退出前的日志
docker logs --tail 200 <容器名> 2>&1 | tail -50
```

### 3. 检查是否 OOM（内存不足被 kill）

```bash
# 系统日志中搜索 OOM 记录
dmesg | grep -i "out of memory"
grep -i "oom" /var/log/syslog
journalctl -k | grep -i oom

# 查看 Docker 的 OOM 事件
docker inspect <容器名> | grep -i oom

# 查看容器内存使用趋势
docker stats --no-stream <容器名>
```

### 4. 检查容器资源限制

```bash
# 查看容器的资源限制配置
docker inspect <容器名> | grep -E "Memory|NanoCpus"

# 查看 cgroup 的限制
cat /sys/fs/cgroup/memory/docker/<container_id>/memory.limit_in_bytes
cat /sys/fs/cgroup/memory/docker/<container_id>/memory.usage_in_bytes
```

### 5. 进入容器内部排查（如果还能短暂运行）

```bash
# 交互式进入容器
docker exec -it <容器名> /bin/sh

# 检查应用日志
cat /var/log/app/*.log
ls -la /tmp/core.*      # 是否有 core dump 文件存在

# 检查磁盘是否写满（会导致无法写日志）
df -h
```

### 6. Kubernetes 环境专用

```bash
# 查看 Pod 事件（包含 OOMKilled 原因）
kubectl describe pod <pod名> -n <命名空间>

# 查看 Pod 重启前的日志
kubectl logs <pod名> -n <命名空间> --previous

# 查看 Node 资源使用
kubectl top node
kubectl top pod -n <命名空间>
```

## 常见原因

### 原因一：OOM（内存不足）
容器内存使用超过限制，被内核 OOM Killer 杀死。退出码为 137（128+9，SIGKILL）。Kubernetes 中显示 "OOMKilled"。

### 原因二：应用内部错误（代码 Bug）
未捕获的异常导致进程退出。退出码通常为 1。常见的包括：配置文件解析失败、数据库连接失败后未重试、空指针异常。

### 原因三：健康检查失败
Kubernetes 的 liveness probe 或 Docker 的 healthcheck 连续失败，容器被自动重启。退出码正常（0 或 137），但反复重启。

### 原因四：磁盘空间不足
容器内或宿主机磁盘写满，应用无法写入日志或临时文件导致崩溃。

### 原因五：信号处理不当
应用没有正确处理 SIGTERM 信号，Docker stop 发送 SIGTERM 后等待超时（默认10秒），然后发送 SIGKILL 强制终止。退出码为 137。

### 原因六：共享内存不足
容器默认 `/dev/shm` 为 64MB，某些应用（如 Oracle、PostgreSQL）需要更大的共享内存。

## 解决方案

### 临时止血

```bash
# 重启容器
docker restart <容器名>

# 重建容器
docker-compose down && docker-compose up -d

# Kubernetes 中重建 Pod
kubectl delete pod <pod名> -n <命名空间>

# 如果是内存不足，立即增加内存限制
docker update --memory 2g --memory-swap 2g <容器名>
```

### 根本修复

- **OOM**：调大容器内存限制（`--memory`），或优化应用内存使用，或增加 JVM 参数 `-Xmx`。同时配置 `-XX:+ExitOnOutOfMemoryError` 让应用优雅退出
- **应用内部错误**：完善启动时的配置校验和依赖检查，增加全局异常捕获和健康检查端点
- **健康检查失败**：调大 `initialDelaySeconds` 和 `periodSeconds`，给应用足够的启动时间
- **磁盘不足**：配置日志轮转（logrotate），设置容器日志大小上限（`--log-opt max-size=10m`）
- **信号处理**：应用监听 SIGTERM 信号，在收到信号后优雅关闭（完成当前请求、关闭连接、清理资源）
- **共享内存不足**：`docker run --shm-size 256m` 或 Kubernetes 中挂载 `emptyDir: medium: Memory`

## 预防措施

- 配置 `--restart=unless-stopped` 或 `restartPolicy: Always` 确保容器异常退出后自动重启
- Kubernetes 中配置 liveness probe 和 readiness probe，并设置合适的 `failureThreshold`
- 配置容器资源限制（requests 和 limits）并使用 LimitRange 确保所有 Pod 都有资源限制
- 接入日志收集（如 ELK、Loki），确保容器退出后的日志仍然可查
- 监控容器重启次数：超过阈值（如 5次/小时）触发告警
