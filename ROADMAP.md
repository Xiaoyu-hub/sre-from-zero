# SRE 端到端学习项目 — 计划与交付物

> 目标：1-2 周（10 个工作日 × 8h）从零搭建一个完整的 SRE 实践闭环，作为零经验候选人唯一的 SRE 凭据。
> 定位：个人学习项目，诚实展示学习路径。

---

## 一、十日计划

### Day 1 — Docker 入门（√）
- 任务：学 Docker 基础，写 Dockerfile 跑通 hello world
- 产出：本地能运行 `docker run` 一个简单的 Python 镜像
- 关键命令：
  - `docker pull python:3.11-slim`
  - `docker run -it --rm python:3.11-slim python -c "print('hello')"`
- 自检：能否在 30 分钟内把一个 FastAPI hello world 容器化跑起来

### Day 2 — k3d/kubectl 入门（√）
- 任务：本地起 k3d 集群，部署一个 nginx 验证能跑
- 产出：本地 K8s 集群，kubectl get pods 能看到 nginx
- 关键命令：
  - `curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash`
  - `k3d cluster create sre-demo`
  - `kubectl create deployment nginx --image=nginx`
  - `kubectl expose deployment nginx --port=80 --type=NodePort`
- 自检：能用 `curl <node-ip>:<port>` 访问到 nginx

### Day 3 — FastAPI 短链服务
- 任务：用 FastAPI 实现 URL 短链核心逻辑
  - `POST /shorten`：传入长 URL，生成短码，存到内存 dict 或 Redis
  - `GET /{short_code}`：301/302 跳转到原 URL
  - `GET /stats/{short_code}`：返回点击次数
- 产出：可运行的本地服务（`uvicorn main:app --reload`）
- 关键点：
  - 短码生成：`base62(uuid4()[:8])` 或 hash(long_url)[:6]
  - 用 in-memory dict 起步，后续可换 Redis
  - 健康检查端点：`GET /healthz`

### Day 4 — 加 metrics 中间件 + Docker 多阶段构建
- 任务：接入 prometheus-client，Dockerfile 多阶段构建
- 产出：服务有 `/metrics` 端点，镜像 < 200MB
- 关键指标：
  - `http_requests_total{method, path, status}` — 请求总数
  - `http_request_duration_seconds_bucket{...}` — 延迟直方图
  - `http_requests_in_progress` — 在途请求
  - `shortener_clicks_total` — 业务指标
- Dockerfile 模板：
  ```dockerfile
  FROM python:3.11-slim AS builder
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --user --no-cache-dir -r requirements.txt

  FROM python:3.11-slim
  WORKDIR /app
  COPY --from=builder /root/.local /root/.local
  COPY . .
  ENV PATH=/root/.local/bin:$PATH
  EXPOSE 8000
  CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```

### Day 5 — K8s 部署清单 + kustomize
- 任务：写 Deployment/Service/HPA + kustomize dev/prod 两套环境
- 产出：`k8s/` 目录结构清晰
- 目录建议：
  ```
  k8s/
  ├── base/
  │   ├── deployment.yaml
  │   ├── service.yaml
  │   ├── hpa.yaml
  │   ├── servicemonitor.yaml
  │   └── kustomization.yaml
  └── overlays/
      ├── dev/kustomization.yaml
      └── prod/kustomization.yaml
  ```
- 关键配置：
  - `resources.requests/limits`：CPU 100m/500m，内存 128Mi/512Mi
  - `livenessProbe/readinessProbe`：指向 `/healthz`
  - HPA：CPU 70% 触发，最小 2 副本
  - ServiceMonitor：让 Prometheus 自动抓取

### Day 6 — 部署 kube-prometheus-stack
- 任务：用 Helm 装 Prometheus + Grafana，配置 ServiceMonitor 抓取短链服务
- 产出：Grafana 能看到短链服务的 metrics
- 关键命令：
  ```bash
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
  helm repo update
  kubectl create namespace monitoring
  helm install kps prometheus-community/kube-prometheus-stack \
    -n monitoring \
    --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false
  ```
