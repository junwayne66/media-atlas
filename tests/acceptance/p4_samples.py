"""P4 Exit 验收样本：20 条中英 AI/科技样本，用于本地化端到端验收（docs/modules/43 §13）。

每样本 = 若干句的"源/目标忠实译对"（保留数字/产品名/否定）+ 目标时长。下游的
一致性检查 / 字幕 / 口型 / 局部重跑全由 domain + Fake provider 在测试中即时组装——这里
只提供最小输入，避免固化脆弱数据。忠实译对是"数字/产品名/否定一致率 100%"验收的正样本；
其中刻意含数字、产品名、否定，以证明检查非空跑。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class P4Sentence:
    sentence_id: str
    source: str
    target: str
    source_lang: str
    target_lang: str
    entities: tuple[str, ...]
    duration_ms: int


@dataclass(frozen=True)
class P4Sample:
    id: str
    category: str  # ai / non-ai
    target_language: str
    sentences: tuple[P4Sentence, ...]


def _s(sid, source, target, sl, tl, entities, dur=5000) -> P4Sentence:
    return P4Sentence(sid, source, target, sl, tl, tuple(entities), dur)


# zh → en（目标 en-US）
_ZH_EN: list[P4Sample] = [
    P4Sample(
        "z1",
        "ai",
        "en-US",
        (
            _s(
                "z1-0",
                "苹果发布了 M5 芯片。",
                "Apple released the M5 chip.",
                "zh-CN",
                "en-US",
                ("Apple", "M5"),
            ),
            _s(
                "z1-1",
                "它比上代快 2 倍。",
                "It is 2 times faster than the last one.",
                "zh-CN",
                "en-US",
                (),
            ),
        ),
    ),
    P4Sample(
        "z2",
        "ai",
        "en-US",
        (
            _s(
                "z2-0",
                "这颗芯片不需要联网。",
                "This chip does not need internet.",
                "zh-CN",
                "en-US",
                (),
            ),
            _s(
                "z2-1",
                "端侧推理只用 8 瓦。",
                "On-device inference uses only 8 watts.",
                "zh-CN",
                "en-US",
                (),
            ),
        ),
    ),
    P4Sample(
        "z3",
        "ai",
        "en-US",
        (
            _s(
                "z3-0",
                "OpenAI 的模型有 175 亿参数。",
                "The OpenAI model has 175 billion parameters.",
                "zh-CN",
                "en-US",
                ("OpenAI",),
            ),
            _s("z3-1", "它不开源。", "It is not open source.", "zh-CN", "en-US", ()),
        ),
    ),
    P4Sample(
        "z4",
        "non-ai",
        "en-US",
        (
            _s(
                "z4-0",
                "这道菜要煮 15 分钟。",
                "This dish takes 15 minutes to cook.",
                "zh-CN",
                "en-US",
                (),
            ),
            _s("z4-1", "别放太多盐。", "Do not add too much salt.", "zh-CN", "en-US", ()),
        ),
    ),
    P4Sample(
        "z5",
        "non-ai",
        "en-US",
        (
            _s(
                "z5-0",
                "这条路全长 3 公里。",
                "This road is 3 kilometers long.",
                "zh-CN",
                "en-US",
                (),
            ),
            _s(
                "z5-1",
                "步行大约 30 分钟。",
                "Walking takes about 30 minutes.",
                "zh-CN",
                "en-US",
                (),
            ),
        ),
    ),
    P4Sample(
        "z6",
        "ai",
        "en-US",
        (
            _s(
                "z6-0",
                "英伟达的 H100 很贵。",
                "The Nvidia H100 is very expensive.",
                "zh-CN",
                "en-US",
                ("Nvidia", "H100"),
            ),
            _s(
                "z6-1",
                "一张卡要 30000 美元。",
                "One card costs 30000 dollars.",
                "zh-CN",
                "en-US",
                (),
            ),
        ),
    ),
    P4Sample(
        "z7",
        "ai",
        "en-US",
        (
            _s(
                "z7-0",
                "这个模型支持 100 种语言。",
                "This model supports 100 languages.",
                "zh-CN",
                "en-US",
                (),
            ),
            _s(
                "z7-1",
                "但它不支持方言。",
                "But it does not support dialects.",
                "zh-CN",
                "en-US",
                (),
            ),
        ),
    ),
    P4Sample(
        "z8",
        "non-ai",
        "en-US",
        (
            _s("z8-0", "电影时长 2 小时。", "The movie is 2 hours long.", "zh-CN", "en-US", ()),
            _s("z8-1", "结局并不圆满。", "The ending is not happy.", "zh-CN", "en-US", ()),
        ),
    ),
    P4Sample(
        "z9",
        "ai",
        "en-US",
        (
            _s(
                "z9-0",
                "谷歌的 Gemini 上线了。",
                "Google Gemini is now live.",
                "zh-CN",
                "en-US",
                ("Google", "Gemini"),
            ),
            _s(
                "z9-1",
                "免费版每天 50 次。",
                "The free tier allows 50 times a day.",
                "zh-CN",
                "en-US",
                (),
            ),
        ),
    ),
    P4Sample(
        "z10",
        "non-ai",
        "en-US",
        (
            _s(
                "z10-0",
                "这款手机电池 5000 毫安。",
                "This phone has a 5000 mAh battery.",
                "zh-CN",
                "en-US",
                (),
            ),
            _s("z10-1", "充电只要 1 小时。", "Charging takes only 1 hour.", "zh-CN", "en-US", ()),
        ),
    ),
]

# en → zh（目标 zh-CN）
_EN_ZH: list[P4Sample] = [
    P4Sample(
        "e1",
        "ai",
        "zh-CN",
        (
            _s(
                "e1-0",
                "Claude 4 handles 200000 tokens.",
                "Claude 4 能处理 200000 个 token。",
                "en-US",
                "zh-CN",
                ("Claude",),
            ),
            _s("e1-1", "It does not forget context.", "它不会忘记上下文。", "en-US", "zh-CN", ()),
        ),
    ),
    P4Sample(
        "e2",
        "ai",
        "zh-CN",
        (
            _s(
                "e2-0",
                "The M5 chip has 3 cores.",
                "M5 芯片有 3 个核心。",
                "en-US",
                "zh-CN",
                ("M5",),
            ),
            _s("e2-1", "Power is only 8 watts.", "功耗只有 8 瓦。", "en-US", "zh-CN", ()),
        ),
    ),
    P4Sample(
        "e3",
        "ai",
        "zh-CN",
        (
            _s(
                "e3-0",
                "Tesla ships 2 million cars.",
                "特斯拉交付 2 百万辆车。",
                "en-US",
                "zh-CN",
                (),
            ),  # Tesla→特斯拉 本地化，非 verbatim 保留
            _s("e3-1", "It is not cheap.", "它并不便宜。", "en-US", "zh-CN", ()),
        ),
    ),
    P4Sample(
        "e4",
        "non-ai",
        "zh-CN",
        (
            _s("e4-0", "Bake it for 20 minutes.", "烤 20 分钟。", "en-US", "zh-CN", ()),
            _s("e4-1", "Do not open the oven.", "别打开烤箱。", "en-US", "zh-CN", ()),
        ),
    ),
    P4Sample(
        "e5",
        "non-ai",
        "zh-CN",
        (
            _s("e5-0", "The trail is 5 miles.", "步道全长 5 英里。", "en-US", "zh-CN", ()),
            _s("e5-1", "Bring 2 bottles of water.", "带 2 瓶水。", "en-US", "zh-CN", ()),
        ),
    ),
    P4Sample(
        "e6",
        "ai",
        "zh-CN",
        (
            _s(
                "e6-0",
                "Meta open-sourced Llama 3.",
                "Meta 开源了 Llama 3。",
                "en-US",
                "zh-CN",
                ("Meta", "Llama"),
            ),
            _s("e6-1", "It has 70 billion parameters.", "它有 70 亿参数。", "en-US", "zh-CN", ()),
        ),
    ),
    P4Sample(
        "e7",
        "ai",
        "zh-CN",
        (
            _s("e7-0", "The API costs 3 dollars.", "接口每次 3 美元。", "en-US", "zh-CN", ()),
            _s("e7-1", "There is no free plan.", "没有免费套餐。", "en-US", "zh-CN", ()),
        ),
    ),
    P4Sample(
        "e8",
        "non-ai",
        "zh-CN",
        (
            _s("e8-0", "The book has 300 pages.", "这本书有 300 页。", "en-US", "zh-CN", ()),
            _s("e8-1", "It is not boring.", "它不枯燥。", "en-US", "zh-CN", ()),
        ),
    ),
    P4Sample(
        "e9",
        "ai",
        "zh-CN",
        (
            _s(
                "e9-0",
                "Nvidia sold 4 million GPUs.",
                "英伟达卖出 4 百万块 GPU。",
                "en-US",
                "zh-CN",
                (),
            ),  # Nvidia→英伟达 本地化，非 verbatim 保留
            _s("e9-1", "Demand does not slow down.", "需求没有放缓。", "en-US", "zh-CN", ()),
        ),
    ),
    P4Sample(
        "e10",
        "non-ai",
        "zh-CN",
        (
            _s("e10-0", "The flight takes 12 hours.", "航班要 12 小时。", "en-US", "zh-CN", ()),
            _s("e10-1", "Do not miss the gate.", "别错过登机口。", "en-US", "zh-CN", ()),
        ),
    ),
]

SAMPLES: list[P4Sample] = _ZH_EN + _EN_ZH
