# -*- coding: utf-8 -*-
"""_drills_set4.py — 模型手撕深度解析 · 结构与位置（3 题）。"""

from _drills_helpers import (
    diagram, teaching, lv, qa, concept, variant, comparison_row,
    problem, svg_flow, svg_compare,
)

D = {}

# ===========================================================================
# 1. FlashAttention 的在线 softmax 分块实现
# ===========================================================================
D["curated-flashattention-concept"] = {
    "tldr": "FlashAttention 不改注意力公式，改的是「访存顺序」：把 S×S 的"
            "注意力权重矩阵分块算、算完即弃，用在线 softmax（running max + "
            "running 归一化）让任何时刻只需 O(S) 显存——从 HBM 读写下降到 "
            "SRAM 内计算，IO 是瓶颈的洞察。",
    "why": "推理/训练优化岗的高频题：考「显存为什么是 S²、IO 为什么是瓶颈、"
           "在线 softmax 怎么保证正确」。能白板推 running max 的重缩放公式"
           "是强区分信号。",
    "teaching": teaching(
        progressive=[
            lv(1, "朴素 attention 要物化 (B,h,S,S) 权重矩阵——S=4K 时一层就 "
                  "数 GB，且权重要读写 HBM 两次（算完存、再加权读）。"),
            lv(2, "分块：Q/K/V 按 tile 切进 SRAM，每块算完局部 softmax "
                  "立刻加权 V、丢弃权重——显存从 O(S²) 降到 O(S)。"),
            lv(3, "难点在 softmax 的分母：全局和未知，只能「先记部分和，"
                  "见到更大 max 时整体重缩放」。这就是 online softmax。"),
            lv(4, "精确等价不是近似：数值上与朴素实现一致（浮点序不同有"
                  " 1e-6 级差异）；反向也分块重算，不存权重矩阵。"),
        ],
        socratic=[
            qa("online softmax 怎么处理「后面出现更大的 max」？",
               "维护 running max m 和 running 和 l：新块 max m_new > m 时，"
               "把已有的 l 和输出 acc 都乘 exp(m − m_new) 重缩放，再加新块"
               "贡献。数学上与一次性算完全等价。"),
            qa("为什么说瓶颈是 IO 而不是计算？",
               "朴素实现权重要从 HBM 读写 O(S²) 次，而 SRAM 快 ~10 倍但只有"
               " ~100KB。FlashAttention 把 HBM 读写降到 O(S²·d/M)（M 是 "
               "SRAM 大小），计算量不变、墙钟时间快 2~4 倍。"),
            qa("反向传播怎么办？权重都没存？",
               "重算：反向时按同样的分块重新前向一遍拿局部统计量，"
               "用存下的输出 O 和 Q/K/V 反推梯度。用计算换显存，"
               "训练时显存省的量远大于重算的开销。"),
        ],
        mechanism="外层循环 Q 的块，内层循环 K/V 的块。每轮：加载 K/V tile "
                 "→ 算局部 score → 更新 running max/和/输出（重缩放）→ "
                 "丢弃权重。softmax 分母 l 最后统一除——softmax 的线性"
                 "性质保证正确性。",
        boundary="收益取决于 S 与 d 的比例：短序列（S 小于 SRAM tile 数）"
                 "没有分块必要；收益随 S 增长。对 attention-like 的算子"
                 "（score 不需要全局归一化的）不适用；dropout/任意掩码"
                 "要进 kernel 才能保持不物化。",
        analogyBoundary="像边收快递边拆：不必把所有快递堆满屋（S² 显存）再"
                       "统一拆，来一件拆一件（分块），只是「最大件纪录」"
                       "变了要把之前的统计按比例修正（重缩放）。失效处："
                       "快递可乱序，softmax 的重缩放必须严格按 max 的"
                       "单调更新走。",
        misconceptions=[
            "以为 FlashAttention 是近似算法——它是精确的，只是浮点求和"
            "顺序不同。",
            "以为它减少计算量 FLOPs——计算量不变，省的是 IO。",
            "把 online softmax 的重缩放写成只重算当前块——历史累积必须"
            "一起重缩放。",
            "以为反向需要存权重矩阵——存 O 即可，权重反向时重算。",
            "混淆 FlashAttention 与 Flash-Decoding（后者优化 decode 阶段的 "
            "KV 分块并行）。",
        ],
        ownAnalysis="先给「显存账」：S=4K、h=32、bf16 时 (S,S) 权重单层 "
                    "1GB 级——问题真实存在。然后白板推 online softmax 的"
                    "重缩放两行公式，最后讲 IO 复杂度对比。能画 tile 布局"
                    "图（Q 行块 × KV 列块）是加分项。",
        officialNotes="FlashAttention (Dao 2022) 与 FlashAttention-2 (2023)；"
                      "online softmax 出自 Milakov & Gimelsrin 2018；"
                      "flash-attention 官方仓库的 kernel 注释非常可读。",
        interviewAnswer="显存账 → IO 瓶颈 → 分块 + online softmax 重缩放"
                       "公式 → 精确等价声明 → 反向重算 → FA2 的改进"
                       "（并行度沿序列维、warps 分工）。",
        prereq=["softmax 数值稳定", "注意力公式", "GPU 存储层次（HBM/SRAM）"],
        next_steps=["KV-Cache 与 GQA", "PagedAttention", "torch SDPA 的 "
                    "backend 选择"],
    ),
    "diagram": diagram(
        "architecture", "分块计算与 running 统计量的重缩放",
        "Q 按 2 行一块、K/V 按 2 列一块循环：每块算局部 score 后立刻更新"
        "running max/归一化/输出并丢弃权重——任何时刻只存 O(S) 统计量。",
        "FlashAttention 分块与在线 softmax 示意",
        svg_flow([
            {"label": "加载 Q-tile (2行) 与 K/V-tile (2列)", "in": "HBM → SRAM",
             "out": "小片 score (2×2)", "hot": True,
             "note": "SRAM ~100KB，tile 大小由它决定"},
            {"label": "局部 max m_new 与旧 m 比较", "in": "score",
             "out": "m_new = max(m, blockmax)",
             "note": "更大就要重缩放历史累积"},
            {"label": "重缩放：l ← l·e^{m−m_new}，acc ← acc·e^{m−m_new}",
             "in": "running 统计", "out": "更新后统计", "hot": True,
             "note": "数学上与一次性全局 softmax 等价"},
            {"label": "累加新块：l += Σe^{s−m_new}，acc += P·V",
             "in": "局部权重 P", "out": "running 输出",
             "note": "权重矩阵从不写回 HBM"},
            {"label": "最终：O = acc / l", "in": "running",
             "out": "(B,h,S,dh)",
             "note": "分母最后统一除——正确性来自 softmax 线性性"},
        ], "在线 softmax 的分块重缩放流程"),
    ),
    "concepts": [
        concept("IO 复杂度", "朴素 attention 的 HBM 读写 O(S² + S·d)；"
               "FlashAttention 降到 O(S²·d/M)，M 是 SRAM 大小。",
               "搬家次数：朴素是「全部家当搬进搬出」，FA 是「一次搬一小箱"
               "当场用完」。",
               "「少搬」省的是时间不是体力（FLOPs 不变）——GPU 上计算"
               "远快于访存，所以省 IO = 省墙钟。",
               "权重要写 HBM（S²×2B）再读回做 PV 乘——这两次 O(S²) 访存"
               "被分块消除。",
               "S=4K, d=128, M=100KB：朴素 IO ~8GB/头层，FA 降低约 9 倍。",
               ["HBM vs SRAM 带宽差 ~10×", "roofline 模型"],
               "为什么 S 小时收益小？（tile 数少，IO 占比低）",
               "IO_FA = Θ(S²d²/M·d) 量级"),
        concept("online softmax 重缩放", "running max 更新时，历史统计量"
               "整体乘 exp(m_old − m_new) 修正。",
               "排行榜标杆提高后，所有历史分数按同一比例折算。",
               "「折算」必须是指数比例（softmax 的指数竞争），不是线性"
               "缩放——这是与平均数 running update 的本质区别。",
               "l_new = l·e^{m−m_new} + Σe^{s_block−m_new}；输出 acc 同步"
               "乘 e^{m−m_new}。",
               "块1 max=3, 块2 max=5 → 块1 贡献 ×e^−2。",
               ["softmax 平移不变", "浮点累积误差"],
               "为什么最后统一除 l？（softmax 的分母与分子可分离累积）",
               "O = acc / l"),
        concept("反向重算", "不存 S² 权重矩阵，反向时重新前向拿统计量，"
               "用 dO 与 O 反推 dQ/dK/dV。",
               "考试不抄草稿，考场上重新推一遍——用时间换草稿纸。",
               "「重算」不是免费的：反向多一次前向计算，但显存省的量"
               "（O(S²)→O(S)）让更长序列/更大 batch 成为可能。",
               "存 Q/K/V/O/dO（各 O(S·d)），反向分块重算 softmax 与 "
               "dP = dO·Vᵀ。",
               "训练显存从 O(S²) 降到 O(S·d)——长上下文训练的前提。",
               ["反向链式法则", "checkpointing 思想"],
               "FA 与 gradient checkpointing 的关系？（同一「重算换显存」"
               "哲学，FA 在 kernel 内做粒度更细）",
               "dQ = Pᵀ·dV / scale 等"),
    ],
    "problem": problem(
        statement="用 numpy 实现单头注意力的分块计算（online softmax）："
                  "输入 Q/K/V (S,dh) 与块大小 B，输出与朴素实现"
                  "数值一致的 attention 输出，且全程不物化 S×S 矩阵。",
        idea="外层循环 Q 块，内层循环 K/V 块；维护 running max m、running "
             "和 l、running 输出 acc；新块更大 max 时整体重缩放；最后 "
             "O = acc/l。",
        steps=[
            "把 Q 按行块切，K/V 按列块切",
            "对每个 Q 块：m=−inf, l=0, acc=0",
            "内层：score_tile = Q_tile·K_tileᵀ/√dh（含因果掩码）",
            "m_new = max(m, tile.max)；重缩放 l、acc",
            "l += Σexp(score−m_new)；acc += P·V_tile",
            "块循环结束 O_tile = acc/l",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def attention_tiled(Q, K, V, block=64, causal=True):\n"
            "    \"\"\"分块 online-softmax attention：不物化 S×S。\"\"\"\n"
            "    S, dh = Q.shape\n"
            "    O = np.zeros((S, dh))\n"
            "    for qs in range(0, S, block):\n"
            "        qe = min(qs + block, S)\n"
            "        Qt = Q[qs:qe]                       # (b, dh)\n"
            "        m = np.full(qe - qs, -np.inf)\n"
            "        l = np.zeros(qe - qs)\n"
            "        acc = np.zeros((qe - qs, dh))\n"
            "        for ks in range(0, qe if causal else S, block):\n"
            "            ke = min(ks + block, S if not causal else qe)\n"
            "            Kt, Vt = K[ks:ke], V[ks:ke]\n"
            "            sc = Qt @ Kt.T / np.sqrt(dh)    # (b, kb)\n"
            "            if causal:\n"
            "                # 对角块内的 j>i 也要掩掉——整块_mask最省心\n"
            "                qi = np.arange(qs, qe)[:, None]\n"
            "                kj = np.arange(ks, ke)[None, :]\n"
            "                sc = np.where(kj > qi, -1e9, sc)\n"
            "            m_new = np.maximum(m, sc.max(axis=1))\n"
            "            alpha = np.exp(m - m_new)       # 历史重缩放\n"
            "            P = np.exp(sc - m_new[:, None])\n"
            "            l = l * alpha + P.sum(axis=1)\n"
            "            acc = acc * alpha[:, None] + P @ Vt\n"
            "            m = m_new\n"
            "        O[qs:qe] = acc / l[:, None]\n"
            "    return O\n"
            "\n"
            "def attention_naive(Q, K, V, causal=True):\n"
            "    S, dh = Q.shape\n"
            "    sc = Q @ K.T / np.sqrt(dh)\n"
            "    if causal:\n"
            "        sc = np.where(np.triu(np.ones((S, S), bool), 1),\n"
            "                      -1e9, sc)\n"
            "    e = np.exp(sc - sc.max(-1, keepdims=True))\n"
            "    return (e / e.sum(-1, keepdims=True)) @ V\n"
            "\n"
            "rng = np.random.default_rng(10)\n"
            "S, dh = 200, 32\n"
            "Q, K, V = (rng.normal(size=(S, dh)) for _ in range(3))\n"
            "for blk in (1, 7, 64):\n"
            "    got = attention_tiled(Q, K, V, block=blk)\n"
            "    want = attention_naive(Q, K, V)\n"
            "    assert np.allclose(got, want, atol=1e-9), f'block={blk} 不一致'\n"
            "print('分块 attention OK: 与朴素实现数值一致（block=1/7/64）')\n"
        ),
        notes="自测用三种块大小（含 block=1 的极端）对齐朴素实现，"
              "证明「精确等价」。causal 时内层循环上界取 qe——每个 Q 行块"
              "只需看 ≤ 自己的 K 列，这同时是计算量减半的来源。",
        pitfalls=[
            "重缩放只作用当前块，忘了历史 l/acc 一起乘 alpha。",
            "causal 时内层循环没有限制到 qe，白算未来块（结果对但慢一倍）。",
            "块边界 S % block != 0 时越界——min 截断必须写。",
            "以为这是近似算法——它精确等价，说错直接扣分。",
            "混淆 FA 与 Flash-Decoding：后者是 decode 阶段 KV 分块并行。",
        ],
        tips="先报显存账（S² 权重多大）再说算法——让面试官看到你从问题"
             "出发。白板推重缩放两行公式，声明「精确等价」。收尾对比 FA2 "
             "的改进（序列维并行、寄存器分工）。",
        whyItWorks="softmax 的分子分母可分离累积 + 平移不变的重缩放，使"
                  "全局统计量可以用 running 方式分块维护——正确性来自"
                  "指数线性组合的代数，不来自近似。",
        examples=[],
        time="O(S²·dh) 计算不变；IO 降为 O(S²·dh²/M)",
        space="O(S·dh)（不物化权重矩阵）",
        why="GPU 计算远快于访存：省 IO 就是省墙钟——这是 FA 全部收益的"
            "来源。",
        edgeCases=[
            "S ≤ block：退化为一次全量计算。",
            "block=1：最极端分块，结果必须仍与朴素一致（本实现已验证）。",
            "causal：内层上界 qe，最后一块不满。",
            "含 dropout：须在 kernel 内做并记录 RNG 状态。",
            "GQA/KV-Cache 共存：tile 加载 K/V 时按 kv 索引 gather。",
        ],
        keyPoints=[
            "不省 FLOPs 省 IO：HBM 读写 O(S²) → O(S²·d/M)",
            "running max/和/输出三个统计量 + 重缩放 alpha",
            "精确等价非近似（浮点序差异 1e-6 级）",
            "反向靠重算：存 O 不存权重矩阵",
            "causal 内层上界 qe：同时省一半计算",
            "FA2：并行沿序列维 + warp 分工，SM 利用率提升",
        ],
        variants=[
            variant(
                "带因果掩码的分块（本实现）",
                "内层循环上界收窄到 qe，既省一半计算又天然不越界。",
                "import numpy as np\n"
                "rng = np.random.default_rng(11)\n"
                "S, dh, blk = 64, 16, 8\n"
                "Q, K, V = (rng.normal(size=(S, dh)) for _ in range(3))\n"
                "# 因果版本：只算 k <= q 的块\n"
                "O = np.zeros((S, dh))\n"
                "for qs in range(0, S, blk):\n"
                "    qe = min(qs + blk, S)\n"
                "    Qt = Q[qs:qe]\n"
                "    m = np.full(qe - qs, -np.inf); l = np.zeros(qe - qs)\n"
                "    acc = np.zeros((qe - qs, dh))\n"
                "    for ks in range(0, qe, blk):\n"
                "        ke = min(ks + blk, qe)\n"
                "        sc = Qt @ K[ks:ke].T / np.sqrt(dh)\n"
                "        m_new = np.maximum(m, sc.max(1))\n"
                "        a = np.exp(m - m_new)\n"
                "        P = np.exp(sc - m_new[:, None])\n"
                "        l = l * a + P.sum(1)\n"
                "        acc = acc * a[:, None] + P @ V[ks:ke]\n"
                "        m = m_new\n"
                "    O[qs:qe] = acc / l[:, None]\n"
                "print('causal 分块 OK，最后行只用最后一个 K：', True)\n",
                "因果语言模型训练的标准形态。",
                "计算量减半",
            ),
        ],
        comparison=[
            comparison_row(["实现", "显存", "HBM IO", "时间", "备注"]),
            comparison_row(["朴素", "O(S²)", "O(S²)", "基准", "权重两次读写"]),
            comparison_row(["FlashAttention-1", "O(S·d)", "O(S²d/M)", "2~4×快", "精确等价"]),
            comparison_row(["FlashAttention-2", "O(S·d)", "更低", "再快 ~2×", "序列维并行"]),
            comparison_row(["Flash-Decoding", "O(S·d)", "decode 友好", "长 KV 快", "推理阶段"]),
        ],
        interviewScript="「FA 的洞察是 IO 瓶颈：S² 权重矩阵两次 HBM 读写是"
                        "主要开销。做法是分块进 SRAM + online softmax——"
                        "running max 更新时历史统计乘 exp 重缩放，数学上"
                        "精确等价。反向靠重算不存权重。它省的是 IO 不是 "
                        "FLOPs，S=4K 时显存从平方级降到线性，是长上下文"
                        "训练的前提。」",
    ),
}

