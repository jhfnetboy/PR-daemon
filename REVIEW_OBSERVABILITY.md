# Review Observability

这份文档只回答一个问题：怎么快速看 PR-Daemon 现在在干什么，以及 DeepSeek / Rapid-MLX 的 review 表现怎么样。

## 一键脚本

根目录已经提供四个快捷脚本：

```bash
./review-status.sh
./review-current.sh
./review-provider-summary.sh
./review-scorecard.sh OWNER REPO PR_NUMBER
```

### 1. 看 watcher 总状态

```bash
./review-status.sh
```

看这些字段：

- `review watcher running` / `not running`
- `active_review=owner/repo#pr`
- `loop_state=...`
- `processed_reviews=N`
- `updated_at=...`

如果显示：

```text
review watcher not running (orphaned active review present)
```

说明 watcher 主进程已经不在了，但上一次 review 的 `current-review.json` 还留着。

### 2. 看当前正在审哪条 PR

```bash
./review-current.sh
```

会直接打印当前 active review 的 JSON；如果没有在审，会显示：

```text
no active codex review
```

### 3. 看 DeepSeek / Rapid-MLX 总体表现

```bash
./review-provider-summary.sh
./review-provider-summary.sh --owner MushroomDAO --limit 20
```

这个总表适合看：

- DeepSeek 一共审了多少条
- Rapid-MLX 一共审了多少条
- 各自平均分
- fallback 次数
- verdict 分布

### 4. 看某一条 PR 的完整评分卡

```bash
./review-scorecard.sh MushroomDAO CityOS 2
./review-scorecard.sh MushroomDAO whitelist 2 --limit 10
```

这个最适合看单条 PR 的：

- 评分
- 漏报
- 误报
- 上一轮改进项是否生效
- 当前还挂着哪些改进项

## 常用 SQL / CLI 命令

### 5. 看 DeepSeek 一共审了多少条

```bash
sqlite3 reviews/model-evals/model-evals.sqlite "
select
  count(*) as total_runs,
  sum(case
    when lower(coalesce(provider,'')) like '%deepseek%'
      or lower(coalesce(model,'')) like '%deepseek%'
    then 1 else 0 end) as deepseek_runs
from model_review_runs;
"
```

### 6. 看最近几条 run 的详细评分

```bash
sqlite3 reviews/model-evals/model-evals.sqlite "
select
  owner || '/' || repo || '#' || pr_number as pr,
  created_at,
  score,
  coalesce(provider,'') as provider,
  coalesce(model,'') as model,
  verdict
from model_review_runs
order by id desc
limit 20;
"
```

### 7. 看它犯过哪些错误

```bash
sqlite3 reviews/model-evals/model-evals.sqlite "
select
  owner || '/' || repo || '#' || pr_number as pr,
  created_at,
  score,
  coalesce(false_positives,'') as false_positives,
  coalesce(misses,'') as misses
from model_review_runs
order by id desc
limit 20;
"
```

### 8. 看针对错误提出了哪些改进项

```bash
sqlite3 reviews/model-evals/model-evals.sqlite "
select
  id,
  owner || '/' || repo || '#' || pr_number as pr,
  improvement_text,
  status,
  coalesce(evaluation,'') as evaluation,
  created_at
from model_improvement_items
order by id desc
limit 30;
"
```

### 9. 看这些改进项有没有真的生效

```bash
sqlite3 reviews/model-evals/model-evals.sqlite "
select
  status,
  count(*) as count
from model_improvement_items
group by status
order by status;
"
```

重点看这些状态：

- `effective`
- `ineffective`
- `needs_followup`
- `proposed`

### 10. 看某次 first-pass 到底是不是 DeepSeek

当前 active PR：

```bash
./watch.sh first-pass
```

指定 PR：

```bash
./watch.sh first-pass MushroomDAO/whitelist 2
```

如果看到：

```text
Provider: deepseek
Fallback Switched: False
```

说明这次 broad first pass 确实走了 DeepSeek，没有掉回本地 Rapid-MLX。

## 推荐日常用法

平时最常用的就是这四个：

```bash
./review-status.sh
./review-current.sh
./review-provider-summary.sh
./review-scorecard.sh MushroomDAO CityOS 2
```
