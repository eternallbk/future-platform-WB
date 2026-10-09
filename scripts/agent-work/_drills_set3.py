# -*- coding: utf-8 -*-
"""_drills_set3.py — 模型手撕深度解析 · 数值与解码（3 题）。"""

from _drills_helpers import (
    diagram, teaching, lv, qa, concept, variant, comparison_row,
    problem, svg_flow, svg_compare,
)

D = {}

# ===========================================================================
# 1. 数值稳定的 Softmax 与 Log-Softmax
# ===========================================================================
D["curated-softmax-stable"] = {
    "tldr": "softmax(x) = exp(x−max)/Σexp(x−max)：减 max 不改结果（平移"
            "不变），却把指数压进安全区。log-softmax 用 logsumexp 一步算出，"
            "绝不先 softmax 再 log——它是交叉熵/对比学习/注意力全部的地基。",
    "why": "看似简单，实为面试官的工程素养探针：max-shift 会不会写、为什么、"
           "log 版怎么不下溢、梯度是什么。它是所有 downstream 损失的地基。",
    "teaching": teaching(
        progressive=[
            lv(1, "朴素版 exp(x)/Σexp(x)：x>700 时上溢为 inf。"),
            lv(2, "减 max：分子分母同乘 e^−max 抵消，指数输入 ≤ 0，永不上溢。"),
            lv(3, "log 版：log_softmax = x − max − log(Σexp(x−max))，"
                  "一步算出，绝不分两步。"),
            lv(4, "梯度：J = diag(p) − ppᵀ，行和为 0；反传向量式 "
                  "p⊙(g − Σp·g)，O(n) 无需 n×n 矩阵。"),
        ],
        socratic=[
            qa("减 max 为什么不改变结果？",
               "softmax 平移不变：softmax(x+c) 分子分母同乘 e^c 约掉。"
               "取 c=−max 纯为让 exp 参数 ≤ 0，免费的数值保险。"),
            qa("为什么不能 log(softmax(x))？",
               "x−max 很负时 softmax 下溢为 0，log(0)=−inf。logsumexp 一次"
               "算出：lse = max + log(Σexp(x−max))，全程无下溢路径。"),
            qa("梯度为什么是 s_i(δ_ij − s_j)？",
               "增加 i 的概率必须从别处等比抽走——总概率守恒使雅可比行和"
               "为 0，这是反向传播数值健康的关键结构。"),
        ],
        mechanism="softmax 把实向量映到概率单纯形；平移不变性给免费 "
                 "max-shift；logsumexp 一次性解决 log-exp 循环的上下溢；"
                 "雅可比行和为 0 使反传可用「p⊙(g−p·g)」完成。",
        boundary="max-shift 解决上溢不解决「全下溢」：x−max 全 −1000 时 exp "
                 "全 0——真实场景罕见（max 自身 exp=1）。fp16 限更低，"
                 "混合精度里 softmax 必须 fp32 内算或用 fused kernel。",
        analogyBoundary="评比后按最高分归一：全队先减最高分再按比例换算，"
                       "名次不变。失效处：softmax 的比例是指数比例——"
                       "差 1 分概率比是 e 倍，比线性归一敏感得多（温度由此来）。",
        misconceptions=[
            "以为减 max 改变分布——它只改中间量，数学严格不变。",
            "log_softmax = log(softmax(x))：下溢直接 −inf/NaN。",
            "softmax 沿错轴——batch 实现里轴错位是高频 bug。",
            "以为 fp16 减 max 就万事大吉——真正问题在累加精度，须 fp32。",
            "梯度推导丢掉行和为 0 结构，写出 n² 矩阵还声称高效。",
        ],
        ownAnalysis="当场用 1e4 量级输入对比朴素版 inf 与稳定版正常；"
                   "log_softmax 用 logsumexp；最后给雅可比并说明温度 τ "
                   "只是 x/τ 缩放——把 softmax 讲成「指数竞争强度调节器」，"
                   "衔接蒸馏与对比学习。",
        officialNotes="Goodfellow §6.2.2（max-shift 与 logsumexp）；CS231n "
                      "softmax 梯度推导；scipy.special.logsumexp 文档。",
        interviewAnswer="平移不变 → max-shift 实现 → logsumexp 的 log 版；"
                       "补雅可比行和为 0 与 fp32 纪律；温度参数接蒸馏/对比"
                       "学习。",
        prereq=["指数对数", "概率归一化", "链式法则"],
        next_steps=["交叉熵与反向传播", "KL 散度", "温度与蒸馏"],
    ),
    "diagram": diagram(
        "curve", "max-shift 把 exp 输入整体压进安全区",
        "logits [1000,1001,999] 直接 exp 上溢；减 max=1001 后指数参数变为"
        "[−1,0,−2]，最大项 exp(0)=1，永不溢出——概率完全不变。",
        "softmax 数值稳定的 max-shift 图示",
        svg_flow([
            {"label": "原始 logits [1000, 1001, 999]", "in": "float64",
             "out": "exp 上溢 → inf", "hot": True,
             "note": "exp(1000) ≈ 1.97e434，远超 1.8e308"},
            {"label": "减 max：x − 1001", "in": "[-1, 0, -2]",
             "out": "exp ∈ (0, 1]", "note": "分子分母同乘 e^{−max}，约掉"},
            {"label": "归一化 Σexp", "in": "[e^-1, 1, e^-2]",
             "out": "p ≈ [.245, .665, .090]", "hot": True,
             "note": "与「直接算」数学上完全一致"},
            {"label": "log_softmax = x − max − log Σexp(x−max)",
             "in": "同上", "out": "[−2.42, −0.41, −2.41]",
             "note": "logsumexp 技巧：绝不先 softmax 再 log"},
        ], "max-shift 前后的数值范围对比"),
    ),
    "concepts": [
        concept("平移不变性", "softmax(x + c) = softmax(x)：同加常数输出不变。",
               "全体选手先扣同样的分再排名，名次不动。",
               "「名次不动」对指数归一严格成立——但它对相对差极敏感"
               "（e 倍/每分），线性归一没这么敏感。",
               "e^{x_i+c} = e^c·e^{x_i}，e^c 是公因子从 Σ 中提出约去。",
               "x=[1,2,3] 与 [101,102,103] 的 softmax 相同。",
               ["指数性质", "归一化定义"],
               "温度 τ 怎么进来？（softmax(x/τ)，τ 缩放相对差）",
               "softmax(x) = softmax(x + c)"),
        concept("logsumexp", "lse(x) = max + log(Σexp(x−max))：log-sum-exp "
               "三重嵌套的稳定算法。",
               "先找会场最高的人，以他为标尺量其他人，最后把标尺加回去。",
               "「加回去」在 log 域；标尺使 exp 参数 ≤ 0，和 ∈ [1,n]，"
               "log ∈ [0, log n]——完全可控。",
               "lse ≥ max 且 ≤ max + log n；它是 max 的光滑近似（温度 1），"
               "蒸馏 soft-target 的熵由此可调。",
               "x=[1000,1001]：lse = 1001 + log(1 + e^−1) ≈ 1001.313。",
               ["log-exp 互逆", "中间量必须 ≤ 0"],
               "lse 与 max 差多少有界吗？（≤ log n）",
               "lse = m + log Σ e^{x−m}"),
        concept("雅可比行和为零", "∂p_i/∂x_j = p_i(δ_ij − p_j)，每行和 = 0。",
               "概率守恒：抬一个必须压别人，行和为 0 就是「有加必有减」。",
               "行和为 0 说的是梯度行，不是概率本身（概率行和恒为 1）。",
               "反传无需 n×n：Jᵀv = p⊙(v − (p·v))，一次内积 + 逐元素乘。",
               "p=[.7,.2,.1]：∂p₁/∂x₁=.21，∂p₁/∂x₂=−.14。",
               ["链式法则", "softmax 定义"],
               "为什么反传可不构造矩阵？（雅可比可分解为内积+逐元素）",
               "J = diag(p) − ppᵀ"),
    ],
    "problem": problem(
        statement="实现数值稳定的 softmax 与 log_softmax：max-shift、"
                  "logsumexp、任意 axis；并验证极端输入（±1e4）与雅可比"
                  "性质（向量式反传对齐数值梯度）。",
        idea="softmax：x − max → exp → 归一化。log_softmax：x − lse(x)。"
             "梯度 Jᵀv = p⊙(v − Σp·v)。",
        steps=[
            "沿 axis 求 max 并 keepdims",
            "exp(x − max) 归一化（log 路径走 logsumexp）",
            "极端输入自测：1e4 量级不溢出",
            "log 版：安全区与 log(softmax) 一致、极端区无 −inf",
            "梯度：向量式实现与数值梯度对齐",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def softmax(x, axis=-1):\n"
            "    x = x - np.max(x, axis=axis, keepdims=True)\n"
            "    e = np.exp(x)\n"
            "    return e / e.sum(axis=axis, keepdims=True)\n"
            "\n"
            "def logsumexp(x, axis=-1):\n"
            "    m = np.max(x, axis=axis, keepdims=True)\n"
            "    return m + np.log(np.exp(x - m).sum(axis=axis, keepdims=True))\n"
            "\n"
            "def log_softmax(x, axis=-1):\n"
            "    return x - logsumexp(x, axis=axis)\n"
            "\n"
            "# 极端输入不上溢\n"
            "x = np.array([[1000.0, 1001.0, 999.0],\n"
            "              [-10000.0, -9999.0, -10001.0]])\n"
            "p = softmax(x)\n"
            "assert np.isfinite(p).all() and np.allclose(p.sum(-1), 1)\n"
            "assert abs(p[0, 1] - 0.665241) < 1e-5\n"
            "# log 版不产生 -inf，安全区与 log(softmax) 一致\n"
            "ls = log_softmax(x)\n"
            "assert np.isfinite(ls).all()\n"
            "assert np.allclose(ls, np.log(p), atol=1e-12)\n"
            "# 雅可比向量式对齐数值梯度\n"
            "rng = np.random.default_rng(8)\n"
            "z = rng.normal(size=6)\n"
            "pp = softmax(z)\n"
            "v = rng.normal(size=6)\n"
            "Jv = pp * (v - (pp * v).sum())\n"
            "eps = 1e-6\n"
            "num = np.array([((softmax(z + eps * e_i) - pp) / eps).dot(v)\n"
            "                for e_i in np.eye(6)])\n"
            "assert np.allclose(Jv, num, atol=1e-6)\n"
            "print('softmax/logsumexp OK; 雅可比向量式与数值梯度对齐')\n"
        ),
        notes="注意对齐方向：数值梯度对齐的是 Jᵀv（真实反传路径），永远"
              "不需要构造 n×n。混合精度纪律：exp/sum 在 fp32 完成。",
        pitfalls=[
            "max 忘 keepdims——广播错轴，小 batch 看不出大 batch 崩。",
            "log_softmax 写成 log(softmax(x))：下溢 −inf。",
            "logsumexp 忘减 max：和式上溢 log(inf)。",
            "axis 语义不清：明确按类别维归一化。",
            "fp16 内做 exp：累加精度不足，须 fp32。",
        ],
        tips="价值在「讲清楚为什么」：30 秒平移不变 → 30 秒稳定版 → 1 分钟 "
             "logsumexp → 1 分钟雅可比，全程 ≤4 分钟，把时间留给追问。",
        whyItWorks="平移不变性免费提供 max-shift；logsumexp 绕开「先 log 后 "
                  "和」的下溢路径；雅可比 diag(p)−ppᵀ 结构让反传 O(n)。",
        examples=[],
        time="O(n)（两遍扫描）",
        space="O(n)",
        why="max 必须先知、归一化必须后算，两遍是最小必要量。",
        edgeCases=[
            "全同值：均匀分布 1/n。",
            "单元素：[1.0]，log 版 [0.0]。",
            "含 −inf 掩码：exp 下溢天然支持；全行 −inf 会 NaN，"
            "掩码要保证每行至少一项有效。",
            "float16 输入：先 cast fp32。",
            "词表 12 万：用 online softmax / 分块（FlashAttention 核心）。",
        ],
        keyPoints=[
            "减 max 数学不变数值必稳——永远写",
            "log_softmax = x − lse(x)，绝不先 softmax 再 log",
            "logsumexp 有界：[max, max + log n]",
            "雅可比 diag(p)−ppᵀ，反传 p⊙(v − p·v)",
            "fp16 混合精度里 softmax 必须 fp32 内算",
            "全 −inf 行会 NaN：掩码保证每行至少一项有效",
        ],
        variants=[
            variant(
                "online softmax（流式）",
                "单遍扫描同时维护 running max 与归一化项——FlashAttention "
                "的理论核心。",
                "import numpy as np\n"
                "def softmax_ref(x):\n"
                "    e = np.exp(x - x.max()); return e / e.sum()\n"
                "def online_softmax(x):\n"
                "    m = -np.inf; s = 0.0\n"
                "    for xi in x:\n"
                "        m_new = max(m, xi)\n"
                "        s = s * np.exp(m - m_new) + np.exp(xi - m_new)\n"
                "        m = m_new\n"
                "    return np.exp(x - m) / s\n"
                "x = np.array([1000., 1001., 999.])\n"
                "assert np.allclose(online_softmax(x), softmax_ref(x))\n"
                "print('online softmax OK：单遍，O(1) 额外显存')\n",
                "流式/分块场景（FlashAttention）；面试进阶谈资。",
                "一遍扫描，显存 O(1)",
            ),
            variant(
                "带温度的 softmax",
                "x/τ：τ<1 锐化、τ>1 平滑——蒸馏与对比学习的竞争强度旋钮。",
                "import numpy as np\n"
                "def softmax(x, axis=-1):\n"
                "    x = x - x.max(axis=axis, keepdims=True)\n"
                "    e = np.exp(x); return e / e.sum(axis=axis, keepdims=True)\n"
                "x = np.array([2.0, 1.0, 0.0])\n"
                "p_hot = softmax(x / 0.5)\n"
                "p_soft = softmax(x / 2.0)\n"
                "assert p_hot[0] > p_soft[0]\n"
                "print('τ=0.5:', np.round(p_hot, 3), ' τ=2:', np.round(p_soft, 3))\n",
                "蒸馏、对比学习、采样温度。",
                "同 softmax",
            ),
        ],
        comparison=[
            comparison_row(["实现", "上溢", "下溢", "复杂度", "用途"]),
            comparison_row(["朴素 exp/Σexp", "会", "—", "O(n)", "仅示意"]),
            comparison_row(["max-shift", "不会", "—", "O(n)", "标准"]),
            comparison_row(["logsumexp 路径", "不会", "不会", "O(n)", "损失函数"]),
            comparison_row(["online/分块", "不会", "不会", "O(n) 单遍", "FlashAttention"]),
        ],
        interviewScript="「稳定性全部来自平移不变：减 max 不改结果只改数值。"
                        "log 版走 logsumexp 一次到位。梯度 diag(p)−ppᵀ，反传"
                        "向量式 O(n)。这两个性质分别是交叉熵稳定性和 "
                        "FlashAttention 在线 softmax 的地基。」",
    ),
}

