
# FinSight 改造清单 · 第一期（CEDG + 证据指针约束 + 类型化验证）

> 本清单面向编码执行者（人或 AI 编码助手）。
> 目标：在 FinSight（https://github.com/RUC-NLPIR/FinSight）基础上，实现「先建图、再验证、后渲染」的第一期改造。
> 原则：**最小侵入**——不改整体多智能体框架，不动 `demo/` 目录，所有改动集中在 `src/`。

---

## 0. 背景与目标

FinSight 现状的问题：

1. **数字零保护**：写作模型把数字直接写进正文（`section_writing` prompt 允许自由写作）。
2. **引用是名字不是地址**：模型写 `[Source: 来源名称]`，成文后由 `_add_reference()` 用 embedding/BM25 相似度回填编号（相似 ≠ 支撑，且找不到时硬塞 top-1），这是引用忠实度仅 72.9% 的机械根源。
3. **产出无校验**：`<draft>` 收稿后直接进 `_final_polish` 二次改写（二次幻觉源），无任何结构校验。

第一期改造目标（对应论文机制③④与 CEDG 图结构）：

- 证据显式编址（E001、E002…），引用只能用地址；
- 正文数字只允许写 `⟨VAR:name⟩` 占位符，渲染期才替换真值（「数字零生成」）；
- 草稿收稿前做结构校验，不合格打回重写；
- 论断按 num/fact/infer 分型落图为 CEDG（`cedg.json`）；
- 数值论断程序化重算验证 + 会计恒等式校验；
- 引用回填从「相似度检索」改为「ID 直译」，旧逻辑保留为对照开关（供消融实验）。

**重要工程说明**：API 模型无法做 logit 级约束解码，本清单的实现路线是「prompt 约束 + 解析校验 + 不合格打回重写」的系统级约束解码。

---

## 1. 代码现状关键位置（已核实）

| 事实                                                           | 位置                                                                                                                                                                                                                                |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 写作主循环：Phase 0 大纲 → Phase 1 逐节写作 → Phase 2 后处理 | `src/agents/report_generator/report_generator.py` `async_run()`（772–931 行）                                                                                                                                                  |
| 写作 prompt（让模型自由写数字、写 `[Source: 名称]`）         | `src/agents/report_generator/prompts/financial_company_prompts.yaml` `section_writing`（1–46 行）；另有 `financial_industry_prompts.yaml`、`general_prompts.yaml` 同名段，及每份文件内的 `section_writing_wo_chart` 变体 |
| 事后引用回填（embedding 检索 + 0.2 阈值 + top-1 兜底）         | `report_generator.py` `_add_reference()`（438–523 行）                                                                                                                                                                         |
| 数据入库（证据 ID 分配点）                                     | `src/memory/variable_memory.py` `add_data()`（292 行）                                                                                                                                                                          |
| 记忆序列化                                                     | `variable_memory.py` `save()`（59–87 行）/ `load()`（89–126 行）                                                                                                                                                            |
| 写作时数据展示（`Data ID {idx}` 枚举处）                     | `report_generator.py` `_prepare_init_prompt()`（148–158 行）                                                                                                                                                                   |
| 代码执行通道（`get_data` 等函数注入处）                      | `report_generator.py` `_prepare_executor()`（94–136 行）                                                                                                                                                                       |
| 草稿收稿动作（当前无条件 `continue: False`）                 | `report_generator.py` `_handle_draft_action()`（213–220 行）                                                                                                                                                                   |
| 二次改写                                                       | `report_generator.py` `_final_polish()`（222–238 行）                                                                                                                                                                          |
| 后处理五子阶段（image→abstract→cover→reference→docx）      | `report_generator.py` `post_process_report()`（527 行起；docx 渲染在 601–641 行）                                                                                                                                              |
| prompt 加载机制（按名字从 yaml 取）                            | `report_generator.py` 56–65 行（`prompt_loader.get_prompt('section_writing')` 等）                                                                                                                                             |
| outline 阶段（**不需要改**）                             | `outline_draft` / `outline_critique` / `outline_refinement` 三个 prompt，大纲不含数字与引用                                                                                                                                   |

---

## 2. 改造步骤（按依赖顺序执行）

### 第 1 步：证据显式编址（0.5 天）

**文件**：`src/memory/variable_memory.py`

1. `Memory.__init__` 中新增：
   ```python
   self.data2eid: Dict[int, str] = {}   # id(data_item) -> "E001"
   self._eid_counter = 0
   ```
2. `add_data()`（292 行）在数据入库时分配 ID：
   ```python
   def add_data(self, data: Any):
       self.data.append(data)                      # 既有逻辑保持
       self._eid_counter += 1
       self.data2eid[id(data)] = f"E{self._eid_counter:03d}"
   ```

   （若 `add_data` 既有签名/逻辑不同，以保持原逻辑为前提追加这两行。）
