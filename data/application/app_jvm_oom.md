# Java 应用内存溢出（OOM / 频繁 Full GC）诊断与处理

## 问题现象

应用抛 `java.lang.OutOfMemoryError: Java heap space`（或 `Metaspace`、`GC overhead limit exceeded`）；响应变慢、周期性卡顿（频繁 Full GC）；严重时进程被系统 OOM Killer 杀掉。

**关联**：与"服务器内存泄漏""Docker 容器 OOM 退出"现象相近，但这里聚焦 JVM 堆内分析。

## 排查步骤

### 1. 看 GC 与堆状况

```bash
jstat -gc <PID> 1000 10     # 看 FGC（Full GC 次数）是否快速增长、FGCT 耗时
jmap -histo:live <PID> | head -30   # 存活对象 Top（哪类对象占内存最多）
```

### 2. 导出堆 dump 深挖

```bash
jmap -dump:live,format=b,file=/tmp/heap.hprof <PID>
# 用 MAT / VisualVM 打开，看 Dominator Tree、找泄漏嫌疑（Leak Suspects）
```

### 3. 看 GC 日志

启动加 `-Xlog:gc*:file=/data/logs/gc.log`，分析 Full GC 频率与回收效果（回收后老年代仍居高 → 泄漏）。

## 常见原因

- **内存泄漏**：静态集合 / 缓存只增不减、`ThreadLocal` 未清理、监听器未注销。
- **堆设置过小**：`-Xmx` 不够支撑业务峰值。
- **一次性加载大对象**：大结果集、大文件全量读入内存。
- **Metaspace 溢出**：动态生成类过多（如反射 / 字节码增强）。
- 连接 / 线程泄漏间接撑爆内存。

## 解决方案

### 临时止血

```bash
jcmd <PID> GC.run            # 触发一次 GC（效果有限）
systemctl restart <服务>     # 重启恢复，先保可用性
```

### 根本修复

- 用 **MAT 分析 dump** 定位泄漏对象与引用链，修代码（及时清理集合 / 缓存设上限与过期）。
- 合理设置 `-Xms = -Xmx`，按压测确定堆大小；启用 G1/ZGC。
- 大数据量改为**流式 / 分页处理**，不要全量入内存。

## 预防措施

- 启动参数加 `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/data/logs`，OOM 时自动留证。
- 监控堆使用率、Full GC 频率与耗时，设告警。
- 上线前压测观察内存曲线是否随时间持续爬升（泄漏特征）。
