# 全清单扫描与每日一只精写

本入口落实《设计研报Agent》原先的分层日报：全部标的由Python扫描，AI集中解释，形成一份中文日报。沿用当前35只美股及ETF清单，不将35只全部转换成每天一篇付费长文。

固定业务仍为 `577624ad8459871630c690e5760ae504ac6f2b9f`。采集复用 `mvp_three.py` 的原生数据和技术计算，模型传输复用已验收的 `perform_post_once()`，邮件复用原生 `EmailSender`。没有迁回早期 `personal-tech-research` 原型，没有改变历史冻结包和已消费请求。

## 内容与调用

- 35只全部列出：有效行展示收盘、涨跌、四条均线、RSI12、多日均量比、上下方观察线和收盘与均线的新穿越。
- MACD的DIF、DEA及柱值来自同一次原生技术结果，缺失保留未知，不由模型补算。
- 采集失败、日期错配、不到60根技术窗口、身份或币种不符时保留明确缺口，不补旧价格。
- 观察线使用均线和目标日高低点，明确不是已验证支撑、有效放量突破或即时交易指令。
- 每天选择一只合格公司精写，与综合日报共用最多一次Sol请求；不是35次基础调用加一次精写。
- 复用已选择的Sol profile：high、32768输出上限包含推理、预留人民币0.05元、零重试/零fallback。它是单次预留及估算约束，不是网关硬支出封顶或新收费授权。

精写筛选把可用的近三日来源材料优先于已验证的均线穿越；都没有时，仅按绝对日变动选择写作对象，不当作投资排名。同层按绝对日变动和原清单顺序决定。ETF和带身份限制的标的不进入公司精写。如果没有合格公司，则只保留程序预览，不编造对象。

这是把原方案“重点事件与变化优先”具体化的实现规则，不是声称原Chat已经写过这些精确评分或平局规则。没有增加固定轮换。

保留原七节：今日最值得关注的3件事、重点公司动态、产业链关联分析、QQQ与SOXX市场观察、今天学一个投资概念、值得继续思考的问题、信息来源与数据截止时间。事件不足时不凑三件事。

## 新闻覆盖

`daily-news-feeds.json`只配置此前已保存过来源依据的NVIDIA官方RSS、微软官方博客RSS、Apple Newsroom RSS。每个feed一次GET，无重试、无重定向，最多保留三条近三日元数据；保存原始字节和哈希。RSS的updated修订时间不冒充发布时间，缺时间、过期、未来、重复及超出条数分别记录。

这不是35家公司综合新闻搜索。没有配置feed的标的，以及feed失败或没有合格条目时，新闻均为未知。只传标题、原始链接、发布及获取时间，不把RSS描述或标题当作全文，不推出未提供的经营事实。来源覆盖不足是当前真实限制。

汇总时再次核对新闻窗口，并复用原生formatter重建精写公司的user提示词，避免采集时合格、汇总时已过期的文章仍留在旧提示词里。日报路径显式允许空新闻，旧AAPL新闻候选仍默认要求至少一条。技术块使用已保存的真实TECHNICAL结果，不因重建提示词把已存在的技术结果标成缺失。

## 本地准备

先使用现有原生采集器准备**新目录**：

```powershell
python .github/scripts/daily_news.py --config .github/research/daily-news-feeds.json --out daily-news
python .github/scripts/mvp_three.py --source ../dsa-mode-business-577 --out daily-capture --universe watchlist35 --news-data daily-news/NEWS_PACKET.json
python .github/scripts/daily_briefing.py prepare --source ../dsa-mode-business-577 --data daily-capture --profile .github/research/gpt-6.1-sol-review-profile.json --out daily-ready --session YYYY-MM-DD
```

采集器中的模型传输是合成响应，仅用于取得原生请求；不使用真实供应商密钥。日报汇总只读取实际行情上下文、技术和身份审计，不使用合成模型报告当作研究结论。

准备生成程序日报MD/HTML、邮件EML预览、全清单事实、每股原上下文、精写请求、profile、锁和哈希。`PREPARATION_STATUS.json`展示精写依据、预算、到期和阻断原因。历史材料加 `--historical-preview`，始终不能进入收费发送；此模式不刷新时间戳。

## 收费与输出检查

发送前必须同时满足：

1. 最新完整交易日、前一交易日相邻、行情数值及标的一致。
2. 请求、上下文、全清单事实和profile通过哈希及语义校验。
3. profile与已审阅Sol配置一致、端点一致、未过期、估算满足预留。
4. 手动路径要求owner、首次Run attempt、既有deploy分支和本人Environment审批。自动路径要求owner、首次Run attempt、默认分支上的专用工作流及明确的定时事件或手动生产操作，并匹配自动授权策略。

按交易日创建稳定的远端消费标记；即使重新抓取或更换锁哈希，同一交易日也不能在此入口再调用一次。结果不明、失败、截断或格式不符都不发修复请求。此标记不影响旧单股测试记录。

完整响应必须显式completed，返回模型等于请求模型。新增daily_sections必须有且只有七个规定章节，focus_symbol必须等于程序选择，引用ID只能来自已给事实或保存新闻。精写公司的结构化risk_plan由原生Python函数核算，缺失或非法时失败。原文、解析JSON、Usage和失败记录保留。

这些验证不认证自然语言全部正确，也不证明新闻全面或交易策略有预测力。新综合prompt目前仅有离线测试，尚未进行额外真实付费测试；以前的单AAPL成功不冒充新综合prompt实测。

## 邮件