# ===========================================================================
# 2. 手写 Top-k 与 Top-p（Nucleus）采样
# ===========================================================================
D["curated-top-k-top-p-sampling"] = {
    "tldr": "Top-k 截断概率前 k 个候选；Top-p 截断累计概率达到 p 的最小集合"
            "——候选数随分布形状自适应。两者都是「截断 + 重归一化 + 采样」，"
            "实现细节在掩码语义与管线顺序。",
    "why": "解码策略是 LLM 应用与推理岗常考题：考「生成质量可控性」的理解"
           "层次——greedy/温度/top-k/top-p 各解决什么、副作用是什么、怎么"
           "组合。代码只要 10 行，讲清取舍才是区分度。",
    "teaching": teaching(
        progressive=[
            lv(1, "greedy 稳定但重复；纯采样多样但可能抽长尾噪声。"
                  "截断采样在两者之间。"),
            lv(2, "Top-k：保留 logit 最大的 k 个，其余 −inf，重归一化后采样。"),
            lv(3, "Top-p：按概率降序累计，取累计 ≥ p 的最小前缀——"
                  "尖时候选少、平时候选多，自适应是本质优势。"),
            lv(4, "管线顺序：penalty → temperature → top-k → top-p → "
                  "softmax → 采样。顺序错了语义就变。"),
        ],
        socratic=[
            qa("为什么 top-p 比 top-k 更合理？",
               "分布尖时 top-k 强塞 k 个长尾候选引噪声；分布平时又截太多。"
               "top-p 按概率质量自适应候选数，两种极端都处理得当。"),
            qa("temperature=0 和 greedy 等价吗？",
               "数学上 τ→0 退化为 argmax；实现上 τ=0 除零，要么特判 greedy "
               "分支要么用极小值近似——HF 就是这么处理的。"),
            qa("top-p 有确定性输出吗？",
               "没有——截断后仍在候选内随机。要确定性得固定 seed 或 greedy；"
               "这也是「评测 greedy/beam、产品 top-p」惯例的原因。"),
        ],
        mechanism="logits 管线：温度缩放 → 惩罚 → top-k 掩码 → top-p 掩码"
                 "（累计 ≥ p 的最小前缀）→ 被掩位置 −inf → softmax（自动"
                 "重归一化）→ 按概率采样。",
        boundary="截断是分布修改：重归一化会把剩余候选概率放大，不是「隐藏"
                 "部分质量」。对长尾知识型任务（代码、专有名词）截断过狠"
                 "系统性伤害。",
        analogyBoundary="点菜：top-k 是「只看前 k 道招牌」，top-p 是「挑出"
                       "合计占 90% 好评的最少几道」。失效处：菜单每天变，"
                       "固定 k 在冷门日把好菜挡在外面——正是 top-p 自适应"
                       "的价值。",
        misconceptions=[
            "先 top-p 后温度：温度应最先，顺序颠倒后阈值语义全变。",
            "top-p 取「累计 ≤ p」：方向反了，把多数候选扔掉。",
            "截断后忘重归一化：直接在原概率上采样，和 < 1。",
            "重复惩罚作用于概率而非 logits——应在 log 域。",
            "以为 top-k 与 top-p 叠加是并集——是「先 k 后 p」的交集。",
        ],
        ownAnalysis="给尖锐与平坦两组分布展示 top-p 候选数自适应（top-k "
                   "做不到的）；再演示管线顺序；最后提 beam search 与截断"
                   "采样的适用边界（评测确定性 vs 产品多样性）与 min-p。",
        officialNotes="The Curious Case of Neural Text Degeneration "
                      "(Holtzman 2019, nucleus 原论文)；HF generation utils "
                      "的 TopK/TopPLogitsWarper 源码。",
        interviewAnswer="管线顺序一句话 → top-k/top-p 实现（排序掩码）→ "
                       "自适应对比 → 副作用（重归一化放大、长尾伤害）→ "
                       "参数经验（temp 0.7~1.0, top-p 0.9~0.95）。",
        prereq=["softmax 与概率分布", "离散采样", "排序与掩码"],
        next_steps=["beam search 与长度归一化", "min-p 采样", "投机解码"],
    ),
    "diagram": diagram(
        "matrix", "同一分布下 top-k 与 top-p 的候选集对比",
        "尖锐分布（前 2 项占 97%）top-p=0.9 只取 2 个候选；平坦分布前 8 项"
        "才凑够 90%——同一 top-p 取 8 个。固定 k=4 在两种场景下都不合适。",
        "top-k 与 top-p 截断行为对比",
        svg_compare(
            [
                {"title": "尖锐分布（置信高）", "lines": [
                    "p = [.80, .15, .02, .01, ...]",
                    "top-p=0.9 → 取 2 个",
                    "top-k=4 → 多带 2 个长尾噪声",
                    "自适应：候选少而准",
                    "生成更稳定"], "hot": True},
                {"title": "平坦分布（不确定）", "lines": [
                    "p = [.20, .18, .15, .12, .10, .08, .07, .05, ...]",
                    "top-p=0.9 → 取 8 个",
                    "top-k=4 → 截掉一半合理选项",
                    "自适应：候选多而全",
                    "生成更多样"], "hot": False},
            ],
            "同一 top-p 在两种分布下的候选数差异",
            bottom="top-p 的候选数是分布形状的函数；top-k 永远是常数"),
    ),
    "concepts": [
        concept("截断重归一化", "被截掉的候选概率质量重新分配给保留集合。",
               "淘汰赛后剩余选手按原实力比例重新瓜分。",
               "「重新瓜分」按原相对比例，不是均分——相对排序不变。",
               "mask 后 logits=−inf → softmax 自动给被掩项 0，保留项按"
               "原相对值归一化。",
               "p=[.5,.3,.2] 截掉 .2 → [.625,.375]。",
               ["softmax 掩码语义", "−inf 与稳定"],
               "为什么置 −inf 不是 0 概率？（掩码在 logit 域，0 logit 仍有"
               "概率）",
               "logits[~keep] = -inf"),
        concept("核采样（nucleus）", "累计概率达到 p 的最小前缀集合。",
               "找出占 90% 好评的最少几道菜。",
               "「好评率」静态；语言分布每步变，核的大小跟着变——这正是"
               "自适应本意。",
               "降序排序 → cumsum → 首个 ≥ p 的位置及之前保留。"
               "HF 写法：cumsum(p) − p < p。",
               "p=0.9，p 排序 [.4,.3,.15,.1,.05]：累计 [.4,.7,.85,.95] → "
               "取前 4。",
               ["排序稳定性", "≥ 与 > 的边界"],
               "p=1.0 时是什么？（不截断，全分布采样）",
               "keep = cumsum(sorted_p) - sorted_p < p"),
        concept("温度与管线顺序", "τ 作用于 logits（最先），截断作用于分布"
               "（后），采样最后。",
               "先调火候再决定哪些菜上桌，最后掷骰子选一份。",
               "火候连续调节，截断硬阈值——作用于不同对象，顺序不可交换。",
               "标准顺序 penalty → temperature → top-k → top-p → softmax → "
               "multinomial；HF 的 LogitsProcessorList 按此排列。",
               "τ=0.7 把 logits 放大 1.43 倍后再截断。",
               ["温度形式", "logit 域 vs 概率域"],
               "penalty 为什么在温度前？（作用于原始 logit 语义，与锐度无关）",
               "logits /= τ → mask → softmax → sample"),
    ],
    "problem": problem(
        statement="实现 top-k 与 top-p 采样（含温度与组合管线），输入一维 "
                  "logits，输出 token id。要求：掩码置 −inf、自动重归一化、"
                  "top-p 候选数随分布自适应。",
        idea="top-k：保留前 k 个索引，其余 −inf。top-p：降序累计概率，"
             "取累计 ≥ p 的最小前缀，其余 −inf。softmax + 按概率抽样。",
        steps=[
            "温度缩放 logits /= τ（τ→0 特判 greedy）",
            "top-k 掩码：保留最大 k 个",
            "top-p 掩码：排序、cumsum、最小前缀",
            "两掩码取交集（先 k 后 p），置 −inf",
            "softmax → rng.choice 采样",
            "自测：尖锐分布 top-p 候选 < 平坦分布候选",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def sample(logits, temperature=1.0, top_k=None, top_p=None, seed=None):\n"
            "    rng = np.random.default_rng(seed)\n"
            "    z = np.asarray(logits, float).copy()\n"
            "    if temperature <= 1e-6:\n"
            "        return int(np.argmax(z))          # greedy 分支\n"
            "    z = z / temperature\n"
            "    if top_k is not None and 0 < top_k < len(z):\n"
            "        kth = np.sort(z)[-top_k]\n"
            "        z = np.where(z < kth, -np.inf, z)\n"
            "    if top_p is not None and 0 < top_p < 1.0:\n"
            "        order = np.argsort(-z)\n"
            "        ps = np.exp(z[order] - z[order].max()); ps /= ps.sum()\n"
            "        keep_sorted = np.cumsum(ps) - ps < top_p   # 最小前缀\n"
            "        keep = np.zeros_like(z, bool)\n"
            "        keep[order[keep_sorted]] = True\n"
            "        z = np.where(~keep, -np.inf, z)\n"
            "    e = np.exp(z - np.max(z[np.isfinite(z)]))\n"
            "    e[~np.isfinite(e)] = 0\n"
            "    p = e / e.sum()\n"
            "    return int(rng.choice(len(z), p=p))\n"
            "\n"
            "def n_candidates(logits, temperature=1.0, top_p=0.9):\n"
            "    z = np.asarray(logits, float) / temperature\n"
            "    ps = np.exp(z - z.max()); ps /= ps.sum()\n"
            "    cs = np.cumsum(np.sort(ps)[::-1])\n"
            "    return int(np.searchsorted(cs, top_p) + 1)\n"
            "\n"
            "z = np.array([2.0, 1.0, 0.5, -1.0])\n"
            "assert sample(z, temperature=0.0) == 0        # greedy\n"
            "picks = {sample(z, top_k=2, seed=s) for s in range(200)}\n"
            "assert picks <= {0, 1}, f'top_k=2 却采出了 {picks}'\n"
            "sharp = np.array([8.0, 6.0, 0.0, 0.0, 0.0])\n"
            "flat = np.array([2.0, 1.9, 1.8, 1.7, 1.6, 1.5, 1.4, 1.3, 0., 0.])\n"
            "n_sharp = n_candidates(sharp)\n"
            "n_flat = n_candidates(flat)\n"
            "assert n_sharp < n_flat, f'自适应失效: {n_sharp} vs {n_flat}'\n"
            "assert n_candidates(z, top_p=0.999999) == len(z)\n"
            "print('Top-k/Top-p OK: sharp=%d 候选, flat=%d 候选 (p=0.9)'\n"
            "      % (n_sharp, n_flat))\n"
        ),
        notes="top-p 的「最小前缀」用 cumsum − 当前项 < p（HF 同款），保证"
              "恰好覆盖 ≥ p 的最小集合。top-k 用「第 k 大的值」做阈值避免"
              "全词表排序（词表 12 万时 argsort 是主要开销）。",
        pitfalls=[
            "top-p 比较方向写反。",
            "截断后直接在原 probs 上采样（没重归一化）。",
            "temperature 放在截断之后。",
            "top_k=0 或 k≥词表的边界没跳过。",
            "用 0 而非 −inf 造掩码：0 logit 仍有概率。",
            "忘 seed 导致测试不稳定。",
        ],
        tips="先画管线顺序再落码——顺序本身就是考点。用尖锐/平坦分布"
             "演示 top-p 自适应是「演示亮点」，比讲十行代码更有说服力。",
        whyItWorks="截断 + 重归一化 = 在「质量可控的候选集」内保留原始分布"
                  "的相对偏好；top-p 的候选集由概率质量定义，因此对分布"
                  "形状自适应。",
        examples=[],
        time="top-k O(V)；top-p O(V log V)（可优化为部分排序）",
        space="O(V)",
        why="V 是词表大小（1e5 量级）；生产用 kernel 融合避免排序。",
        edgeCases=[
            "τ=0：greedy 分支，不能除零。",
            "top_k ≥ V 或 ≤ 0：跳过截断。",
            "top_p→1：不截断；top_p→0：趋近 greedy。",
            "logits 含 −inf：排序与 cumsum 要稳定处理。",
            "全同值 logits：均匀分布，top-k 取任意前 k 个。",
        ],
        keyPoints=[
            "管线顺序：penalty → temperature → top-k → top-p → softmax → 采样",
            "top-p 是「累计 ≥ p 的最小前缀」，方向不能反",
            "截断重归一化由 softmax(−inf) 自动完成",
            "top-p 自适应候选数，top-k 固定",
            "τ=0 特判 greedy，不能除零",
            "截断采样无确定性：评测 greedy/beam，产品 top-p",
        ],
        variants=[
            variant(
                "min-p 采样（2024）",
                "只保留概率 ≥ min_p·p_max 的候选：以最高概率为锚，比 top-p "
                "对温度更稳健。",
                "import numpy as np\n"
                "def sample_minp(logits, min_p=0.1, temperature=1.0, seed=0):\n"
                "    rng = np.random.default_rng(seed)\n"
                "    z = np.asarray(logits, float) / temperature\n"
                "    e = np.exp(z - z.max()); p = e / e.sum()\n"
                "    keep = p >= min_p * p.max()\n"
                "    p = np.where(keep, p, 0.0); p /= p.sum()\n"
                "    return int(rng.choice(len(z), p=p))\n"
                "z = np.array([5., 4.5, 1., 0.5, 0.])\n"
                "picks = {sample_minp(z, seed=s) for s in range(300)}\n"
                "assert picks <= {0, 1, 2}\n"
                "print('min-p OK:', sorted(picks))\n",
                "高温防长尾噪声的新方案；vLLM/HF 已支持。",
                "同 top-p",
            ),
            variant(
                "重复惩罚（presence 简化版）",
                "在 logit 域对已出现 token 减惩罚，抑制复读——与截断采样"
                "正交，作用于管线最前。",
                "import numpy as np\n"
                "def penalize(logits, generated, penalty=1.2):\n"
                "    z = np.asarray(logits, float).copy()\n"
                "    for tok in set(generated):   # presence：出现过就罚一次\n"
                "        z[tok] = z[tok] - np.log(penalty) if z[tok] > 0 \\\n"
                "                 else z[tok] + np.log(penalty)\n"
                "    return z\n"
                "z = penalize(np.array([3., 3., 1.]), generated=[0, 0, 1])\n"
                "assert z[0] < 3.0 and z[1] < 3.0   # 出现过的都被压\n"
                "assert z[2] == 1.0                 # 没出现的不动\n"
                "print('重复惩罚 OK:', np.round(z, 3))\n",
                "开放式生成防复读；与 top-p 组合。",
                "O(生成长度)",
            ),
        ],
        comparison=[
            comparison_row(["策略", "候选数", "确定性", "主要问题", "适用"]),
            comparison_row(["greedy", "1", "有", "重复循环", "评测/代码类"]),
            comparison_row(["纯采样", "全部", "无", "长尾噪声", "几乎不用"]),
            comparison_row(["top-k", "固定 k", "无", "不自适应", "传统基线"]),
            comparison_row(["top-p", "自适应", "无", "重归一化放大", "产品默认"]),
            comparison_row(["min-p", "按 p_max 比例", "无", "较新", "高温场景"]),
            comparison_row(["beam search", "beam×S", "有", "长度偏置", "翻译/摘要"]),
        ],
        interviewScript="「解码管线顺序是惩罚→温度→top-k→top-p→softmax→"
                        "采样。top-k 固定候选数，尖时引噪声平时截太多；"
                        "top-p 按累计概率质量自适应，是产品默认。两个易错点："
                        "top-p 取『累计 ≥ p 的最小前缀』，截断靠置 −inf 让 "
                        "softmax 自动重归一化。评测用 greedy/beam，产品用 "
                        "top-p 0.9~0.95 加温度 0.7~1.0。」",
    ),
}

