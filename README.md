# SilkReel-01 · 江口缫丝坞

缫丝盆环状作业台。登录后看到的是沿汤池围成一圈的盆位，点盆登记汤温并改状态——不是侧栏双列表 CRUD。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Web API | Quart（异步 Flask 族）· Hypercorn |
| 结构 | `repositories.py` 仓储 + `services.py` 门槛，路由不直接拼 SQL |
| 数据 | SQLAlchemy 2 async · asyncpg · PostgreSQL 15 |
| 前端 | Preact 10 · Vite |
| 部署 | Docker Compose |

## 路径与端口

- 前端：http://localhost:4760
- API：http://localhost:8760
- PostgreSQL：localhost:6160

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 管理员 |
| `admin2` | `123456` | 管理员（用于演示两位主管并发保存勾选） |
| `worker` | `123456` | 缫丝工 |

## 业务规则

盆状态不可标成「已缫完」，除非该盆**最近一条**汤温记录落在 **38～42℃**。规则在 `backend/app/services.py`。

管理员在顶栏「采样人过滤」页勾选要看的操作人并保存（全局唯一版本，带乐观锁；两位主管并发提交时旧版本得到 409，库里只留一版）。环盆底下的汤温温谱与温谱台账同跟这一批勾选，共用同一条过滤查询；一个都不勾时两边都是空表，不造任何行。勾选只影响展示，不会改动已记下的温度数字。

## 快速启动

```bash
cd SilkReel/SilkReel-01
docker compose up --build
```
