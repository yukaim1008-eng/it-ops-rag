# 服务器磁盘空间 / inode 耗尽诊断与处理

## 问题现象

应用写入失败、日志报 `No space left on device`；服务无法启动或频繁报错；数据库无法写入、上传功能异常；有时 `df -h` 显示磁盘还有空间却仍报满（inode 耗尽）。监控显示某挂载点使用率接近或达到 100%。

## 排查步骤

### 1. 查看磁盘与 inode 使用

```bash
df -h            # 各挂载点空间使用率，关注 Use% 接近 100% 的分区
df -i            # inode 使用率（大量小文件时空间没满但 inode 先满）
```

### 2. 定位大文件 / 大目录

```bash
# 逐层下钻找最占空间的目录
du -h --max-depth=1 / | sort -rh | head -10
du -sh /var/log/* | sort -rh | head -10
# 找出大于 500M 的文件
find / -type f -size +500M -exec ls -lh {} \; 2>/dev/null
```

### 3. 排查"已删除但未释放"的文件

```bash
# 进程仍持有已删除文件的句柄，空间不会释放（常见于日志被 rm 但进程没重启）
lsof | grep deleted | sort -k7 -rh | head
```

### 4. inode 耗尽时找小文件聚集的目录

```bash
for d in /*; do echo "$(find $d -xdev 2>/dev/null | wc -l) $d"; done | sort -rn | head
```

## 常见原因

- **日志疯长**：应用日志 / Nginx access log 未轮转，单文件几十 G。
- **临时文件堆积**：`/tmp`、上传缓存、session 文件未清理。
- **大量小文件 → inode 耗尽**：缓存碎片、邮件队列、海量 session（空间没满也报满）。
- **已删除文件未释放**：`rm` 了日志但进程仍持有句柄。
- **数据库 binlog / 慢查询日志膨胀**。

## 解决方案

### 临时止血

```bash
truncate -s 0 /var/log/huge.log     # 清空大日志但不删文件（避免句柄问题）
journalctl --vacuum-size=200M       # 压缩 systemd 日志
systemctl restart <服务>            # 已删除未释放：重启持有句柄的进程
```

### 根本修复

- 配置 **logrotate**：按大小 / 时间切割 + 保留份数 + 压缩。
- 清理策略：定时清理 `/tmp`、过期缓存、旧 binlog（`expire_logs_days`）。
- inode 问题：合并小文件 / 调整缓存策略 / 重建文件系统时增大 inode 数。
- 关键服务日志单独分区，避免撑爆根分区。

## 预防措施

- **磁盘与 inode 双指标监控**（很多人只看 `df -h` 漏看 `df -i`），超 80% 预警。
- 所有日志接入 logrotate。
- 容量规划：按数据增长预估，预留 20% 以上余量。
