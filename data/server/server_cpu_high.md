# 服务器 CPU 使用率过高诊断与处理

## 问题现象

用户反馈服务响应变慢、请求超时增加，或系统监控显示 CPU 使用率持续超过 80% 甚至达到 100%，系统操作卡顿，SSH 连接可能出现延迟或断开，重启服务后暂时恢复但问题会再次出现。

## 排查步骤

### 1. 确认 CPU 高负载范围（全局观察）

```bash
# 查看系统整体 CPU 使用情况，关注 us（用户态）和 sy（内核态）占比
top

# 或使用更直观的 htop
htop

# 查看 CPU 各核心分布，确认是所有核心都高还是单核打满
mpstat -P ALL 2 5

# 查看系统负载（load average），1分钟/5分钟/15分钟值超过 CPU 核心数表示过载
uptime
```

**判断方向**：us 占比高 → 应用层计算密集型问题；sy 占比高 → 系统调用频繁或内核问题；wa 占比高 → IO 等待，非 CPU 问题但需关注；st 占比高 → 虚拟化环境宿主机争抢。

### 2. 定位高 CPU 消耗的进程

```bash
# top 中按 P 键（大写）按 CPU 使用率排序
top -c

# 一次性获取 Top 5 CPU 消耗进程
ps aux --sort=-%cpu | head -n 6

# 持续监控特定进程的 CPU 变化
pidstat -p <PID> 2 10

# 查看进程下各线程的 CPU 占用（关键步骤）
top -H -p <PID>
# 或使用 ps 查看线程
ps -T -p <PID> -o pid,tid,pcpu,comm
```

### 3. 分析高 CPU 的具体代码路径

#### Java 应用场景（最常用）

```bash
# 步骤1：找到高 CPU 的线程 ID（十进制）
top -H -p <PID>
# 记录高 CPU 的 TID，如 12345

# 步骤2：将 TID 转换为十六进制（用于 jstack 检索）
printf "%x\n" 12345   # 输出如 3039

# 步骤3：打印线程堆栈并定位
jstack <PID> | grep -A 30 3039

# 更高效的方式：多次采样对比
jstack <PID> > /tmp/jstack_1.log
sleep 3
jstack <PID> > /tmp/jstack_2.log
diff /tmp/jstack_1.log /tmp/jstack_2.log
```

#### Python 应用场景

```bash
# 使用 py-spy（推荐，生产环境安全）
py-spy top -p <PID>           # 实时查看热点函数
py-spy dump -p <PID>          # 打印当前调用栈
py-spy record -o profile.svg -p <PID> --duration 30  # 生成火焰图

# 或使用 Python 内置工具（需提前安装 signal 处理）
kill -SIGQUIT <PID>           # 打印所有线程堆栈（取决于应用实现）
```

#### Go 应用场景

```bash
# 开启 pprof 调试接口（需要在代码中导入 net/http/pprof）
# 通过 HTTP 获取 CPU profile
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30

# 进入 pprof 交互界面后使用 top 查看热点
(pprof) top10
(pprof) list 函数名
```

#### 通用 Linux 进程（C/C++/任何原生程序）

```bash
# 使用 perf 采集 CPU 采样
perf top -p <PID>             # 实时查看热点符号
perf record -p <PID> -g -- sleep 30   # 采样30秒
perf report                   # 生成报告，查看调用链

# 使用 strace 检查系统调用是否异常频繁（可能误伤性能）
strace -c -p <PID>            # 统计系统调用次数
# 若看到大量 futex、poll 等，可能是锁竞争或死循环
```

### 4. 容器环境专用排查

```bash
# 查看容器 CPU 使用情况
docker stats --no-stream

# 进入容器内部排查
docker exec -it <容器名> top

# 查看容器 CPU 限制与使用（Cgroup）
cat /sys/fs/cgroup/cpu/cpuacct.usage
cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us

# Kubernetes 环境查看 Pod CPU
kubectl top pod <pod名> -n <命名空间>

# 查看 Node 上各容器 CPU 分布
kubectl top node
```

### 5. 特殊情况：内核态 CPU（sy）过高

```bash
# 查看系统中断分布
cat /proc/interrupts | head -20
watch -n 1 "cat /proc/softirqs | head -10"

# 查看上下文切换频率（过高会消耗 CPU）
vmstat 2 10
# cs 列如果持续超过 10w/s，说明上下文切换异常

# 查看具体是哪个内核模块/驱动消耗
perf top -g                    # 不带进程ID，查看全局
```

## 常见原因

### 原因一：死循环或无限循环
代码中存在 while(true) 没有正确的退出条件，或递归调用没有终止条件。典型特征是 CPU 使用率稳定在 100%（单核），线程堆栈中始终停在某一行循环代码。

### 原因二：频繁的 Full GC（Java 特有）
内存不足导致 JVM 不停执行 Full GC，GC 线程本身消耗大量 CPU。特征是 CPU 周期性飙升到 100%，jstat 显示 FGC 次数快速增加。

