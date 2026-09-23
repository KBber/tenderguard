"""Per-CK-type review questions and recommended actions (spec §十二).

Each entry is keyed by a (review_type, category) pair when possible.
Falls back to per-review_type defaults.
"""

from __future__ import annotations

from tenderguard.app.schemas import ReviewType


# By CK title keyword (best effort, deterministic)
_TITLE_QUESTIONS: list[tuple[str, str, str]] = [
    # (title keyword, review_question, recommended_action)
    ("项目名称", "投标文件全文使用的项目名称是否与招标文件一致？请逐处核对。",
     "在投标文件封面 + 投标函 + 报价表中确认项目名称"),
    ("项目编号", "投标文件的项目编号是否与招标文件完全一致（含连字符 / 大小写）？",
     "使用 grep 全文搜索项目编号；不匹配处视为异常"),
    ("包号", "投标文件的包号是否与招标文件一致？多包项目不得错填包号。",
     "在封皮 + 投标函 + 报价表核对"),
    ("投标人", "投标人主体名称是否与营业执照、信用代码一致？",
     "对比营业执照扫描件，名称差异一律 FAIL"),
    ("授权", "授权书是否由法人代表签字？被授权人信息是否完整？",
     "在 UI 中查看授权书扫描件页码"),
    ("投标报价", "投标报价是否经过销售经理审核？是否在投标最后两周内更新过？",
     "询问销售经理报价决策；要求提供书面审核记录"),
    ("保证金", "保证金是否按招标要求汇出？收款方/账户/截止时间是否一致？",
     "核对银行回单，金额/收款人/截止时间三项逐项校验"),
    ("报价表", "分项报价表中同型号产品的单价是否一致？",
     "比对 Excel 报价表（GROUP BY model），单价不同即 FAIL"),
    ("偏离表", "商务偏离表是否覆盖全部商务要求（付款、质保、交货、培训等）？",
     "逐条核对付款条件/质保期/交货期/培训计划"),
    ("商务响应", "投标文件是否对商务条款逐条响应？是否含负偏离？",
     "查看商务响应章节；标记任何无响应/负偏离项"),
    ("技术响应", "技术参数是否全部满足或超过招标要求？是否含负偏离？",
     "对照参数表逐项打钩；任何不满足即 FAIL"),
    ("资质材料", "资质材料是否按打分表准备齐全？所有资质是否在有效期内？",
     "列出资质清单并核对有效期 / 公司名 / 盖章"),
    ("产品资质", "检测报告 / 节能证书 / 3C / 产品彩页是否齐全？是否在有效期内？",
     "在 UI 中查看资质扫描件；逐项打钩"),
    ("业绩", "业绩是否满足招标要求的数量、年限、合同金额？时间字段是否完整？",
     "对照业绩汇总表 + 合同扫描件；缺一项即 FAIL"),
    ("公章", "投标文件所有需盖章处（封皮/报价表/授权书/资质/检测报告/点对点应答）是否已盖章？",
     "逐章节扫描盖章；缺章一律 FAIL"),
    ("打印、封标", "投标文件是否按招标要求打印、装订、密封？",
     "打印前清单；封装前确认"),
    ("讲标", "讲标 PPT 是否准备好？讲标人员是否熟悉内容？",
     "由讲标人员 + 商务复核"),
    ("失信名单", "所投产品厂家是否在军队采购失信名单？",
     "查询 http://plap.mil.cn/freecms-glht/site/juncai//jdjc/index.html"),
    ("节能环保", "投标产品是否在节能产品政府采购目录？是否在有效期内？",
     "查询政府采购网节能产品目录 + 强制节能标识"),
    ("整体合规", "项目核心信息（名称/编号/法人代表/报价/废标条款）是否全部正确？",
     "由商务负责人逐项核对"),
    ("一致性", "跨文档（投标函 vs 营业执照 vs 检测报告 vs 业绩汇总）字段是否完全一致？",
     "在 UI 中查看 Coverage Matrix，逐字段打钩"),
    ("标书结构", "投标文件目录是否包含招标要求的所有章节？",
     "对照招标文件的 required_sections 列表，逐章节确认存在"),
    ("复盘", "项目投标是否进行了复盘？复盘结论是否记录？",
     "由项目经理组织；输出复盘文档"),
    ("三级审查", "三级审查（自审 / 互审 / 终审）是否完成？审查人是否在日报中留名？",
     "查投标日报邮件 / 飞书消息 / 文档版本历史"),
    ("现场投标", "现场投标授权代表是否熟悉其它家投标文件密封情况？签字确认环节是否对不明确丢分项提出质疑？",
     "由现场负责人 / 商务经理执行"),
    ("样品", "样品是否准备好并已自测通过？现场测试环境是否安排？",
     "由技术部 + 商务部共同确认"),
    ("启动会", "项目启动会是否召开？通读招标文件 / 任务分工是否完成？",
     "检查启动会会议纪要 + 任务分工表"),
    ("夕会", "项目投标过程中是否每日召开夕会？进度 / 风险是否通报？",
     "检查日报 / 飞书群 / 邮件存档"),
    ("风险点评审", "投标过程中的风险点（技术 / 商务）是否评审？",
     "查评审会议纪要"),
    ("模拟打分", "方案评审后是否做了模拟打分？日报邮件是否公示分值及丢分项？",
     "查日报邮件"),
    ("策略", "投标策略（直投 / 借资 / WB）是否确定？",
     "由商务负责人 / 办事处决策"),
    ("应答、签到、解密", "电子投标应答 / 签到 / 解密是否按时完成？是否避免同 IP / 同电脑多账号？",
     "由电子投标负责人操作"),
    ("外采设备", "外采设备清单是否已提交 PD 流程？询价是否含调试费？",
     "检查 PD 系统 + 询价邮件"),
    ("公司更名", "所附资质上的公司名是否为更名前？是否附变更函 / 新执照 / 网页截图？",
     "由商务核对 + 资料员盖章"),
]