- 端口转发（开发用）：
  ```bash
  kubectl port-forward -n monitoring svc/kps-grafana 3000:80
  # 默认账号 admin / prom-operator
  ```

### Day 7 — SLO 面板 + 告警规则
- 任务：Grafana 配 SLO 仪表盘，写告警规则
- 产出：可视化 SLO + 告警触发链路
- 核心 SLO：
  - **可用性 SLO**：99.9%（月度允许 downtime ≈ 43 分钟）
    - SLI：`sum(rate(http_requests_total{status!~"5.."}[5m])) / sum(rate(http_requests_total[5m]))`
  - **延迟 SLO**：P99 < 200ms
    - SLI：`histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))`
- 告警规则示例（PrometheusRule）：
  ```yaml
  apiVersion: monitoring.coreos.com/v1
  kind: PrometheusRule
  metadata:
    name: shortener-slo
  spec:
    groups:
    - name: shortener
      rules:
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{job="shortener",status=~"5.."}[5m]))
          / sum(rate(http_requests_total{job="shortener"}[5m])) > 0.01
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "短链服务错误率超过 1%"
      - alert: HighP99Latency
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket{job="shortener"}[5m])) by (le)
          ) > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "短链服务 P99 延迟 > 200ms"
  ```

### Day 8 — 故障演练
- 任务：制造 1-2 种故障，验证告警能触发、面板能显示
- 产出：演练截图 + 视频
- 推荐故障场景：
  - **场景 A（Pod 异常）**：
    ```bash
    kubectl delete pod -l app=shortener -n default
    # 观察：HPA 是否拉起新 Pod？告警是否触发？
    ```
  - **场景 B（高延迟）**：注入慢查询到 Redis
    - 在服务里加一个 `?slow=1` 参数，sleep(2)
    - 用 ab/wrk 压测，看 P99 面板和告警
- 截图/录屏建议：每种场景至少 1 张 Grafana 截图 + 1 段告警触发时间戳

### Day 9 — 写 Postmortem
- 任务：按 Google SRE 模板写 1 份故障复盘
- 产出：`postmortems/2026-XX-XX-pod-oom.md`
- 模板：
  ```markdown
  # Postmortem: [简要故障描述]

  **日期**：2026-XX-XX
  **作者**：[你的名字]
  **状态**：Resolved
  **Severity**：SEV-3 (Service Degraded)
  **Reviewers**：[可选，列出帮你 review 的人]

  ## Summary (一段话总结)

  ## Impact (影响范围)
  - 受影响服务 / 用户 / 时长
  - 业务损失估算

  ## Timeline (时间线，UTC+8)
  - HH:MM — 事件 X 发生
  - HH:MM — 监控告警触发
  - HH:MM — 工程师介入
  - HH:MM — 故障恢复

  ## Root Cause (根本原因)
  5 Whys 分析：
  1. 为什么…？因为…
  2. 为什么…？因为…
  …

  ## Trigger (直接触发)
  ## Detection (如何发现)
  ## Resolution (如何恢复)
  ## What Went Well
  ## What Went Wrong

  ## Action Items (行动项)
  | # | Action | Owner | Priority | Due Date |
  |---|--------|-------|----------|----------|
  | 1 | 添加 readinessProbe 失败次数告警 | self | P1 | 2026-XX-XX |
  | 2 | 为服务配置 PDB (PodDisruptionBudget) | self | P2 | 2026-XX-XX |
  | 3 | 文档化"如何手动 kill pod 做演练" | self | P3 | 2026-XX-XX |
  ```