每份日报一个MD/HTML与一个EML，不为每只标的单独发送邮件。真实发送复用现有DSA SMTP模块。使用现有GitHub Secrets：

- `EMAIL_SENDER`
- `EMAIL_PASSWORD`（邮箱所需的授权凭据，不在聊天或报告中填写）
- `EMAIL_RECEIVERS`

手动邮件入口要求成功的日报状态和确切 `DAILY_REPORT.md` SHA256审核引用。在首次Run attempt、owner与deploy分支上才允许发送。自动邮件入口仅接受本次运行产生、已通过程序检查、哈希未变且材料未过期的自动日报；记录为用户授权自动发送，不冒充人工审阅。两条路径共用当日邮件标记，SMTP不明或失败后均不自动重试。保存结果不包含地址或密码。

```powershell
python .github/scripts/daily_briefing_mail.py --source ../dsa-mode-business-577 --report daily-real/DAILY_REPORT.md --out mail-preview
```

上面只检查准备情况，不联系SMTP。手动真实发送需要另加 `--send --review-reference REPORT_SHA256`；自动工作流使用 `--send --automatic --report-sha256 REPORT_SHA256`。二者都检查相应GitHub运行环境和Secret要求，不能单凭本地加参数发信。

## GitHub入口与定时状态

提供 `.github/workflows/06-daily-consolidated.yml.disabled`，默认prepare；generate在材料准备完成后进入既有Environment；email针对已审阅的历史生成Run。三种操作互斥。免费扫描任务不注入模型或邮箱Secrets。

以上旧手动模板保留disabled后缀和既有Environment设置。用户已明确新指令：“改为自动生成发信，北京时间九点”。该新授权记录在 `.github/research/daily-automatic-policy.json`，新生产流程不再逐次人工审批，不改变旧测试入口的审批设置。

生产模板为 `.github/research/daily-production-workflow.yml`。发布时将其中两处controller版本占位符替换为已提交的完整SHA，并仅将渲染后的 `.github/workflows/06-daily-consolidated.yml` 发布到默认分支main。启动文件checkout固定controller版本及固定业务源577；不把全部历史开发差异直接快进到main。

UTC cron为 `0 1 * * 2-6`，即北京时间周二至周六09:00启动，对应美国周一至周五收盘后的报告；XNYS日历再次排除美国休市日，包括半日市的正确已完成日线。09:00是工作流启动目标，GitHub排队和采集/生成耗时可能使到信晚于09:00。

默认手动操作为 `check_config`，仅检查配置，不采集行情、不调用模型或SMTP。`prepare`仅进行免费采集并保存候选。`run_paid_daily`才是明确的单次生产生成加发信，和schedule使用同一自动授权策略及交易日消费标记。

自动生产先检查SEEKERX及三个邮箱Secrets。缺少邮箱配置或收件人列表不合法时，在依赖安装、行情采集及模型POST之前停止，说明缺少的Secret名称，不输出值。生成函数在POST前再次检查邮箱配置。配置检查不等于SMTP连通性已实测。

自动调用要求事件来自main上的专用工作流，schedule的cron必须匹配策略；其他分支、其他工作流、pull_request、重跑attempt及仅免费准备的手动操作均不能获得自动收费/发信权限。生成状态明确为自动程序检查通过；邮件要求同run、同策略、报告哈希及锁哈希绑定，并检查材料有效期。自然语言未逐次人工核实。

自动模式复用既有精写质量检查；若已确认均线矛盾、未定义情景等`CONFIRMED_CONTRADICTION`或`SOURCE_BLOCKER`，保存原响应与检查结果并拒绝发信，不请求模型补写。非阻断候选和解释限制继续记录，不等同于自然语言已全面核实。

交易日判断使用纽约市场日期及XNYS日历，不按北京时间星期一到五猜测，因此北京时间周六清晨可能仍对应美国周五。实际运行时间决定使用哪个最新完整交易日；模板不伪造尚未收盘的当日K线。

## 验证与暂停

定向测试覆盖合成新闻、缺失/异常行情、日期、focus、请求哈希、语义错配、单POST失败保存、原生风险计算和SMTP桩。测试不访问真实供应商、出版商或SMTP。

免费采集遇到Yahoo 403或429时，先保存HTTP审计，再立即退出当前标的；剩余标的保留批次熔断状态。采集器强制原生yfinance下载在调用线程执行，避免拒绝异常留在后台线程、最后误报240秒超时。不增加绕过限流的端点、代理切换或重试；准确退出不等于行情可用性已恢复。
财务适配器的终止网络信号同样向外传播，不转换成普通财务缺失；普通财务读取错误仍保留明确缺口，不触发重新请求。

已注册的 `01-free-market-validation.yml` 在本审阅分支复用为零付费原生采集诊断：默认仅NVDA，来源可用后才选watchlist35。固定相同业务源，不注入模型或邮箱Secrets，只有contents读取权限，无schedule、模型生成或SMTP阶段。没有一只有效行情时Run明确失败，同时保留结果和HTTP证据；部分有效时仍须查看完整覆盖，Run成功不代表35只全成功。手动启用诊断不等于启用生产日报，验证结束应恢复关闭。

历史真实采集可以离线汇总展示，但缺失的19只不能被标记为恢复；需要未来实际新采集结果。没有重跑已消费批次，也没有新增付费测试。

暂停时禁用工作流，保留全部消费标记和输出；回滚代码使用普通后续提交，不删除消费记录。本文为新增中文操作说明；既有英文单股专题不复制一套日报说明，避免维护两份不同状态。
