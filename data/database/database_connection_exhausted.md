# 数据库连接耗尽 / 连接池打满诊断与处理

## 问题现象

应用报 `Too many connections`、`Connection pool exhausted`、获取连接超时；服务"连不上数据库"但 DB 进程在跑；高峰期尤其频繁。

## 排查步骤

### 1. 看数据库侧连接数

```sql
SHOW STATUS LIKE 'Threads_connected';    -- 当前连接数
SHOW VARIABLES LIKE 'max_connections';   -- 上限
SHOW PROCESSLIST;                         -- 谁占着连接、是否大量 Sleep（泄漏迹象）
```

### 2. 看应用侧连接池

- 连接池最大值（HikariCP `maximumPoolSize` 等）是否远小于并发需求。
- 是否有连接**借出不归还**（连接泄漏）：活跃连接只增不减。
- 慢查询是否长时间占用连接（参考慢查询文档）。

## 常见原因

- **连接泄漏**：代码异常路径没关连接 / 没用 try-with-resources，连接只借不还。
- **连接池过小**或 **max_connections 设太低**，扛不住并发。
- **慢查询占用连接过久**，连接周转不过来。
- 突发流量 / 下游变慢导致连接堆积。
- 短连接风暴：频繁建连不复用。

## 解决方案

### 临时止血

```sql
-- 找出大量 Sleep 的连接并清理
SELECT id FROM information_schema.processlist WHERE command='Sleep' AND time>600;
KILL <id>;
SET GLOBAL max_connections = 500;   -- 临时调大（治标）
```

### 根本修复

- **修连接泄漏**：确保所有路径释放连接（try-with-resources / finally）。
- 合理配置连接池大小 + **连接超时回收**（idleTimeout / maxLifetime）。
- 优化慢查询，缩短连接占用时间。
- 读写分离 / 加缓存，降低对主库连接的压力。

## 预防措施

- 监控 `Threads_connected` 与连接池活跃数，接近上限告警。
- 连接池统一封装，禁止裸用连接。
- 压测验证连接池在峰值流量下不被打满。