3. `save()/load()` 的 `memory_state` 字典中对称加入 `data2eid` 与 `_eid_counter`。
4. 新增查询方法：
   ```python
   def get_eid(self, data_item) -> str: return self.data2eid.get(id(data_item), "")
   def get_evidence_by_eid(self, eid: str):
       for item in self.data:
           if self.data2eid.get(id(item)) == eid: return item
       return None
   ```

**验收**：任意跑一次数据收集后，`memory.data2eid` 非空且 ID 单调递增；重启 load 后 ID 不丢。

### 第 2 步：派生变量注册表（1 天）

**文件**：`report_generator.py` `_prepare_executor()`（94–136 行）

1. `__init__` 或 `_prepare_executor` 开头初始化：
   ```python
   self.var_registry = {}   # name -> {"value":..., "code":..., "depends_on":[eid,...]}
   ```
2. 在注入 executor 命名空间的函数组里（与 `get_data` 并列）新增：
   ```python
   def _set_var(name: str, value, depends_on: list = [], _code: str = ""):
       self.var_registry[name] = {"value": value, "depends_on": depends_on, "code": _code}
       return value
   ```

   并以与 `get_data` 相同的方式暴露给被执行代码。
3. `data_api` prompt 段（在各 prompt yaml 中）补充约定：**任何计算结果必须先 `_set_var("name", value, depends_on=["E012"], _code="<计算表达式>")`，正文才能引用 `⟨VAR:name⟩`**。

**验收**：在 `<execute>` 里调用 `_set_var("x", 42, depends_on=["E001"])` 后，`self.var_registry["x"]["value"] == 42`。

### 第 3 步：写作 prompt 改为指针式写作（1 天）

**文件**：`financial_company_prompts.yaml`、`financial_industry_prompts.yaml`、`general_prompts.yaml`（每份的 `section_writing` 与 `section_writing_wo_chart` 两个变体都要改，共 6 处）

改动点：

1. Citation 规则（原第 12 行）改为：
   - 引用一律写 `[Source:E012]` 形式的证据 ID，**禁止写来源名称**；
   - 数据上下文中的每条证据以 `**Evidence [E012] (data_id=N):**` 形式给出（配合第 4 步的 data_info 修改）。
2. 新增数字规则：
   - 正文**禁止直接出现任何数字**（年份、章节号除外）；
   - 金额、比率、数量一律写 `⟨VAR:var_name⟩` 占位符，渲染时才替换；
   - 占位符引用的变量必须已在 `<execute>` 阶段通过 `_set_var` 注册。
3. `<draft>` 输出前自检清单写进 prompt：每个 `[Source:E…]` 是合法 E-ID；每个数字都是 `⟨VAR:…⟩`；推断性表述若无证据需写 `[INFER]` 标记。
4. `final_polish` prompt 追加：**必须原样保留所有 `⟨VAR:…⟩`、`[Source:E…]`、`[INFER]` 标记，禁止增删改**。

**注意**：`section_writing_wo_chart` 是 `enable_chart=False` 路径（`report_generator.py` 173–185 行），漏改会导致该路径退化为旧行为。

### 第 4 步：data_info 改用 E-ID 展示（0.5 天）

**文件**：`report_generator.py` `_prepare_init_prompt()`（148–158 行）

把

```python
data_info += f"**Data ID {idx}:**\n{item.brief_str()}\n\n"
```

改为

```python
eid = self.memory.get_eid(item)
data_info += f"**Evidence [{eid}] (data_id={idx}):**\n{item.brief_str()}\n\n"
```

analysis_result 列表同理（`get_analysis_result` 分支，分配同序列 E-ID 或加前缀 `A001`，二选一，保持全库唯一即可）。

### 第 5 步：草稿解析器 + 打回重写循环（2 天，本期核心）

**新建** `src/cedg/__init__.py` 与 `src/cedg/draft_parser.py`：

