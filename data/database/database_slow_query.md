# MySQL 慢查询优化指南

## 问题现象

数据库响应变慢，应用日志中出现大量数据库超时错误（如 "Lock wait timeout exceeded" 或 "Query execution was interrupted"）。`SHOW PROCESSLIST` 显示有长时间运行的查询处于 "Sending data" 或 "Creating sort index" 状态。

## 排查步骤

### 1. 开启慢查询日志

```sql
-- 查看当前慢查询配置
SHOW VARIABLES LIKE 'slow_query%';
SHOW VARIABLES LIKE 'long_query_time';

-- 开启慢查询日志
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 2;              -- 超过2秒的查询会被记录
SET GLOBAL slow_query_log_file = '/var/log/mysql/slow.log';

-- 记录未使用索引的查询（开发环境使用，生产需谨慎）
SET GLOBAL log_queries_not_using_indexes = ON;
```

### 2. 使用慢查询分析工具

```bash
# mysqldumpslow 自带工具，按总时间取前10条
mysqldumpslow -s t -t 10 /var/log/mysql/slow.log

# pt-query-digest（Percona Toolkit）更详细的分析
pt-query-digest /var/log/mysql/slow.log > slow_report.txt

# 查看报告中的关键指标：Response time、Lock time、Rows examined
```

### 3. EXPLAIN 分析执行计划

```sql
EXPLAIN SELECT * FROM orders WHERE user_id = 123 AND status = 'pending' ORDER BY created_at DESC;
```

重点关注字段：
- **type**：ALL（全表扫描）最差，应至少达到 range 或 ref 级别
- **key**：实际使用的索引，为 NULL 表示未命中任何索引
- **rows**：预估扫描行数，越小越好，与实际返回行数差距大说明索引选择性差
- **Extra**：出现 Using filesort（额外排序）或 Using temporary（临时表）是性能杀手

### 4. 检查索引使用情况

```sql
-- 查看表的索引信息
SHOW INDEX FROM orders;

-- 找出未使用的索引（MySQL 8.0+）
SELECT * FROM sys.schema_unused_indexes;

-- 找出冗余索引
SELECT * FROM sys.schema_redundant_indexes;
```

## 常见原因

### 原因一：缺少索引或索引失效
WHERE 条件列没有索引，或对索引列使用了函数（如 `WHERE DATE(create_time) = '2024-01-01'`），导致索引失效走全表扫描。

### 原因二：索引选择性差
索引列的值重复度太高（如 status 只有 3 种状态），MySQL 优化器认为全表扫描更快。

### 原因三：SELECT * 导致回表
查询所有列导致即使命中索引也需要回表取数据，IO 开销大。

### 原因四：大 offset 分页
`LIMIT 100000, 20` 需要扫描并丢弃前 100000 行，越往后越慢。

### 原因五：JOIN 缺少索引或驱动表选错
多表 JOIN 时关联列没有索引，或优化器选错了驱动表（小表驱动大表原则）。

### 原因六：锁等待
行锁或表锁竞争导致查询阻塞，通过 `SHOW ENGINE INNODB STATUS` 查看锁信息。

## 解决方案

### 临时止血

```sql
-- 终止长时间运行的查询
SHOW PROCESSLIST;
KILL <id>;

-- 紧急添加索引（会锁表，需评估影响）
ALTER TABLE orders ADD INDEX idx_user_status_time (user_id, status, created_at);
```

### 根本修复 —— 常用优化技巧

**覆盖索引**：让查询的所有列都在索引中，避免回表。
```sql
CREATE INDEX idx_cover ON orders(user_id, status, created_at);
```

**避免 SELECT ***：只查需要的列，减少数据传输和回表开销。

**大 offset 分页优化**：用子查询先定位起始 ID。
```sql
-- 原写法
SELECT * FROM t ORDER BY id LIMIT 100000, 20;
-- 优化后
SELECT * FROM t WHERE id > (SELECT id FROM t ORDER BY id LIMIT 100000, 1) LIMIT 20;
```

**避免索引列使用函数**：
```sql
-- 错误写法
WHERE DATE(create_time) = '2024-01-01'
-- 正确写法
WHERE create_time >= '2024-01-01' AND create_time < '2024-01-02'
```

**JOIN 优化**：确保 JOIN 列有索引，小表作为驱动表。

## 预防措施

- 配置慢查询监控告警：慢查询数量 > 10/min 触发告警
- 定期执行 `ANALYZE TABLE` 更新索引统计信息，帮助优化器做出正确的执行计划
- 上线前进行 SQL 审核：使用 Inception 或 Yearning 等工具对所有 SQL 变更进行审核
- 建立 SQL 性能基线：压测记录各接口的数据库查询耗时，上线后对比偏离度
- 定期清理无用索引和冗余索引，减少写入时的索引维护开销