# ===========================================================================
# 3. 手写交叉熵与反向传播
# ===========================================================================
D["curated-cross-entropy-backward"] = {
    "tldr": "交叉熵 = −log p(y)：把正确类的概率拉向 1。手撕反传的核心结论："
            "softmax+CE 融合后梯度就是 p − onehot(y)——一个减法，雅可比的"
            "对角/非对角项在融合中完美相消。所有分类损失的反传模板。",
    "why": "「手推交叉熵梯度」是深度学习面试保留节目：考链式法则功底、"
           "softmax 雅可比记忆、以及「为什么框架要 fused 实现」的工程意识。"
           "答出 p − onehot 且能推导，后面所有损失类追问都好接。",
    "teaching": teaching(
        progressive=[
            lv(1, "前向：p = softmax(z)，loss = −log p[y]；数值上直接 "
                  "log_softmax(z)[y] 一步到位。"),
            lv(2, "链式法则：CE 上游梯度 −onehot/p_y 乘 softmax 雅可比，"
                  "p_y 相消后 = p − onehot(y)。"),
            lv(3, "为什么相消：−1/p_y 只在 y 分量非零，与雅可比第 y 行 "
                  "p_y(δ − p) 相乘恰好约掉 p_y。"),
            lv(4, "工程含义：不构造 n×n 雅可比，直接 (p − onehot)/B；"
                  "fused kernel 连 p 都不物化（logsumexp 路径）。"),
        ],
        socratic=[
            qa("为什么不先 softmax 再 −log？",
               "两步路径要先物化 p 且 p 下溢为 0 时 log 爆炸。fused 路径 "
               "log_softmax = z − lse(z) 数值稳定且少一次读写。"),
            qa("p − onehot 梯度的直觉？",
               "每个类别的梯度 = 当前概率与目标 0/1 的差——「概率缺口」。"
               "正确的类为负（推高），其余为正（推低）。"),
            qa("类别不均衡时有什么问题？",
               "梯度只由概率缺口决定：高频类 p→1 梯度消失，低频类样本少"
               "但梯度大——总体偏向高频类。对策：加权 CE 或 Focal Loss。"),
        ],
        mechanism="前向：logp = z − lse(z)，loss = −mean(logp[y])。反向："
                 "上游 dlogp = −onehot(y)/B，dz = dlogp − (Σdlogp)·softmax "
                 "化简后 = (p − onehot(y))/B。关键在符号相消。",
        boundary="p→1 梯度消失（学对就停），p→0 时趋近 −1（错得离谱猛推）"
                 "——健康的自适应步长。但对「错误但自信」样本梯度恒 1 量级，"
                 "噪声标签持续注入大梯度——标签平滑/focal loss 的动机。",
        analogyBoundary="教练按「实际与目标名次的差距」给训练量：差得远练得"
                       "狠、达标就少练。失效处：目标是人为 onehot，"
                       "标签噪声直接变成错误训练量。",
        misconceptions=[
            "写出 n×n 雅可比再乘向量——对但低效，必被追问融合形式。",
            "忘除 batch（mean 语义）或重复除。",
            "反向推导丢 −1/p_y 的符号：梯度方向反了训练发散。",
            "对 soft label 硬套 p − onehot：应为 p − y_soft。",
            "CE 与 NLL 混淆：CE 含 softmax，NLL 只取 logp[y]——"
            "框架的 CrossEntropyLoss 是两者 fused。",
        ],
        ownAnalysis="推导「两步走」：先 softmax 雅可比，再乘 CE 的 −onehot/p_y "
                   "演示 p_y 相消。代码先写朴素两步版展示 log(0) 爆炸，再写 "
                   "fused 稳定版。给 label smoothing 一行扩展 "
                   "(p − (1−ε)onehot − ε/K)。",
        officialNotes="Goodfellow §6.2 与 CS231n softmax 梯度推导；PyTorch "
                      "CrossEntropyLoss 文档明确 fused log_softmax + NLL；"
                      "label smoothing 出自 Inception-v3 (Szegedy 2016) §7。",
        interviewAnswer="写 fused 前向 → 推雅可比相消 → 给 p − onehot → "
                       "batch mean 与数值稳定 → label smoothing/focal loss "
                       "扩展 → 为什么框架要 fused。",
        prereq=["softmax 雅可比", "链式法则", "onehot 编码"],
        next_steps=["KL 散度与蒸馏", "Focal Loss", "InfoNCE 对比损失"],
    ),
    "diagram": diagram(
        "architecture", "softmax 雅可比与 CE 梯度的相消过程",
        "CE 上游梯度只在正确类 y 处非零（−1/p_y），与 softmax 雅可比第 y 行 "
        "p_y(δ−p) 相乘时 p_y 恰好约掉——最终梯度 = p − onehot(y)。",
        "交叉熵反传的相消推导",
        svg_flow([
            {"label": "上游：dL/dlogp = −onehot(y)/p_y", "in": "loss 标量",
             "out": "(n,) 只在 y 处非零", "hot": True,
             "note": "−log p_y 对 logp_y 的导数"},
            {"label": "softmax 雅可比第 y 行：p_y(δ − p)", "in": "p (n,)",
             "out": "行向量",
             "note": "diag(p) − ppᵀ 的第 y 行"},
            {"label": "相乘：p_y(δ−p) · (−1/p_y)", "in": "两个 (n,)",
             "out": "p − onehot(y)", "hot": True,
             "note": "p_y 完全相消——融合梯度的全部秘密"},
            {"label": "batch 语义：dz = (p − onehot) / B", "in": "(B,n)",
             "out": "(B,n)",
             "note": "mean 归约 → 除 B；sum 归约不除"},
        ], "从上游梯度到融合梯度的三步相消"),
    ),
    "concepts": [
        concept("NLL 与 CE 的关系", "CE(softmax(z), y) = NLL(log_softmax(z), y)："
               "前者含归一化，后者假设输入已是 log 概率。",
               "CE 是「评分 + 换算」，NLL 只看已换算好的分数。",
               "框架的 CrossEntropyLoss 是 fused 名字——输入必须是未归一化 "
               "logits，喂概率会双重 softmax。",
               "logp = z − lse(z)；loss = −logp[y]。",
               "z=[2,1,0], y=0：lse≈2.408，loss=−logp₀=0.408。",
               ["logsumexp", "softmax 定义"],
               "给 CrossEntropyLoss 喂 softmax 输出会怎样？（双重归一化，"
               "loss 与梯度全错）",
               "CE = NLL ∘ log_softmax"),
        concept("概率缺口梯度", "dz = p − onehot(y)：梯度就是当前概率与"
               "目标的差。",
               "射箭：离靶心差多少修正力度就多少；正中靶心修正为零。",
               "错误侧梯度恒接近 1，不会因错得更狠而更大——CE 对「自信的"
               "错误」没有额外惩罚（focal loss 补这里）。",
               "p→1：dz→0；p→0（错误类）：dz→−1；其它类 dz = p_i > 0。",
               "p=[.7,.2,.1], y=0 → dz=[−.3, .2, .1]。",
               ["softmax 雅可比", "batch 归约"],
               "标签平滑后梯度？（p − ((1−ε)e_y + ε/K))",
               "dz = (p − onehot(y)) / B"),
        concept("标签平滑", "目标从 onehot 换成 (1−ε)·onehot + ε/K。",
               "老师改卷最高 98 分——留出不确定性余地。",
               "平滑不是正则噪声，是系统性目标修改：最优解从 p=1 移到 "
               "p=(1−ε)+ε/K，全部类保留 ε/K 基线概率。",
               "ε=0.1, K=1000：目标 = 0.9001·onehot + 0.0001·其余。",
               "Inception-v3 用 ε=0.1，泛化普遍提升。",
               ["onehot 与概率单纯形", "梯度形式不变性"],
               "ε 过大会怎样？（最优概率上限被压低，模型欠拟合）",
               "target = (1−ε)·onehot + ε/K"),
    ],
    "problem": problem(
        statement="实现交叉熵前向（fused log_softmax 路径）与反向传播："
                  "输入 logits (B,K) 与标签 y (B,)，输出 loss 与 dz；"
                  "验证 dz == (p − onehot)/B 且与数值梯度对齐。",
        idea="前向：logp = z − lse(z)，loss = −mean(logp[range(B), y])。"
             "反向：dz = (p − onehot(y))/B，p 由稳定 softmax 得出。",
        steps=[
            "fused 前向：logsumexp → logp → gather y",
            "反向：dz = (softmax(z) − onehot(y)) / B",
            "数值实验：与有限差分数值梯度对齐",
            "朴素两步版（softmax → log）在极端 logits 下爆 −inf，对比",
            "扩展：label smoothing 的目标替换",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def ce_forward(z, y):\n"
            "    \"\"\"fused：log_softmax 路径。z:(B,K), y:(B,) int。\"\"\"\n"
            "    m = z.max(axis=1, keepdims=True)\n"
            "    lse = m + np.log(np.exp(z - m).sum(axis=1, keepdims=True))\n"
            "    logp = z - lse\n"
            "    loss = -logp[np.arange(len(y)), y].mean()\n"
            "    return loss, logp\n"
            "\n"
            "def ce_backward(z, y):\n"
            "    \"\"\"dz = (p - onehot(y)) / B。\"\"\"\n"
            "    B, K = z.shape\n"
            "    m = z.max(axis=1, keepdims=True)\n"
            "    e = np.exp(z - m)\n"
            "    p = e / e.sum(axis=1, keepdims=True)\n"
            "    dz = p.copy()\n"
            "    dz[np.arange(B), y] -= 1.0\n"
            "    return dz / B\n"
            "\n"
            "rng = np.random.default_rng(9)\n"
            "B, K = 4, 6\n"
            "z = rng.normal(size=(B, K))\n"
            "y = rng.integers(0, K, size=B)\n"
            "loss, logp = ce_forward(z, y)\n"
            "assert np.isfinite(loss) and abs(loss) < 10\n"
            "\n"
            "# 数值梯度对齐（对每个 logit 分量）\n"
            "dz = ce_backward(z, y)\n"
            "eps = 1e-6\n"
            "num = np.zeros_like(z)\n"
            "for i in range(B):\n"
            "    for k in range(K):\n"
            "        zp, zm = z.copy(), z.copy()\n"
            "        zp[i, k] += eps; zm[i, k] -= eps\n"
            "        num[i, k] = (ce_forward(zp, y)[0]\n"
            "                     - ce_forward(zm, y)[0]) / (2 * eps)\n"
            "assert np.allclose(dz, num, atol=1e-6), '反传必须对齐数值梯度'\n"
            "\n"
            "# 概率缺口验证：dz + onehot/B == p/B\n"
            "e = np.exp(z - z.max(1, keepdims=True))\n"
            "p = e / e.sum(1, keepdims=True)\n"
            "oh = np.zeros((B, K)); oh[np.arange(B), y] = 1\n"
            "assert np.allclose(dz, (p - oh) / B)\n"
            "\n"
            "# 朴素两步版在极端 logits 下爆炸\n"
            "z_bad = np.array([[1000.0, 0., 0.]]); y_bad = np.array([0])\n"
            "try:\n"
            "    naive = -np.log(np.exp(z_bad) / np.exp(z_bad).sum())[0, 0]\n"
            "    ok = np.isfinite(naive)\n"
            "except Exception:\n"
            "    ok = False\n"
            "assert not ok, '朴素版此处应已上溢'\n"
            "print('CE 前向/反向 OK: loss=%.4f，dz 对齐数值梯度' % loss)\n"
        ),
        notes="反向的核心一行：dz[range(B), y] −= 1 再整体除 B——这就是"
              "「p − onehot」的实现形态。数值实验用中心差分对齐，"
              "比单侧差分精度高一个量级。",
        pitfalls=[
            "写出 n×n 雅可比：对但低效，必被追问。",
            "忘除 B（mean 语义）：loss 随 batch 大小漂移。",
            "丢 −1/p_y 符号：梯度反向训练发散。",
            "对 soft label 硬套 onehot：应为 p − y_soft。",
            "朴素两步前向：p 下溢 log(0)=−inf。",
            "gather 用 argmax 而不是标签：那是自蒸馏/EM 的语义，不是 CE。",
        ],
        tips="推导「两步走」演示 p_y 相消是全场高潮；代码先朴素后 fused "
             "对比。收尾一句「这就是为什么框架的 CrossEntropyLoss 要求"
             "输入 logits」——把工程意识和理论连起来。",
        whyItWorks="CE 上游梯度 −onehot/p_y 与 softmax 雅可比第 y 行相乘时 "
                  "p_y 恰好相消——融合梯度的全部秘密都在这个结构里。",
        examples=[],
        time="前向 O(B·K)，反向 O(B·K)",
        space="O(B·K)（fused kernel 可不物化 p）",
        why="一次 max + 一次 sum + 一次 gather 是最小必要量。",
        edgeCases=[
            "p→1（几乎全对）：梯度→0，收敛停火。",
            "p→0（自信错误）：梯度 −1 量级，噪声标签持续注入大梯度。",
            "K=1：loss 恒 0（只有一个类的分布无熵）。",
            "标签越界：必须断言检查（框架会 CUDA 断言崩溃）。",
            "label smoothing：目标替换后梯度形式不变。",
        ],
        keyPoints=[
            "前向走 log_softmax = z − lse(z)，绝不先 softmax 再 log",
            "融合梯度 dz = (p − onehot(y))/B",
            "相消来源：上游 −1/p_y 与雅可比第 y 行的 p_y 约掉",
            "mean 归约除 B，sum 归约不除",
            "标签平滑：目标 (1−ε)onehot + ε/K，梯度形式不变",
            "框架 CE 的输入必须是 logits——喂概率是双重归一化 bug",
        ],
        variants=[
            variant(
                "label smoothing 版",
                "目标换成 (1−ε)·onehot + ε/K，梯度变为 p − target，"
                "一行改动。",
                "import numpy as np\n"
                "def ce_backward_smooth(z, y, eps=0.1):\n"
                "    B, K = z.shape\n"
                "    e = np.exp(z - z.max(1, keepdims=True))\n"
                "    p = e / e.sum(1, keepdims=True)\n"
                "    t = np.full((B, K), eps / K)\n"
                "    t[np.arange(B), y] += 1.0 - eps\n"
                "    return (p - t) / B\n"
                "z = np.random.default_rng(0).normal(size=(2, 5))\n"
                "d = ce_backward_smooth(z, np.array([0, 3]))\n"
                "assert np.isfinite(d).all()\n"
                "print('label smoothing OK, 梯度形状', d.shape)\n",
                "分类泛化、蒸馏前的热身。",
                "同 CE",
            ),
            variant(
                "Focal Loss 权重",
                "在 CE 上乘 (1−p_y)^γ：易例（p 高）权重指数衰减，"
                "聚焦难例——检测任务标配。",
                "import numpy as np\n"
                "def focal_weighted_ce(z, y, gamma=2.0):\n"
                "    m = z.max(1, keepdims=True)\n"
                "    lse = m + np.log(np.exp(z - m).sum(1, keepdims=True))\n"
                "    logp = z - lse\n"
                "    py = np.exp(logp[np.arange(len(y)), y])\n"
                "    fl = ((1 - py) ** gamma) * (-logp[np.arange(len(y)), y])\n"
                "    return float(fl.mean())\n"
                "z = np.random.default_rng(1).normal(size=(4, 5))\n"
                "y = np.array([0, 1, 2, 3])\n"
                "l = focal_weighted_ce(z, y)\n"
                "assert l >= 0 and np.isfinite(l)\n"
                "print('focal OK, loss=%.4f' % l)\n",
                "目标检测/极端不均衡分类（RetinaNet）。",
                "同 CE + 一次逐元素乘",
            ),
        ],
        comparison=[
            comparison_row(["损失", "目标", "梯度形态", "适用", "备注"]),
            comparison_row(["CE", "onehot", "p − onehot", "通用分类", "fused 稳定"]),
            comparison_row(["CE + smoothing", "(1−ε)onehot + ε/K", "p − target", "提升泛化", "Inception-v3"]),
            comparison_row(["Focal", "onehot ×(1−p)^γ", "加权缺口", "极端不均衡", "RetinaNet"]),
            comparison_row(["KL(蒸馏)", "软目标 q", "p − q", "知识蒸馏", "含温度"]),
        ],
        interviewScript="「前向走 fused log_softmax 路径，一步到 loss。"
                        "反向推导两步：softmax 雅可比 diag(p)−ppᵀ，CE 上游"
                        "−onehot/p_y，相乘时 p_y 相消——梯度就是 p − onehot"
                        " 除以 batch。扩展两点：标签平滑只换目标，focal 在"
                        "缺口上加 (1−p)^γ 权重。这就是框架 CE 要求 logits "
                        "输入的原因——fused 路径既是性能也是正确性。」",
    ),
}