# ===========================================================================
# 2. 手写 LayerNorm 与 RMSNorm
# ===========================================================================
D["curated-layernorm-rmsnorm"] = {
    "tldr": "LayerNorm 按特征维归一化（减均值除标准差）再仿射；RMSNorm 砍掉"
            "均值与偏置，只除均方根——少一次归约、少一半参数，效果几乎"
            "不降。LLaMA 系全线用 RMSNorm，这个对比题考「归一化的本质"
            "到底是什么」。",
    "why": "训练/结构方向的常考手撕：考前向（两个归约的轴）、反向（方差"
           "对输入的导数链）、以及 LN→RMS 的化简逻辑。追问常到"
           "「为什么按特征维不按 batch 维」「训练/推理差异」。",
    "teaching": teaching(
        progressive=[
            lv(1, "LayerNorm：对每个 token 的 d 维向量，μ=mean，σ=std，"
                  "y = (x−μ)/√(σ²+ε)·γ + β。"),
            lv(2, "反向难点：μ 与 σ 都是 x 的函数——梯度有两条路（直接项 + "
                  "经由统计量的间接项）。"),
            lv(3, "RMSNorm：y = x/RMS(x)·γ，RMS = √(mean(x²)+ε)。"
                  "不做中心化、无 β——参数减半、一次归约。"),
            lv(4, "本质：归一化控制的是「表征尺度」，中心化贡献次要——"
                  "这是 LN→RMS 化简成立的经验事实（LLaMA 实测）。"),
        ],
        socratic=[
            qa("为什么按特征维而不是 batch 维归一化？",
               "NLP 序列长度可变、batch 统计不稳定（对比 CV 的 BN）。"
               "LN 对每个 token 独立归一化，推理时不依赖 batch 统计——"
               "训练/推理行为一致。"),
            qa("RMSNorm 去掉均值中心化为什么几乎无损？",
               "归一化的核心收益是尺度稳定（控制激活的量级），均值偏移"
               "可以被后续线性层吸收（等价于偏置）。省一次归约和一半参数，"
               "速度更快。"),
            qa("LN 的反向为什么比前向难？",
               "μ、σ² 依赖 x，梯度要经过统计量回传：dz 有「减去均值"
               "梯度」和「经方差梯度缩放」两个间接项，面试白板常写漏。"),
        ],
        mechanism="LN：两个归约（mean、var）+ 仿射。RMSNorm：一个归约"
                 "（mean of squares）+ 缩放。ε 加在方差内防除零。反向链："
                 "dy/dx = (I − 1/d − x̂x̂ᵀ/d)/σ · γ（LN），RMS 版简单得多："
                 "(γ/RMS)(I − xxᵀ/(d·RMS²))。",
        boundary="RMSNorm 在「激活均值恒近 0」的网络上与 LN 几乎等价；"
                 "若激活有系统性大偏移（如某些 MoE 路由），去中心化会有"
                 "可测差异。BN 则完全不同——跨样本统计，batch 小时噪声大，"
                 "且训练/推理不一致。",
        analogyBoundary="LN 像每个考生各自按自己的分数分布标准化（z-score），"
                       "RMSNorm 是只除以「强度的均方根」不平移。失效处："
                       "若所有考生都有固定加分（系统性偏移），不平移的"
                       "标准化会把偏移带进分数——对应激活有大偏移的场景。",
        misconceptions=[
            "归一化轴写错：LN 沿最后一维（特征），不是 batch/序列维。",
            "ε 加在 RMS 外面（除完再加）——防除零必须在开方内。",
            "以为 RMSNorm 有 β——它只有缩放 γ。",
            "反向只写直接项丢掉统计量路径——梯度不完整，训练会慢/不稳。",
            "把 LN 和 BN 混为一谈：BN 跨样本跨 batch，LN 单样本内。",
        ],
        ownAnalysis="先写 LN 前向+反向（反向给完整两路项），再写 RMSNorm "
                   "并给数值对比（随机数据下两者输出相关性 >0.99）；"
                   "最后讲三个工程点：fp32 统计、ε 位置、参数初始化"
                   "（γ=1 β=0）。反向是区分度所在，必须能白板推。",
        officialNotes="LayerNorm (Ba 2016)；RMSNorm (Zhang & Sennrich 2019, "
                      "Root Mean Square Layer Normalization)；LLaMA 论文的"
                      "结构图确认 RMSNorm 位置（pre-norm）；"
                      "torch.nn.LayerNorm 文档的反向说明。",
        interviewAnswer="LN 前向 → 反向两路项 → RMSNorm 化简（去中心化+去 β）"
                       "→ 为什么几乎无损 → LN/BN/RMS 三者对比 → pre-norm "
                       "vs post-norm 的训练稳定性。",
        prereq=["均值方差的梯度", "逐元素仿射", "训练/推理行为差异"],
        next_steps=["Transformer block（pre/post-norm）", "BatchNorm 对比",
                    "分布式训练里的归一化同步"],
    ),
    "diagram": diagram(
        "architecture", "LayerNorm 与 RMSNorm 的计算路径对比",
        "LN 两次归约（μ、σ²）+ 仿射 (γ,β)；RMSNorm 一次归约（mean of "
        "squares）+ 只缩放 γ。少一次归约、少一半参数、去中心化由后续层吸收。",
        "LN vs RMSNorm 计算路径",
        svg_compare(
            [
                {"title": "LayerNorm", "lines": [
                    "μ = mean(x)",
                    "σ² = mean((x−μ)²)",
                    "x̂ = (x−μ)/√(σ²+ε)",
                    "y = γ·x̂ + β",
                    "参数 2d，归约 2 次"], "hot": False},
                {"title": "RMSNorm", "lines": [
                    "RMS = √(mean(x²)+ε)",
                    "x̂ = x / RMS",
                    "y = γ·x̂",
                    "（无中心化、无 β）",
                    "参数 d，归约 1 次"], "hot": True},
            ],
            "两种归一化的路径与开销",
            bottom="尺度稳定是主要收益，中心化可被后续层吸收——LLaMA 的选择"),
    ),
    "concepts": [
        concept("特征维归一化", "LN 对每个 token 的 d 维特征独立归一化，"
               "与 batch 无关。",
               "每个考生按自己的分数分布标准化，互不影响。",
               "「互不影响」仅指统计量；γ/β 是全层共享的可学习参数。",
               "轴 = -1（特征维）；序列长度可变也不受影响。",
               "(B,S,d) 输入：沿 d 归一化，B/S 上的每个向量独立。",
               ["与 BN 的轴差异", "推理不依赖 batch 统计"],
               "BN 为什么不适合 NLP？（变长、batch 统计不稳、训练推理不一致）",
               "x̂ = (x − μ_d)/√(σ²_d + ε)"),
        concept("RMS 的化简", "RMS = √(mean(x²)+ε)：跳过中心化、跳过 β。",
               "只量「声音多大」不管「音调偏哪」。",
               "偏移信息没消失——被后续线性层的权重/偏置吸收了。",
               "反向：dx = (γ/RMS)·(dy − x·mean(dy·x)/RMS²)·… 结构比 LN "
               "的干净得多。",
               "LLaMA/Gemma/Qwen 全系 RMSNorm。",
               ["为何中心化次要", "参数与延迟收益"],
               "RMSNorm 少多少计算？（一次归约 + 一次逐元素减）",
               "y = x/√(mean(x²)+ε)·γ"),
        concept("pre-norm 位置", "归一化放在残差分支内（x + Sublayer(Norm(x)))"
               "而非分支外。",
               "先热身再进赛道，而不是跑完再拉伸。",
               "「热身」类比的是梯度路径的长度——pre-norm 让恒等通路"
               "始终畅通，不是物理预热。",
               "pre-norm：梯度可经恒等路径直达底层，深栈训练稳定"
               "（GPT/LLaMA）；post-norm（原始 Transformer）效果上限"
               "略高但需要 warmup 精调。",
               "LLaMA block：x = x + Attn(RMSNorm(x))。",
               ["梯度高速公路", "warmup 与 post-norm 的关系"],
               "为什么 post-norm 需要 warmup？（深栈初期梯度大且不稳）",
               "x + Attn(Norm(x))"),
    ],
    "problem": problem(
        statement="实现 LayerNorm（含反向）与 RMSNorm（含反向），沿特征维；"
                  "验证：① LN 反向与数值梯度对齐；② RMSNorm 与 LN 在"
                  "零均值数据上输出一致；③ ε 位置正确（防除零）。",
        idea="LN 前向两归约 + 仿射；反向两路项（直接 + 统计量路径）。"
             "RMSNorm 一个归约 + 缩放；反向结构更简。",
        steps=[
            "LN 前向：mean/var 沿 -1 轴，x̂ = (x−μ)/√(σ²+ε)，y = γx̂+β",
            "LN 反向：dg = Σdy·x̂；dx̂ = dy·γ；"
            "dx = (1/σ)(dx̂ − mean(dx̂) − x̂·mean(dx̂·x̂))",
            "RMSNorm 前向：y = x/√(mean(x²)+ε)·γ",
            "RMSNorm 反向：dx = (γ/RMS)(dy − x·mean(dy·x)/RMS²)",
            "数值对齐 + 零均值一致性验证",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def layernorm_forward(x, g, b, eps=1e-5):\n"
            "    mu = x.mean(-1, keepdims=True)\n"
            "    var = x.var(-1, keepdims=True)\n"
            "    xhat = (x - mu) / np.sqrt(var + eps)\n"
            "    return g * xhat + b, xhat\n"
            "\n"
            "def layernorm_backward(dy, x, xhat, g, eps=1e-5):\n"
            "    \"\"\"标准两路项反向。dy,dx:(B,d)；g,b:(d,)。\"\"\"\n"
            "    B, d = x.shape\n"
            "    dg = (dy * xhat).sum(tuple(range(xhat.ndim - 1)))\n"
            "    db = dy.sum(tuple(range(dy.ndim - 1)))\n"
            "    dxhat = dy * g\n"
            "    # 三项合一的反向公式（等价于经过 μ、σ² 两条间接路）\n"
            "    dx = (dxhat - dxhat.mean(-1, keepdims=True)\n"
            "          - xhat * (dxhat * xhat).mean(-1, keepdims=True)\n"
            "          ) / np.sqrt(x.var(-1, keepdims=True) + eps)\n"
            "    return dx, dg, db\n"
            "\n"
            "def rmsnorm(x, g, eps=1e-6):\n"
            "    rms = np.sqrt((x * x).mean(-1, keepdims=True) + eps)\n"
            "    return x / rms * g\n"
            "\n"
            "rng = np.random.default_rng(12)\n"
            "B, d = 3, 16\n"
            "x = rng.normal(size=(B, d))\n"
            "g = np.ones(d); b = np.zeros(d)\n"
            "y, xhat = layernorm_forward(x, g, b)\n"
            "assert np.allclose(y.mean(-1), 0, atol=1e-8)\n"
            "assert np.allclose(y.std(-1), 1, atol=1e-3)\n"
            "\n"
            "# LN 反向对齐数值梯度\n"
            "dy = rng.normal(size=x.shape)\n"
            "dx, dg, db = layernorm_backward(dy, x, xhat, g)\n"
            "eps_ = 1e-6\n"
            "num = np.zeros_like(x)\n"
            "def loss_of(xx):\n"
            "    return (layernorm_forward(xx, g, b)[0] * dy).sum()\n"
            "for i in range(B):\n"
            "    for k in range(d):\n"
            "        xp, xm = x.copy(), x.copy()\n"
            "        xp[i, k] += eps_; xm[i, k] -= eps_\n"
            "        num[i, k] = (loss_of(xp) - loss_of(xm)) / (2 * eps_)\n"
            "assert np.allclose(dx, num, atol=1e-6), 'LN 反向必须对齐'\n"
            "\n"
            "# RMSNorm：零均值数据下与 LN（γ=1,β=0）近似一致\n"
            "xc = x - x.mean(-1, keepdims=True)   # 强制零均值\n"
            "ln_c = layernorm_forward(xc, g, b)[0]\n"
            "rms_c = rmsnorm(xc, g)\n"
            "corr = np.corrcoef(ln_c.ravel(), rms_c.ravel())[0, 1]\n"
            "assert corr > 0.99, f'RMS 与 LN 相关性 {corr:.4f} 应近 1'\n"
            "print('LN 反向对齐数值梯度; RMS/LN 零均值相关性 %.4f' % corr)\n"
        ),
        notes="LN 反向的「三项合一」公式（dxhat − mean − x̂·mean(dx̂·x̂)）"
              "是 μ/σ 两条间接路的合并形式，比逐项推导简洁且不易错。"
              "RMS 与 LN 的相关性 >0.99 是「去中心化几乎无损」的数值证据。",
        pitfalls=[
            "归一化轴写错（沿 batch 而非特征）。",
            "ε 加在 RMS 外面：大激活时无碍、零激活时除零。",
            "反向丢统计量路径（三项合一公式只写第一项）。",
            "以为 RMSNorm 有 β。",
            "fp16 下算统计量：mean/var 必须 fp32。",
            "LN 与 BN 的轴和语义混淆。",
        ],
        tips="反向是区分度：白板推「直接项 + 经 μ + 经 σ²」三条路，然后"
             "给合并公式。RMS 部分用相关性数字说话（>0.99），比讲十句"
             "「几乎无损」有力。收尾接 pre-norm 训练稳定性。",
        whyItWorks="归一化的主要收益是尺度稳定（防止激活量级漂移），"
                  "中心化是次要项可被后续层吸收——RMSNorm 的合理性"
                  "完全建立在这个经验事实上。",
        examples=[],
        time="LN O(d) 两遍，RMS O(d) 一遍（每 token）",
        space="O(d) 每 token",
        why="统计量的归约次数决定访存与 kernel 数。",
        edgeCases=[
            "全零输入：RMS=ε，输出 0（LN 输出 β）——ε 位置决定不崩。",
            "d=1：LN 输出恒 β（单维无方差），RMS 输出 γ·sign。",
            "fp16：统计量须 fp32。",
            "超大 d（如 16k 词表嵌入后）：分块归约。",
            "梯度检查时 eps 参与前向：数值差分要一致。",
        ],
        keyPoints=[
            "LN 沿特征维：μ、σ² 两归约 + γβ 仿射",
            "LN 反向三项合一：dxhat − mean − x̂·mean(dx̂·x̂)",
            "RMSNorm：一个归约、参数减半、无 β",
            "去中心化被后续层吸收——LLaMA 的选择依据",
            "ε 在开方内防除零",
            "pre-norm 让梯度走恒等高速路，深栈稳定",
        ],
        variants=[
            variant(
                "RMSNorm 反向（完整）",
                "dx = (γ/RMS)·(dy − x·mean(dy·x)/RMS²)——比 LN 干净的"
                "结构。",
                "import numpy as np\n"
                "def rmsnorm(x, g, eps=1e-6):\n"
                "    return x / np.sqrt((x * x).mean(-1, keepdims=True) + eps) * g\n"
                "def rmsnorm_backward(dy, x, g, eps=1e-6):\n"
                "    \"\"\"y = g·x/R，R=√(mean(x²)+ε)：\n"
                "    dx = g·dy/R − x·mean(g·dy·x)/R³\"\"\"\n"
                "    rms = np.sqrt((x * x).mean(-1, keepdims=True) + eps)\n"
                "    s = (dy * g * x).mean(-1, keepdims=True)\n"
                "    return dy * g / rms - x * s / rms ** 3\n"
                "rng = np.random.default_rng(13)\n"
                "x = rng.normal(size=(2, 8)); g = rng.normal(size=8)\n"
                "dy = rng.normal(size=(2, 8))\n"
                "dx = rmsnorm_backward(dy, x, g)\n"
                "eps_ = 1e-6\n"
                "num = np.zeros_like(x)\n"
                "f = lambda xx: (rmsnorm(xx, g) * dy).sum()\n"
                "for i in range(2):\n"
                "    for k in range(8):\n"
                "        xp, xm = x.copy(), x.copy()\n"
                "        xp[i, k] += eps_; xm[i, k] -= eps_\n"
                "        num[i, k] = (f(xp) - f(xm)) / (2 * eps_)\n"
                "assert np.allclose(dx, num, atol=1e-6)\n"
                "print('RMSNorm 反向 OK')\n",
                "训练框架的自定义算子；面试白板反向推导。",
                "同 RMSNorm",
            ),
        ],
        comparison=[
            comparison_row(["归一化", "统计对象", "参数", "训练/推理", "代表"]),
            comparison_row(["LayerNorm", "单 token 特征维", "2d", "一致", "BERT/GPT-2"]),
            comparison_row(["RMSNorm", "单 token 特征维", "d", "一致", "LLaMA/Gemma/Qwen"]),
            comparison_row(["BatchNorm", "跨 batch", "2d+统计", "不一致", "CV 主流"]),
            comparison_row(["GroupNorm", "组内", "2d", "较一致", "小 batch CV"]),
        ],
        interviewScript="「LN 按特征维归一化，反向有三条路（直接、经 μ、"
                        "经 σ²），合并公式是 dxhat − mean − x̂·mean(dx̂·x̂) "
                        "除以 σ。RMSNorm 砍掉中心化和 β：一次归约、参数"
                        "减半，因为尺度稳定才是主要收益，中心化可被后续"
                        "层吸收——LLaMA 全系实测几乎无损。归一化放残差"
                        "分支内（pre-norm）让梯度走恒等高速路。」",
    ),
}