### Day 10 — README + 技术博客
- 任务：写项目 README（架构图 + 截图 + 快速开始），发布 1 篇博客
- 产出：可读性强的项目门面
- README 必含：
  - 项目简介（1 段）
  - 架构图（用 excalidraw/draw.io/mermaid 画）
  - 快速开始（`git clone` 到 `kubectl apply` 三步走）
  - 截图（架构图、Grafana 面板、告警触发、Postmortem 节选）
  - SLO 定义说明
  - 已知限制（诚实列出）
- 博客建议平台：掘金 / CSDN / 知乎 / 个人博客
- 博客标题示例：《从零搭建一个生产级 SRE 实践平台：URL 短链 + K8s + 完整可观测性》

---

## 二、简历怎么写

### 项目板块模板

```
项目名称：基于 K8s 的 URL 短链服务 + 完整 SRE 闭环（个人学习项目）
时间：2026.08 - 2026.09
技术栈：Python · FastAPI · Docker · Kubernetes · k3d · Prometheus · Grafana · Helm

- 基于 FastAPI + Redis 自研短链服务，支持 100+ QPS 压测，P99 延迟 < 80ms
- 通过 kustomize 编排 K8s 多环境部署（dev/prod），本地 k3d 一键拉起
- 集成 kube-prometheus-stack + Grafana 搭建可观测性体系，
  配置 SLI/SLO（99.9% 可用性 + P99<200ms 延迟）
- 制定 3 条告警规则（错误率/P99 延迟/Pod 异常），模拟 OOM/Pod 异常故障，
  验证告警链路触发与恢复
- 主导 1 次故障复盘，输出 Blameless Postmortem，落地 3 项 Action Items
- 撰写技术博客《从零搭建一个生产级 SRE 实践平台》（X 字，平台阅读量 XXX）
```

### 写法要点

1. **用动词开头**：「基于...」「通过...」「集成...」「制定...」「主导...」「撰写...」
2. **量化数字**：QPS、延迟、可用性、告警条数、Action Items 数量、博客字数/阅读量
3. **绑定工具到动作**：不要孤立列"K8s、Prometheus"，要说"通过 kustomize 编排"、"集成 kube-prometheus-stack"
4. **诚实定位**：标题里写"个人学习项目"——面试官对零经验心知肚明，诚实加分
5. **链接齐全**：GitHub 仓库地址 + 博客链接 + README 截图

### 简历项目放置位置

- 简历顺序：**教育背景 → 项目经历（含本项目）→ 技能清单 → 其他**
- 项目板块只放 2-3 个最硬的项目，本项目 + 1 个课程项目
- 不要把本项目写在最前（除非你没有任何其他项目）

### 不要做的事

- ❌ 写"百万 QPS"（你压测 100 QPS 写百万，面试必挂）
- ❌ 写"主导公司 X 项目"（这是个人项目，不要伪装成企业项目）
- ❌ 写"使用 Spring Cloud、Kafka、Istio"（你没用就别写）
- ❌ 省略 Postmortem 经历（这是最大的差异化点）

---

## 三、诚实回答清单（面试高频问题 + 诚实回答）

### 问 1：这是真实项目吗？是公司项目还是个人项目？
**诚实回答**：
> 这是我的个人学习项目。我意识到作为零经验候选人，简历上需要有可验证的 SRE 凭据，所以花了 10 天时间从零搭建了完整的 SRE 闭环——包括一个真实可运行的微服务、K8s 部署、Prometheus+Grafana 监控、告警规则和 Postmortem。目标不是模拟生产，而是完整理解 SRE 每一环。

### 问 2：为什么没有用 Terraform？
**诚实回答**：
> 1-2 周时间有限，Terraform 本身有学习成本。我做了取舍：先掌握 K8s 部署的本质（清单+YAML+GitOps 思想），把 IaC 放在下一步。我已经在 README 的"后续计划"里写了 Terraform 是下个学习目标。