```python
import re
from dataclasses import dataclass, field

@dataclass
class Claim:
    cid: str
    ctype: str            # num / fact / infer
    text: str
    source_eids: list = field(default_factory=list)
    var_names: list = field(default_factory=list)

@dataclass
class ParsedDraft:
    claims: list
    errors: list          # 硬错误 → 打回
    warnings: list        # 软警告 → 记录不拦截

SOURCE_RE = re.compile(r'\[Source:(E\d{3})\]')
VAR_RE    = re.compile(r'⟨VAR:([A-Za-z_][\w]*)⟩')
BARE_NUM  = re.compile(r'(?<![⟨\w:])\d[\d,]*\.?\d*%?')   # 排除 ⟨VAR: 内部与 E 编号
INFER_RE  = re.compile(r'\[INFER\]')

def parse_draft(text, valid_eids: set, valid_vars: set) -> ParsedDraft:
    # 1. 抽取 Source / VAR 标记
    # 2. 悬空指针：Source 的 eid ∉ valid_eids 或 VAR 名 ∉ valid_vars → errors
    # 3. 裸数字：剥掉所有 ⟨VAR:…⟩、[Source:E…]、年份(19xx/20xx)、章节号后仍命中 BARE_NUM → errors
    # 4. 论断切分（按句号/段落），分型：含 VAR → num；含 Source 无 VAR → fact；含 [INFER] 或两者都无 → infer
    # 5. 无源论断：含判断性动词（增长/下滑/领先/恶化/超预期…）且段内无 Source → warnings
    ...
```

**改** `report_generator.py` `_handle_draft_action()`（213–220 行）：

```python
async def _handle_draft_action(self, action_content: str):
    parsed = parse_draft(
        action_content,
        valid_eids=set(self.memory.data2eid.values()),
        valid_vars=set(self.var_registry.keys()),
    )
    if parsed.errors:
        feedback = "Your draft was REJECTED. Fix the following errors and output <draft> again:\n" \
                   + "\n".join(f"- {e}" for e in parsed.errors)
        return {'action': 'draft', 'action_content': action_content,
                'result': feedback, 'continue': True}     # 打回重写
    self.section_claims = getattr(self, 'section_claims', {})
    self.section_claims[self._current_section_idx] = parsed.claims
    return {'action': 'draft', 'action_content': action_content,
            'result': action_content, 'continue': False}
```

`_current_section_idx` 在 Phase 1 循环（856–907 行）每节开始前设置。

**改** `_final_polish()`（222–238 行）：polish 返回后做指针集合 diff——

```python
def _ptr_set(text): 
    return set(SOURCE_RE.findall(text)) | set(VAR_RE.findall(text))
if not _ptr_set(final_section).issubset(_ptr_set(draft_section)):
    final_section = draft_section        # polish 引入/丢失指针 → 弃用 polish 结果
```

**验收**：构造一份含裸数字「营收 123.4 亿元」和悬空 `[Source:E999]` 的假草稿调用 `_handle_draft_action`，应返回 `continue: True` 且 feedback 列出两条错误。

### 第 6 步：CEDG 数据结构与落图（2 天）

**新建** `src/cedg/graph.py`：

```python
import json
from dataclasses import dataclass, field, asdict

@dataclass
class EvidenceNode:
    eid: str
    kind: str          # tool_result / analysis / web
    ref_repr: str      # brief_str() 摘要

@dataclass
class ClaimNode:
    cid: str
    ctype: str         # num / fact / infer
    text: str
    var_names: list = field(default_factory=list)
    kappa: float = 1.0
    nu: str = "pending"      # pending / verified / failed / infer

@dataclass
class CEDG:
    evidence: dict = field(default_factory=dict)   # eid -> EvidenceNode
    claims: dict = field(default_factory=dict)     # cid -> ClaimNode
    edges: list = field(default_factory=list)      # [(src, dst, "sup"|"derive"|"conflict")]
    def to_json(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"evidence": {k: asdict(v) for k, v in self.evidence.items()},
                       "claims": {k: asdict(v) for k, v in self.claims.items()},
                       "edges": self.edges}, f, ensure_ascii=False, indent=2)
```

**改** `report_generator.py`：

- `__init__` 加 `self.cedg = CEDG()`；
- Phase 1 每节收稿后：遍历 `parsed.claims` 建 ClaimNode；`source_eids` 各记一条 `(eid, cid, "sup")` 边；`var_names` 查 `var_registry[name]["depends_on"]` 记 `(eid, cid, "derive")` 边；
- Phase 2 结束时 `self.cedg.to_json(os.path.join(self.working_dir, "cedg.json"))`。

**验收**：跑完一节，`cedg.json` 存在且 claims 数与该节论断数一致、edges 非空。

### 第 7 步：引用回填改为指针直译（1 天）

**文件**：`report_generator.py` `_add_reference()`（438–523 行）、`src/config/default_config.yaml`

1. 配置文件新增：
   ```yaml
   citation_mode: pointer   # pointer | legacy
   verify_mode: marking     # strict | marking
   ```
