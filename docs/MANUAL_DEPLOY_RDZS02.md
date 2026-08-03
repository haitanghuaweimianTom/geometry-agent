# rdzs02 Lean 4 验证服务部署手册

> 竞赛模式 (`grade="competition"`) 需要远端 Lean HTTP 服务。服务不在本机,部署在局域网设备 rdzs02 (HP ProDesk 400 G5, i5-8500, 8GB RAM)。

## 当前状态 (2026-08-03)

**服务已部署并运行中** — `http://10.42.0.124:9407` 响应正常,开机自启通过 crontab @reboot 配置。

- Lean 版本: v4.32.2 (手动解压到 `~/lean/lean-4.32.2-linux/`)
- Python 依赖: fastapi 0.115.0 + uvicorn 0.30.6 + pydantic 2.9.2 (pip --user 离线 whl 安装到 `~/.local/`)
- 启动脚本: `~/lean-svc/start.sh`
- 日志: `~/lean-svc/uvicorn.log`
- 代码: `~/lean-svc/lean_service.py`

快速验证:
```bash
curl -s http://10.42.0.124:9407/health
# {"status":"ok"}
curl -s -X POST http://10.42.0.124:9407/verify -H 'Content-Type: application/json' -d '{"conclusion":"1+1=2"}'
# {"verified":true,...}
```

## 网络信息
- 热点 IP: `10.42.0.124`
- Tailscale IP: `100.74.221.60`
- 用户: `rdzs02`
- SSH 密码: `rdzs1234` (注意是**4 位**数字结尾,不是 3 位)
- 服务端口: `9407`

## 一键部署脚本

在 geometry_agent 主机上运行:

```bash
cd /path/to/geometry_agent

# 方式一:热点网络
python scripts/deploy_lean_service.py --host rdzs02@10.42.0.124 --pass rdzs1234

# 方式二:Tailscale 网络 (跨网络可用)
python scripts/deploy_lean_service.py --host rdzs02@100.74.221.60 --pass rdzs1234

# 方式三:绕过 Docker,直接在宿主机上装 Lean+FastAPI 裸跑
python scripts/deploy_lean_service.py --host rdzs02@10.42.0.124 --pass rdzs1234 --no-docker
```

脚本会:
1. SSH 到 rdzs02 检查环境
2. 安装 Docker / elan+pip (根据选择)
3. 复制 `scripts/lean_service.py` 和 `scripts/Dockerfile.lean` 到 `~/lean-svc/`
4. 构建并启动服务 (Docker 容器或 nohup uvicorn)
5. 等待 `/health` 就绪,POST 一个 `1+1=2` 冒烟测试

## 已知部署坑

### 1. Snap curl 问题
rdzs02 上默认 `/snap/bin/curl` 是 snap 沙盒版本,访问隐藏目录/外网会失败。
解决:`sudo apt install curl` 装原生 curl,或用 `wget`。

### 2. apt 源代理问题
rdzs02 的 apt 可能设置了代理 `http://10.42.0.1:7890`,当本机热点的代理没开时,apt 报 502/签名错。
解决:临时取消代理 `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy`,再执行 apt。或确保本机代理 7890 端口正常。

### 3. sudo 密码
`docker` 命令需要 sudo。脚本使用 `echo "rdzs1234" | sudo -S ...` 自动传密码,但首次运行需要 rdzs02 在 sudo 组。
检查: `groups rdzs02`;若不在 docker 组: `sudo usermod -aG docker rdzs02` 后重新登录。

### 4. Lean 工具链安装时间
`elan toolchain install stable` 首次下载 Lean 约 300-500MB,视网速可能需要 5-15 分钟。

## 手动部署 (脚本失败时使用)

```bash
# 1. SSH 到 rdzs02
sshpass -p rdzs1234 ssh -o StrictHostKeyChecking=no rdzs02@10.42.0.124

# 2. 装原生 curl + pip3 (如缺失)
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
echo "rdzs1234" | sudo -S apt-get update
echo "rdzs1234" | sudo -S apt-get install -y curl python3-pip python3-venv

# 3. 装 elan (Lean 版本管理器)
curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y --default-toolchain stable
source ~/.bashrc
export PATH="$HOME/.elan/bin:$PATH"
lean --version   # 应显示 Lean 4.x

# 4. 装 Python 依赖
pip3 install --user --break-system-packages fastapi uvicorn pydantic

# 5. 创建服务目录,复制 lean_service.py
mkdir -p ~/lean-svc
# 在 geometry_agent 主机上 scp:
# sshpass -p rdzs1234 scp -o StrictHostKeyChecking=no scripts/lean_service.py rdzs02@10.42.0.124:~/lean-svc/

# 6. 启动服务
cd ~/lean-svc
pkill -f "uvicorn.*9407" || true
nohup ~/.local/bin/uvicorn lean_service:app --host 0.0.0.0 --port 9407 > ~/lean-svc/uvicorn.log 2>&1 &
sleep 5
curl http://127.0.0.1:9407/health
# 期望: {"status":"ok"}

# 7. 冒烟测试
curl -s -X POST http://127.0.0.1:9407/verify \
  -H 'Content-Type: application/json' \
  -d '{"conclusion":"1+1=2"}'
# 期望: {"verified":true,"output":"...","elapsed_ms":...}
```

## 配置 geometry_agent 调用

部署完成后,在 `configs/default.yaml` 里设置:

```yaml
verification:
  enabled: true
  max_retries: 3
  symbolic_timeout_ms: 200
  lean_endpoint: "http://10.42.0.124:9407"   # 热点
  # lean_endpoint: "http://100.74.221.60:9407"   # Tailscale
  lean_timeout_s: 10
  llm_judge_enabled: true
```

竞赛模式将自动把每步 claim_step 发到该端点做 Lean 编译验证。若服务不可达,系统会降级为 UNCERTAIN → LLM judge 兜底,不阻断整题求解。

## 服务管理

```bash
# 查看日志
ssh rdzs02@10.42.0.124 'tail -30 ~/lean-svc/uvicorn.log'

# 重启
ssh rdzs02@10.42.0.124 'pkill -f "uvicorn.*9407"; cd ~/lean-svc && nohup ~/.local/bin/uvicorn lean_service:app --host 0.0.0.0 --port 9407 > ~/lean-svc/uvicorn.log 2>&1 &'

# 停止
ssh rdzs02@10.42.0.124 'pkill -f "uvicorn.*9407"'
```

## 未来扩展 (mathlib)

当前 Lean 服务没装 mathlib,仅支持内置战术(`simp`, `decide`, `ring_nf`, `norm_num`, `linarith`)。要支持更复杂的竞赛证明,需:

1. 在 rdzs02 上用 `lake init` 创建项目并添加 mathlib 依赖(约 1-3GB 磁盘,首次 build 约 30-60 分钟)
2. 在 `lean_service.py` 里把 src 写入该项目目录,用 `lake env lean` 替代裸 `lean`
3. Docker 方案:用 `ghcr.io/leanprover-community/mathlib4:latest` 作为基础镜像

mathlib 镜像巨大(>5GB),对 rdzs02 的 8GB RAM 有压力,建议仅当实际需要时再安装。