### 问 3：日活在多少？撑得住生产流量吗？
**诚实回答**：
> 我用 ab/wrk 做了压测，4 副本下能扛 100+ QPS，P99 < 80ms。这离生产级（千 QPS、万 QPS）有差距，但作为学习项目，重点是 SRE 闭环的完整性，不是性能调优。生产级还需要做：Redis 集群、数据库分片、CDN 加速、流量镜像、容量规划。

### 问 4：这跟生产环境有什么区别？
**诚实回答**（主动列出来是加分项）：
> 主要差距：
> 1. **缺 IaC**：没接 Terraform，云资源还是手动管理
> 2. **缺 GitOps**：没用 ArgoCD，部署还是 kubectl apply
> 3. **缺多副本生产级高可用**：单节点 k3d，没有跨 AZ
> 4. **缺安全加固**：没做 RBAC、NetworkPolicy、Pod Security Standards
> 5. **缺完整日志栈**：只用了 stdout JSON，没接 Loki 做聚合检索
> 6. **缺混沌工程**：只手动 kill pod 做了 1 次演练，没有自动化 chaos 平台
>
> 我对这些差距是清楚的，这也是我接下来要补的方向。

### 问 5：接下来打算做什么？
**诚实回答**：
> 我给自己规划的成长路径是：
> 1. 短期（1-2 个月）：学 Terraform + Helm 高级用法，把 IaC 补齐
> 2. 中期（3-6 个月）：做第二个项目——SRE 工具集（值班机器人/告警聚合），把"造工具"能力补上
> 3. 长期：基于真实生产环境积累 SLO/事故响应经验，从"会用工具"进化到"能设计 SRE 体系"

### 问 6：SLO burn rate 告警为什么这么设阈值？什么原理？
**诚实回答**：
> 我用 multi-window multi-burn-rate 思路（Google SRE Workbook 第 5 章）：
> - 短窗口（5min）+ 长窗口（1h）双检查
> - 短窗口快速触发（响应快），长窗口确认（避免抖动）
> - 阈值依据 error budget burn rate：99.9% SLO 一个月 30 天 ≈ 43 分钟 downtime。如果 1 小时烧掉整月预算的 2%，就是 5% 错误率持续 1 小时
> - 我项目里用了简化版（单窗口 2m/5m），完整的 multi-burn-rate 在 Postmortem 后续 Action Items 里

### 问 7：Postmortem 为什么不追责到个人？Blameless 怎么理解？
**诚实回答**：
> Blameless Postmortem 是 Google SRE 文化核心。原因：
> 1. 故障是系统问题，不是个人问题——人会犯错的概率是 100%，系统应该设计成"犯错也能兜底"
> 2. 追责会导致信息隐藏：下次出事故没人敢说真话
> 3. 关注 Root Cause 而不是 Who：5 Whys 问的是"为什么系统允许这件事发生"，不是"谁点的按钮"
> 4. 目标是从故障中学习，不是惩罚

### 问 8：你觉得你项目最大的不足是什么？
**诚实回答**：
> 最大的不足是**没有真实流量**。我在 100 QPS 压测下看指标，但生产环境的流量分布、错误模式、用户行为是模拟不出来的。所以我接下来要进真实生产环境去"看"——通过实习或工作接触真实告警、真实事故、真实的 on-call。我个人项目能证明"我能从零搭起来"，但不能证明"我能扛住生产"。

---

## 附：检查清单（项目交付前自检）

- [ ] GitHub 仓库能 clone 后 `make up`（或 README 命令）一键跑起来
- [ ] README 有架构图、截图、快速开始
- [ ] Postmortem 用 Google SRE 模板，包含 Timeline + Action Items
- [ ] Grafana 面板能 export 成 JSON 提交到仓库
- [ ] 告警规则文件（PrometheusRule YAML）在仓库里
- [ ] 压测脚本和结果截图在仓库里
- [ ] 技术博客已发布（带链接）
- [ ] 简历项目描述按"动词+技术+量化"格式写好
- [ ] 面试诚实回答清单已练习（至少对自己讲 1 遍）