### 原因三：锁竞争与线程频繁切换
高并发场景下过度使用 synchronized 或 ReentrantLock，导致线程大量阻塞和唤醒。特征是用 top -H 看到很多线程在 Runnable 状态，perf top 显示 futex 相关调用。

### 原因四：正则表达式灾难性回溯
使用复杂正则表达式匹配长字符串时，发生 catastrophic backtracking。特征是在特定输入下 CPU 瞬间飙高，堆栈停在 Pattern.matcher 相关方法。

### 原因五：日志框架异步队列堆积
日志队列满后，日志写入线程陷入忙等或频繁重试。特征是在高负载下 sy（内核态）占比异常升高。

### 原因六：外部接口超时时间过短
调用下游接口设置了很短的超时（如 10ms），大量请求快速失败后立即重试，形成重试风暴。特征是 CPU 与业务流量不成比例增长。

### 原因七：虚拟机/容器 CPU 超分过度
宿主机 CPU 资源争抢导致频繁的 CPU 调度和上下文切换。特征是用 top 看到 st（steal time）占比超过 10%。

## 解决方案

### 临时止血（恢复服务可用性）

```bash
# 方案1：重启问题进程（最快，但会中断服务）
systemctl restart <服务名>
kill -9 <PID> && 启动脚本

# 方案2：容器环境下直接重建 Pod
kubectl delete pod <pod名> -n <命名空间>

# 方案3：限制问题进程的 CPU 使用（不重启，使用 cgroup）
cgcreate -g cpu:/limit
cgset -r cpu.cfs_quota_us=200000 limit   # 限制为 2 个核心
cgset -r cpu.cfs_period_us=100000 limit
cgclassify -g cpu:limit <PID>

# 方案4：使用 taskset 将进程绑定到特定核心，避免多核争抢
taskset -cp <核心号> <PID>

# 方案5：如果 Java 应用是 Full GC 导致，尝试触发一次 GC（效果有限）
jcmd <PID> GC.run

# 方案6：临时降级/熔断（通过配置中心或网关）
# 关闭非核心功能、开启限流、降低线程池大小
```

### 根本修复（彻底解决）

#### 死循环/无限循环
使用前一步获取的堆栈定位到具体代码行。检查循环条件是否有进展（如缺少 break、递归无终止条件）。添加超时退出机制或请求数上限。修复后增加边界条件测试用例。

#### 频繁 Full GC 导致 CPU 高
用 jmap 导出堆 dump，使用 MAT 分析内存泄漏。调整堆大小（-Xms 和 -Xmx 相等减少动态扩容）。优化代码减少临时对象创建，启用 G1GC 或 ZGC。同时参考内存泄漏文档处理。

#### 锁竞争与线程频繁切换
用 jstack 多次采样，找出频繁 BLOCKED 的线程。缩小锁粒度（使用 ConcurrentHashMap 替代 HashTable）。使用读写锁或乐观锁替代独占锁。无锁化编程（CAS、ThreadLocal）。

#### 正则表达式灾难性回溯
定位到具体的正则表达式和输入字符串。优化正则：使用非贪婪匹配 `.*?` 而非 `.*`，使用原子分组 `(?>...)` 防止回溯。预处理输入，限制长度。改用简单的字符串方法（indexOf、contains）。

#### 日志框架异步队列堆积
降低日志级别（如从 DEBUG 改为 INFO）。调整异步日志队列大小和批量写入策略。升级日志框架版本（如 Log4j2 的 LMAX Disruptor）。

#### 外部接口超时过短导致重试风暴
增加超时时间到合理值（如 500ms-1s）。实现退避重试策略（指数退避 + 抖动）。增加熔断机制，下游异常时快速失败而非重试。

#### 容器 CPU 超分过度
调整 Pod CPU 请求和限制（request 和 limit 尽量相等避免争抢）。使用 CPU 独占绑核（Guaranteed QoS）。升级节点规格或减少节点上 Pod 数量。

## 预防措施

- 配置 CPU 告警阈值：建议 70% 持续 5 分钟触发预警，90% 触发告警
- 接入 APM 工具：使用 SkyWalking、Pinpoint 或 ARMS 持续监控调用链和热点方法
- 建立性能基线：压测确定正常 QPS 对应的 CPU 水位，超过基线 50% 自动触发 profile 采集
- Java 应用启动参数增加异常时自动 dump：

```
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/data/logs
-XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:/data/logs/gc.log
```

- 定期代码审查：使用 SpotBugs 扫描明显性能问题（如循环内创建对象、字符串拼接）。CR 时关注循环、锁使用、正则表达式和递归调用
- 压测回归：每次上线前在预发环境执行流量回放或 JMeter 压测，观察 CPU 曲线是否异常

### 修复验证标准

修复后运行稳定性测试 30 分钟到 1 小时，CPU 使用率应随业务流量波动而非持续爬升。使用 top 观察 us 占比应在正常范围内（通常业务高峰期不超过 70%）。连续运行 24 小时后平均 CPU 水位与刚上线时偏差不超过 20%。触发自动伸缩的频率恢复正常（若之前因 CPU 高频繁扩缩容）。使用火焰图对比修复前后，热点函数应集中在业务逻辑而非系统开销或 GC。