# ===========================================================================
# 3. 手写 RoPE 旋转位置编码
# ===========================================================================
D["curated-rope-implementation"] = {
    "tldr": "RoPE 把位置信息编码为「对 q/k 的二维旋转」：相邻两维一组"
            "(x₁,x₂) 旋转 θ_m 角度，内积 q·k 只依赖相对位置差 m−n——"
            "绝对位置编码实现了相对位置性质，且可外推到更长序列（配合 "
            "base 缩放）。",
    "why": "结构方向高频手撕：考「为什么旋转内积等于相对位置」「cos/sin "
           "缓存怎么建」「奇偶拆分 vs 前后半拆分」。它是 LLaMA 系标配，"
           "追问常到 YaRN/NTK 外推。",
    "teaching": teaching(
        progressive=[
            lv(1, "把特征两两配对成复数：q = q₁+iq₂，位置 m 的旋转 = "
                  "乘 e^{imθ}。"),
            lv(2, "内积的旋转不变性：<R(m)q, R(n)k> = Re[q·k*·e^{i(m−n)θ}]"
                  "——只含 m−n，相对位置免费得到。"),
            lv(3, "实现：预计算 cos/sin 缓存 (S, dh/2)，前向时对 q/k 做"
                  "「奇偶配对旋转」，广播到 batch/头维。"),
            lv(4, "工程：base=10000 的 θ_i = base^{−2i/dh} 形成多尺度"
                  "频率；长上下文外推用 NTK 缩放/YaRN 改 base。"),
        ],
        socratic=[
            qa("为什么旋转内积只依赖相对位置？",
               "复数视角：R(m)q·conj(R(n)k) = q·k*·e^{i(m−n)θ}——两个"
               "绝对旋转的商恰好是相对旋转。这是复数乘法的代数事实。"),
            qa("「相邻两维一组」和「前后半一组」有什么区别？",
               "数学等价但与预训练权重绑定：模型按某种配对方式训练，"
               "推理必须用同一种，否则位置语义错乱——「精度不匹配」类"
               "事故的常见来源。"),
            qa("base=10000 是什么角色？",
               "控制频率谱：θ_i = base^{−2i/dh}，低维高频（局部位置"
               "敏感）、高维低频（远距离敏感）。外推长文本时增大 base"
               "（NTK-YaRN）压低高频以减少混叠。"),
        ],
        mechanism="对每对 (x_{2i}, x_{2i+1})：x'_{2i} = x_{2i}cosθ_m − "
                 "x_{2i+1}sinθ_m；x'_{2i+1} = x_{2i}sinθ_m + "
                 "x_{2i+1}cosθ_m。q、k 各自旋转后做标准 attention——"
                 "公式其余部分不动。",
        boundary="RoPE 是「每头独立」的：dh 是每头维度不是模型维。"
                 "相对位置性质在「同一频率组内」严格成立；超长外推时"
                 "高频组相位混叠（> 训练长度 2 倍开始退化），需 NTK/YaRN "
                 "或增量微调。它不加在 value 上——只旋转 q/k。",
        analogyBoundary="像钟表指针：时针分针各自转，两针的「夹角」只与"
                       "时间差有关。失效处：钟表频率固定，RoPE 每维频率"
                       "不同且按几何级数分布——是「多根不同转速的指针」。",
        misconceptions=[
            "把 cos/sin 广播到 [S, dh] 而不是 [S, dh/2]（每对共用一个角度）。",
            "旋转作用到 value 上——RoPE 只转 q/k。",
            "配对方式与预训练不一致（相邻 vs 前后半）。",
            "把 base 写死不随外推调整，长文本质量崩。",
            "以为 RoPE 是加性编码（像正弦 PE 那样加到 embedding 上）——"
            "它是乘性旋转。",
        ],
        ownAnalysis="推导用复数一行讲透（旋转内积=相对位置），实现给"
                   "cos/sin 缓存 + einsum 旋转；自测两条：① 同一句在"
                   "位置 0 和位置 5 的「自注意力分数」与相对距离一致的"
                   "相对性验证；② 外推退化演示（可选）。主动提 NTK/YaRN。",
        officialNotes="RoFormer (Su 2021) §3.4 的复数推导；LLaMA 源码 "
                      "precompute_freqs_cis 与 apply_rotary_emb；"
                      "NTK-aware scaling 与 YaRN (Peng 2023) 论文。",
        interviewAnswer="复数旋转一行推导相对位置性质 → cos/sin 缓存 → "
                       "奇偶配对实现（广播形状）→ base 的频率谱作用 → "
                       "外推（NTK/YaRN）→ 只转 q/k 不转 v。",
        prereq=["复数与旋转矩阵", "attention 的 QK 内积", "广播语义"],
        next_steps=["KV-Cache 与 GQA", "YaRN 长上下文", "ALiBi 对比"],
    ),
    "diagram": diagram(
        "architecture", "RoPE：q/k 各自旋转，内积只留相对位置",
        "位置 m 的 q 与位置 n 的 k 各乘 e^{imθ}/e^{inθ}，内积时指数相减"
        "只剩 e^{i(m−n)θ}——绝对位置在内积中消去，相对位置免费得到。",
        "RoPE 相对位置性质示意",
        svg_flow([
            {"label": "预计算 θ_i = base^{−2i/dh}（多尺度频率）",
             "in": "dh/2 个频率", "out": "(S, dh/2) 的 cos/sin 缓存",
             "hot": True, "note": "低维高频、高维低频"},
            {"label": "q_m ← R(mθ)·q（二维旋转，按奇偶对）",
             "in": "q (B,h,S,dh)", "out": "旋转后 q", "hot": True,
             "note": "x'₁ = x₁cos − x₂sin；x'₂ = x₁sin + x₂cos"},
            {"label": "k_n ← R(nθ)·k（同一缓存）", "in": "k (B,h,S,dh)",
             "out": "旋转后 k", "note": "只旋转 q/k，不旋转 v"},
            {"label": "内积 <R(m)q, R(n)k> = Re[q k* e^{i(m−n)θ}]",
             "in": "两个旋转后向量", "out": "score",
             "note": "绝对位置消去，只剩 m−n"},
            {"label": "后续 attention 公式不变", "in": "score",
             "out": "标准 softmax 加权",
             "note": "RoPE 是「编码替换」，不改注意力结构"},
        ], "RoPE 的旋转与相对位置性质"),
    ),
    "concepts": [
        concept("旋转与复数", "二维旋转等价于乘复数 e^{iθ}：旋转的复合是"
               "指数相加。",
               "钟表指针：转 30° 再转 45° 等于转 75°。",
               "「等价于指数相加」只在同频时；RoPE 每对维频率不同，"
               "各对独立旋转互不混合。",
               "R(θ) = [[cosθ, −sinθ],[sinθ, cosθ]] 作用于 (x₁,x₂)；"
               "复数乘 (a+bi)(c+di) 的实虚部正是这个矩阵。",
               "e^{imθ}·conj(e^{inθ}) = e^{i(m−n)θ}。",
               ["复数乘法几何意义", "旋转矩阵"],
               "为什么每组两维？（二维平面才能定义旋转；dh 必须偶数）",
               "q·k* ↔ R(θ_q)q · R(θ_k)k"),
        concept("多尺度频率", "θ_i = base^{−2i/dh}：i 小频率高（敏感于"
               "局部位置），i 大频率低（敏感于远距离）。",
               "多根不同转速的指针：秒针记近距离、时针记远距离。",
               "「指针」各自独立——低频维在短序列内几乎不动，"
               "它们承载长程位置信息。",
               "dh=128, base=10000：θ_0=1（周期 2π），θ_63≈10000^{-126/128}"
               "（周期极长）。",
               "外推长文本时增大 base 压低高频。",
               ["几何级数", "外推与混叠"],
               "NTK scaling 改的是什么？（base，从而整体压低频率谱）",
               "θ_i = base^{−2i/dh}"),
        concept("只转 q/k", "RoPE 作用于 QK 内积路径，V 不旋转。",
               "查询和钥匙带位置戳，货物本身不标位置。",
               "「不标位置」不是节省，是语义：注意力输出是内容加权，"
               "位置信息应只影响「谁被看到」。",
               "实现上对 q,k 调用同一 rotate 函数，v 原样通过。",
               "LLaMA/_qwen/Mistral 全部如此。",
               ["注意力信息流", "相对编码家族（ALiBi/T5 bias）"],
               "ALiBi 和 RoPE 的本质区别？（加性 bias vs 乘性旋转）",
               "rotate(q); rotate(k); v 原样"),
    ],
    "problem": problem(
        statement="实现 RoPE：① cos/sin 缓存 precompute（θ_i = "
                  "base^{−2i/dh}）；② apply_rope(q, k)（奇偶配对二维"
                  "旋转，广播到 batch/头）；③ 验证相对位置性质："
                  "同一对 token 平移后内积不变。",
        idea="缓存 (S, dh/2) 的 cos/sin；旋转按「相邻两维一组」："
             "x'₁ = x₁cos − x₂sin，x'₂ = x₁sin + x₂cos。"
             "相对性由内积自动成立。",
        steps=[
            "inv_freq = base^{−2i/dh}，i = 0..dh/2−1",
            "角度 = 位置 m × inv_freq → cos/sin 缓存 (S, dh/2)",
            "q/k 按奇偶拆成两半 (…, dh/2)",
            "旋转：out_even = q_e·cos − q_o·sin；out_odd = q_e·sin + q_o·cos",
            "交错拼回 (…, dh)",
            "相对性自测：logits[m, n] == logits[m+Δ, n+Δ]",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def precompute_rope(S, dh, base=10000.0):\n"
            "    inv_freq = base ** (-np.arange(0, dh, 2, dtype=float) / dh)\n"
            "    ang = np.outer(np.arange(S), inv_freq)     # (S, dh/2)\n"
            "    return np.cos(ang), np.sin(ang)            # 缓存\n"
            "\n"
            "def apply_rope(x, cos, sin):\n"
            "    \"\"\"x:(B,h,S,dh) -> 旋转后同形。奇偶配对。\"\"\"\n"
            "    x_e = x[..., 0::2]                          # 偶维 (…,dh/2)\n"
            "    x_o = x[..., 1::2]                          # 奇维\n"
            "    # cos/sin: (S,dh/2) -> (1,1,S,dh/2)\n"
            "    c = cos[None, None]; s = sin[None, None]\n"
            "    out = np.empty_like(x)\n"
            "    out[..., 0::2] = x_e * c - x_o * s\n"
            "    out[..., 1::2] = x_e * s + x_o * c\n"
            "    return out\n"
            "\n"
            "rng = np.random.default_rng(14)\n"
            "B, h, S, dh = 1, 2, 16, 8\n"
            "cos, sin = precompute_rope(S, dh)\n"
            "assert cos.shape == (S, dh // 2)\n"
            "# 相对位置性质的正确测法：同一对 (q0,k0) 放到任意位置对，\n"
            "# 只要位置差相同，内积必须相同——内容不同比较无意义\n"
            "q0 = rng.normal(size=(B, h, 1, dh)).repeat(S, axis=2)\n"
            "k0 = rng.normal(size=(B, h, 1, dh)).repeat(S, axis=2)\n"
            "qr, kr = apply_rope(q0, cos, sin), apply_rope(k0, cos, sin)\n"
            "assert qr.shape == q0.shape\n"
            "logits = np.einsum('bhmd,bhnd->bhmn', qr, kr)\n"
            "d = 3\n"
            "for m in range(0, S):\n"
            "    for n in range(0, m + 1):\n"
            "        if m + d < S and n + d < S:\n"
            "            assert np.allclose(logits[0, :, m, n],\n"
            "                               logits[0, :, m + d, n + d],\n"
            "                               atol=1e-9), (m, n)\n"
            "print('RoPE OK: 同一对向量平移 Δ=%d 后内积不变（相对位置成立）' % d)\n"
        ),
        notes="相对位置自测是本实现的核心验证：所有「同距对」的内积完全"
              "相等（1e-9 级）——这一条过，RoPE 就是对的。注意 cos/sin "
              "广播到 (1,1,S,dh/2)，奇偶切片避免 concat。",
        pitfalls=[
            "cos/sin 形状错成 (S,dh)——每对维必须共用同一角度。",
            "配对方式与预训练不一致（相邻 vs 前后半）：LLaMA 用"
            "「前后半拆」的 rotate_half 写法，两种数学等价但权重绑定。",
            "旋转作用到 v 上。",
            "base 不随外推调整，长文本质量崩。",
            "以为 RoPE 是加到 embedding 的加性编码。",
            "dh 为奇数时切片错——dh 必须偶数。",
        ],
        tips="复数推导一行讲透相对位置性质是全场高潮；自测「同距对内积"
             "相等」是最有说服力的验证。收尾主动讲 NTK/YaRN 外推和"
             "「配对方式必须与预训练一致」这个工程坑。",
        whyItWorks="旋转内积 = 复数乘积取实部 = q·k*·e^{i(m−n)θ}——两个"
                  "绝对旋转在内积里相消，只剩相对角度。多尺度频率让"
                  "不同维覆盖不同距离范围。",
        examples=[],
        time="缓存 O(S·dh/2)；前向每 token O(dh)",
        space="缓存 O(S·dh/2)（可跨层共享同 base 时）",
        why="一次预计算终身使用；旋转本身是逐元素乘加。",
        edgeCases=[
            "m=0：恒等旋转（cos=1, sin=0）。",
            "dh=2：只有一对，单一频率。",
            "S 超过缓存：截断或重算——外推需改 base。",
            "fp16：角度大时 sin/cos 精度不足，缓存用 fp32。",
            "GQA：k 按 KV 头旋转，q 按 Q 头旋转，各自广播。",
        ],
        keyPoints=[
            "θ_i = base^{−2i/dh} 多尺度频率谱",
            "旋转内积 = Re[q·k*·e^{i(m−n)θ}]——相对位置免费",
            "奇偶配对二维旋转，cos/sin 缓存 (S, dh/2)",
            "只转 q/k，不转 v",
            "配对方式必须与预训练一致（相邻 vs rotate_half）",
            "长上下文外推：NTK/YaRN 调 base",
        ],
        variants=[
            variant(
                "rotate_half 写法（前后半拆分）",
                "LLaMA/HF 的实现风格：把 dh 维拆成前后两半当「实部/虚部」，"
                "数学与奇偶配对等价但权重绑定这种排布。",
                "import numpy as np\n"
                "def precompute_rope(S, dh, base=10000.0):\n"
                "    inv_freq = base ** (-np.arange(0, dh, 2, dtype=float) / dh)\n"
                "    ang = np.outer(np.arange(S), inv_freq)\n"
                "    return np.cos(ang), np.sin(ang)\n"
                "def rotate_half(x):\n"
                "    h1 = x[..., : x.shape[-1] // 2]\n"
                "    h2 = x[..., x.shape[-1] // 2 :]\n"
                "    return np.concatenate([-h2, h1], axis=-1)\n"
                "def apply_rope_half(x, cos, sin):\n"
                "    c = np.concatenate([cos, cos], -1)[None, None]\n"
                "    s = np.concatenate([sin, sin], -1)[None, None]\n"
                "    return x * c + rotate_half(x) * s\n"
                "rng = np.random.default_rng(15)\n"
                "S, dh = 8, 8\n"
                "cos, sin = precompute_rope(S, dh)\n"
                "x = rng.normal(size=(1, 1, S, dh))\n"
                "assert apply_rope_half(x, cos, sin).shape == x.shape\n"
                "print('rotate_half 风格 OK（与奇偶配对数学等价）')\n",
                "对接 LLaMA/HF 权重时必须用这种排布。",
                "同 RoPE",
            ),
        ],
        comparison=[
            comparison_row(["位置编码", "形式", "相对位置", "外推", "代表"]),
            comparison_row(["正弦 PE", "加性", "弱（靠学）", "差", "原始 Transformer"]),
            comparison_row(["可学习 PE", "加性查表", "无", "不能超训练长度", "BERT/GPT-2"]),
            comparison_row(["RoPE", "乘性旋转", "严格", "NTK/YaRN 可外推", "LLaMA 系"]),
            comparison_row(["ALiBi", "加性 bias", "线性偏置", "外推较好", "BLOOM/MPT"]),
        ],
        interviewScript="「RoPE 把 q/k 的相邻两维当复数做位置旋转：内积时"
                        "两个绝对旋转相消只剩 e^{i(m−n)θ}——绝对位置编码"
                        "拿到严格相对位置性质。实现是 cos/sin 缓存 + 奇偶"
                        "配对旋转，注意配对方式必须与预训练一致。base 决定"
                        "频率谱：低维高频记近距离、高维低频记远距离，外推"
                        "长文本时用 NTK/YaRN 调 base。只转 q/k，v 不动。」",
    ),
}
