# 服务器内存泄漏诊断与处理

## 问题现象

用户发现服务器响应变慢或频繁宕机，重启服务或服务器后恢复正常，但运行一段时间后问题复现；监控系统显示内存使用率持续爬升（如从20%逐渐涨到95%+），即使业务量没有明显增长，内存也不会自动回落，最终触发OOM Killer导致进程被杀或系统无响应。

## 排查步骤

### 1. 确认内存泄漏存在（快速定性）

```bash
# 观察内存变化趋势，每2秒刷新一次
watch -n 2 free -h

# 重点关注 available 列是否持续下降
# 若 available 从 8G 逐渐降至 100M 且 cache/buffer 无显著增长，高度怀疑泄漏
```

### 2. 定位泄漏进程

```bash
# 找出内存占用最高的 Top 10 进程，观察 RES（物理内存）和 %MEM
ps aux --sort=-%mem | head -n 10

# 持续监控特定进程的内存变化（多次执行对比）
watch -n 10 "ps aux | grep <进程名> | grep -v grep"

# 更精细的监控：每隔30秒记录一次进程内存
while true; do ps -p <PID> -o pid,rss,vsz,cmd --no-headers >> mem.log; sleep 30; done
```

### 3. 判断泄漏类型

```bash
# 查看进程内存分布
pmap -x <PID> | tail -20

# 若 heap 区域异常巨大 → 堆内存泄漏
# 若有很多 64K 或 2M 的匿名内存块 → 可能堆外/原生内存泄漏

# 检查系统内核内存（若用户进程占用不高但系统内存耗尽）
slabtop -o  # 观察 dentry、inode 等是否异常增长
```

### 4. 深度分析（以 Java 应用为例）

```bash
# 生成堆转储文件（会触发Full GC，谨慎在生产高峰操作）
jmap -dump:live,format=b,file=/tmp/heap_$(date +%Y%m%d_%H%M%S).hprof <PID>

# 实时查看GC情况，若FGC后Old区仍持续增长
jstat -gcutil <PID> 1000

# 开启Native Memory Tracking（需要重启JVM）
-XX:NativeMemoryTracking=detail
# 运行时查看
jcmd <PID> VM.native_memory summary diff
```

### 5. 容器环境专用排查

```bash
# 查看容器内存实时状态
docker stats --no-stream

# 进入容器查看进程内存占用
docker exec -it <容器名> top

# 查看cgroup内存限制与使用量
cat /sys/fs/cgroup/memory/memory.stat
```

## 常见原因

| 原因分类 | 典型场景 | 特征表现 |
|---------|---------|---------|
| 1. 代码逻辑缺陷 | 集合对象（List/Map）只增不减、监听器未注销、缓存无过期策略 | 堆内存持续增长，GC无法回收 |
| 2. 资源未正确关闭 | 数据库连接、文件流、HTTP连接忘记close；JDBC的ResultSet未关闭 | 通常是堆外内存泄漏，进程内存 > Xmx配置 |
| 3. 第三方库/驱动问题 | JDBC驱动Bug、Netty的DirectByteBuffer未释放、日志框架异步缓冲区溢出 | 原生内存（Native Memory）不断增长 |
| 4. 中间件/容器配置不当 | ThreadLocal未remove、线程池无限增长、JVM元空间（Metaspace）泄漏 | 特定场景触发，低流量下内存也会涨 |

## 解决方案

### 临时止血（恢复服务可用性）

```bash
# 方案1：重启进程（最快但会中断服务）
systemctl restart <服务名>   # systemd服务
kill -9 <PID> && 启动脚本     # 普通进程

# 方案2：触发主动GC（仅对Java堆内存有效，释放效果有限）
jcmd <PID> GC.run

# 方案3：容器环境下直接重建Pod
kubectl delete pod <pod名> -n <命名空间>

# 方案4：写入内存限制并配置OOM优先级（防止系统宕机）
echo -1000 > /proc/<PID>/oom_score_adj   # 保护关键进程不被杀
```

### 根本修复（彻底解决）

| 泄漏类型 | 修复措施 |
|---------|---------|
| Java堆内存泄漏 | ① 用MAT分析heap.hprof，定位到具体类 → ② 检查是否集合无清理 → ③ 修复代码（如：使用WeakHashMap、手动remove、引入缓存过期）→ ④ 增加压测验证 |
| 资源未关闭 | ① 检查代码中的try-with-resources → ② 数据库连接池配置验证连接有效性 → ③ 修复后使用 lsof -p <PID> 对比打开文件描述符数量 |
| 堆外内存泄漏 | ① 检查Netty、NIO代码是否显式调用cleaner().clean() → ② 升级有问题的JDBC驱动 → ③ 启用NMT定位具体分配点 |
| ThreadLocal泄漏 | ① 在线程池场景中确保每次请求后调用remove() → ② 代码审查排查未清理的ThreadLocal → ③ 使用阿里Arthas监控ThreadLocal膨胀 |

## 预防措施

- 配置内存告警阈值（建议85%触发预警，95%触发告警）
- 接入监控大盘（Prometheus + Grafana），观察内存趋势曲线
- 建立内存基线：压测确定正常内存水位，超过基线30%自动触发dump
- 代码规范：强制静态代码扫描（SpotBugs、SonarQube）检测资源关闭
- Java应用启动参数增加：

```
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/data/logs
-XX:NativeMemoryTracking=summary
```

> **修复验证标准**：修复后运行稳定性测试24小时，内存曲线应呈现"锯齿状"（GC后回到底线）而非"爬坡状"；连续48小时内存水位波动不超过20%即为正常。
