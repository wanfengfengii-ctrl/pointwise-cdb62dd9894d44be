# 台架录制交班簿

试验中心台架计量组用这个项目固定采样录制、核对设备接口读数，并把必要载荷交给无源库访问权限的夜班。夜班更正后，交班员按件号复领父件、成功子件和逐视图差账。项目使用 Python 3.11 标准库和两个独立的 SQLite 库。

## 运行

在项目根目录运行控制台随项目提供的完整回归入口。

```sh
python3 -B check_project.py
```

可直接用 `python3 -B -m unittest discover -s tests -t .` 执行同一项目的 unittest 发现。演示使用项目内的 `examples/bench.json` 和独立临时库，实际执行登记、签发、移走源库、接件、更正、拒绝矛盾批及重开复领。

```sh
python3 -B demo.py
```

## 使用顺序

调用方打开并管理两条空闲 SQLite 连接。源连接依次初始化 `capture.catalog.RecordingCatalog`、`views.registry.ViewRegistry`、`handover.issued_index.IssuedIndex`。隔离连接初始化 `offline.revisions.RevisionStore`。写入入口自行管理事务，调用方在操作之间可关闭并重开连接。重复初始化补齐表结构，保留已有记录。

1. `capture.recording.register_recording(catalog, external_name, banks)` 接收具名非空字节映射或名称与字节的有序对，返回不透明录制号。存储区名与其载荷绑定，同名同映射可重投。
2. `views.registry.register_views(catalog, registry, recording_id, layouts)` 接收 `views.layout.ViewLayout` 批次，返回按名排列的固定目录。与既有定义完全一致的定义可重投。一个批次内的名称唯一。
3. `audit.archive.source_check(catalog, registry, recording_id, view_name)` 返回 `AuditedView`，包含整数明细及计数、和、最小值及最大值。
4. `handover.issue.issue_package(catalog, registry, index, recording_id, names)` 接收唯一视图名的非空有序选单，返回 `IssuedPackage` 的件号和完整字节。相同录制和选单复领原件，顺序不同形成另一份选单。
5. `offline.accept.accept_package(store, wire)` 校验并保存交班件，返回父件号。反复接纳同件可复领。已有件号锁定包版本、出处、视图和载荷。
6. `offline.settle.correct_package(store, parent_id, requests)` 接收由 `offline.corrections.CorrectionRequest` 组成的非空批次。每项给出 `view_name`、零起算 `element_index` 和整数 `value`。成功返回子件号和 `StoredReceipt`，后续可经 `store.get_receipt(child_id)` 复领。
7. `audit.archive.read_audit(store, package_id)` 按固定顺序读取明确件号。`audit.compare.compare_audits(store, parent_id, child_id)` 核对直接父子关系后返回原序双方明细、统计和精确子减父和值差。

未知录制、视图或件号抛出 `KeyError`，无效定义、越界、无效件、重复冲突或错误父子配对抛出 `ValueError`。字节要求矛盾使用其子类 `ByteConflict`。SQLite 写入错误由入口传播。更正的 `before_commit` 可用于验证事务回滚，回调在两项写入之后、提交之前执行，回调应返回或抛出异常。

## 字节和账目

视图第 i 个元素从 `start + i * stride` 的字节偏移开始。元素内总按地址递增取一或两个字节。负步长改变元素访问顺序。一字节值为 0 至 255，两字节值按大端或小端解释为 0 至 65535。允许相邻元素重叠。明细和核账对每个逻辑元素分别计数，统计使用精确整数。

交班件载荷仅包含选单覆盖的物理字节。同一存储区偏移在所有视图及元素中共享，不同原位置独立。隔离端在同一父件上计算所有更正的写入要求，同位同值可以合并，矛盾则拒绝整批。更正保留父件，用新的固定件号和同事务提交的回执发布子件。

包是 UTF-8 JSON，外层字段为 `version`、`body` 和 `sha256`。摘要为 `version` 与 `body` 组成的对象使用 ASCII 转义、键排序及紧凑分隔符编码后的 SHA-256 十六进制。摘要用于检验传输内容完整性。当前版本 2 的 `body` 含 `id`、`recording`、全件 Base64 `data` 和有序 `views`。每个视图含 `name`、`width`、`byteorder` 与 `elements`，后者按逻辑顺序列出每个元素的包内字节索引。旧版本 1 的 `body` 含相同的 `id`、`recording` 和 `views`，载荷以各视图的 Base64 `data` 内联。旧视图的每个内联字节占独立位置，接纳后仍可正常更正和复领。

样例中 P 为 `[1,2,3,239,173]`，Q 为 `[1,2]`。选 A、B、C 时，交班件只保留 P 前三字节和 Q 两字节。父件读数为 `[513,515,513]`。更正 A 为 1025 后，子件为 `[1025,1027,513]`，和值差为 `[512,512,0]`。同批要求 B 为 1283 会与 A 的共享字节要求冲突。原回归另核对反向视图、同视图重叠和 65537 的精确和值。
