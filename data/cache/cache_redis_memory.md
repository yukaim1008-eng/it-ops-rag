# Redis 内存满 / key 淘汰 / 变慢诊断与处理

## 问题现象

Redis 内存接近 `maxmemory`；写入被拒报 `OOM command not allowed when used memory > maxmemory`，或大量 key 被淘汰导致缓存命中率骤降；应用变慢、偶发超时（缓存没命中全打到数据库）。

## 排查步骤

### 1. 看内存与淘汰情况

```bash
redis-cli INFO memory     # used_memory / maxmemory / mem_fragmentation_ratio
redis-cli INFO stats      # evicted_keys（淘汰数）、keyspace_hits/misses（命中率）
```

### 2. 找大 key 与慢命令

```bash
redis-cli --bigkeys              # 扫描各类型最大的 key
redis-cli SLOWLOG GET 10         # 慢命令（大 key 的 O(n) 操作会拖慢整个实例）
```

## 常见原因

- **大量 key 没设过期时间**，只增不减，内存被填满。
- **bigkey**：单个超大 Hash/List/Set，占内存且操作慢。
- `maxmemory` 设得过小，或 `maxmemory-policy` 不当（如 `noeviction` 直接拒写）。
- 内存碎片率高（`mem_fragmentation_ratio` 远大于 1）。

## 解决方案

### 临时止血

```bash
redis-cli CONFIG SET maxmemory 4gb                  # 临时调大
redis-cli CONFIG SET maxmemory-policy allkeys-lru   # 允许 LRU 淘汰，避免拒写
# 清理已知 bigkey（用 UNLINK 异步删，别用 DEL 阻塞）
```

### 根本修复

- **所有 key 设合理 TTL**，避免无限堆积。
- 拆分 bigkey（分片 / 改结构），杜绝 O(n) 大操作。
- 选对淘汰策略（`allkeys-lru` / `volatile-ttl`），按业务定。
- 数据量大则**分片集群**（Redis Cluster）扩容内存。

## 预防措施

- 监控内存使用率、`evicted_keys`、命中率、碎片率，设告警。
- 写入规范：key 必须带 TTL，禁止无界 bigkey。
- 容量规划：缓存内存与数据规模匹配，预留余量。