def _question_for_title(title: str) -> tuple[str, str] | None:
    """Return (review_question, recommended_action) tailored to the CK title."""

    for kw, q, a in _TITLE_QUESTIONS:
        if kw in title:
            return q, a
    return None


# Per-review-type fallback questions / actions
_TYPE_QUESTIONS: dict[ReviewType, tuple[str, str]] = {
    ReviewType.DOCUMENT_DETERMINISTIC: (
        "请确认抽取的事实（项目名称/编号/包号/金额/型号/页码）正确无误。",
        "在 UI 中点击查看 rule_trace，逐字段比对",
    ),
    ReviewType.DOCUMENT_HYBRID: (
        "请人工核对 LLM 抽取的事实与原文是否一致。",
        "在 UI 中查看 evidence 表，对比 PDF 原文",
    ),
    ReviewType.DOCUMENT_SEMANTIC: (
        "请人工评审语义匹配结果（coverage matrix）。",
        "在 UI 中展开 Requirement Coverage Matrix，逐项确认",
    ),
    ReviewType.EXTERNAL_DATA: (
        "请查询外部权威系统并将结果填入。",
        "查询外部数据（军队网/政采网/产品官网）后回填",
    ),
    ReviewType.PROCESS_HUMAN: (
        "请按公司 SOP 推进该流程事项并留痕。",
        "在 SOP 系统中勾选/留痕",
    ),
    ReviewType.STRATEGY_HUMAN: (
        "请业务负责人基于市场判断做最终决策。",
        "在业务决策会上确定方案",
    ),
}


def derive_review_qa(title: str, review_type: ReviewType) -> tuple[str, str]:
    """Return (review_question, recommended_action) tailored to title + review_type."""

    tailored = _question_for_title(title)
    if tailored:
        return tailored
    return _TYPE_QUESTIONS.get(
        review_type,
        (f"请人工复核 {title}", "在 UI 中查看 evidence 与 rule_trace"),
    )