2. `_add_reference` 开头分支：`citation_mode == 'pointer'` 时跳过整个 embedding 检索段（464–511 行），改为：
   ```python
   match_list = re.findall(r'\[Source:(E\d{3})\]', content)
   for eid in match_list:
       item = self.memory.get_evidence_by_eid(eid)
       # 用 item.name / item.source / (ClickResult 的) link 生成参考文献条目
       # 替换 [Source:E012] → [n]（编号规则沿用既有 total_cited_dict 去重逻辑）
   ```

   `legacy` 分支保留原逻辑原样——**主实验「生成时绑定 vs 事后匹配」的对照就靠这个开关**。

**验收**：同一任务分别以 `pointer` 和 `legacy` 跑一遍，两份报告的 Reference Data Sources 章节都能正常生成。

### 第 8 步：类型化验证算子（2 天）

**新建** `src/cedg/verifiers.py`：

1. **数值重算（零模型成本）**：遍历 `nu == "pending"` 且 `ctype == "num"` 的论断，取 `var_registry[name]["code"]` 在 executor 中重跑，与注册值比对（容差 1e-6 或按格式化精度），不一致 → `nu = "failed"`；
2. **会计恒等式**：实现 3–5 条勾稽关系（资产 = 负债 + 所有者权益；营业利润 → 利润总额 → 净利润链条；现金及现金等价物净增加额 = 经营 + 投资 + 筹资现金流净额），写成 `(name, lhs_expr, rhs_expr, tolerance)` 表，对引用了财务报表类证据的数值论断逐条校验；
3. **infer 论断**：只登记前提链（前提 claim 的 cid 列表），`nu` 置 `"infer"`，不判真伪——论文口径「推断只保证可追溯，永不提升为事实」。

**改** `post_process_report()`（527 行起）：在子阶段 3（reference）与 4（docx 渲染）之间插入子阶段 `verify`（注意 resume 状态机 `_post_stage` 编号要同步调整）：

- `verify_mode == 'strict'`：失败论断所在节打回 Phase 1 重写（最多重试 1 次，防止死循环）；
- `verify_mode == 'marking'`：失败论断在正文标 `[待核实]`，并把 κ 衰减记入 `cedg.json`。

### 第 9 步：渲染期替换 + 端到端验证（1.5 天）

1. `post_process_report` 渲染 docx 之前（601 行附近），对 `report.sections` 全文执行：
   ```python
   def render_vars(text, registry):
       return VAR_RE.sub(lambda m: format_value(registry[m.group(1)]["value"]), text)
   ```

   `format_value` 统一千分位与小数位（例：金额 2 位小数、比率 1 位 + %）——「渲染与生成解耦」是论文卖点，格式化集中在此。
2. 用 `docs/example_configs/my_config_company.yaml` 跑一家小公司全流程；人工抽 50 条引用核对支撑性，记录改造前后引用忠实度对比（对照组用 `citation_mode: legacy`）。

---

## 3. 修改/新建文件汇总

**修改（6 个）**

- `src/memory/variable_memory.py`（add_data / save / load / 新增 get_eid、get_evidence_by_eid）
- `src/agents/report_generator/report_generator.py`（_prepare_init_prompt / _prepare_executor / _handle_draft_action / _final_polish / _add_reference / post_process_report / async_run Phase 1 循环）
- `src/agents/report_generator/prompts/financial_company_prompts.yaml`（section_writing + section_writing_wo_chart + data_api + final_polish）
- `src/agents/report_generator/prompts/financial_industry_prompts.yaml`（同上四处）
- `src/agents/report_generator/prompts/general_prompts.yaml`（同上四处）
- `src/config/default_config.yaml`（citation_mode / verify_mode）

**新建（3 个）**

- `src/cedg/__init__.py`
- `src/cedg/draft_parser.py`
- `src/cedg/graph.py`、`src/cedg/verifiers.py`

**不改**：`demo/` 目录；outline 相关 prompt（outline_draft / outline_critique / outline_refinement）。

---

## 4. 实施注意事项

1. prompt 改动务必 3 个文件 × 2 个变体同步，漏一处会出现特定报告类型退化为旧行为。
2. 打回重写要设上限（建议 2 次），超过后放行并在 `cedg.json` 记 `nu="unresolved"`，避免死循环烧 token。
3. 裸数字正则需维护白名单：年份（19xx/20xx）、章节编号、已有 Source 标记内的内容。
4. `checkpoint` resume 机制贯穿 Phase 1/2（`save()/load()`），新增的状态（var_registry、section_claims、cedg）都要纳入 `_get_persist_extra_state` / `_load_persist_extra_state`（652、662 行），否则断点续跑会丢图。
5. 第二期规划（本清单不含）：机制①真值发现 + 机制②反驳检索（改 `src/agents/search_agent/search_agent.py`）；第三期：机制⑤快照隔离（回到 variable_memory 加版本号）+ 机制⑥置信度拒答 + 图表诚实性校验（`src/utils/figure_helper.py`）。
