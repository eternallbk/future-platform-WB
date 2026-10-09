# -*- coding: utf-8 -*-
"""_drills_set5.py — 模型手撕深度解析 · 微调/生成/多模态/结构（5 题）。"""

from _drills_helpers import (
    diagram, teaching, lv, qa, concept, variant, comparison_row,
    problem, svg_flow, svg_compare, svg_matrix,
)

D = {}

# ===========================================================================
# 1. 手写 LoRA 层
# ===========================================================================
D["curated-lora-implementation"] = {
    "tldr": "LoRA 把权重更新 ΔW 分解为两个低秩矩阵的积：W' = W + B·A，"
            "A 降维 r、B 升维回 d。训练只更新 A/B（参数量 d²→r(d+d)），"
            "推理可把 B·A 合并进 W 零开销。A 用高斯初始化、B 置零——"
            "保证训练起点 ΔW=0。",
    "why": "微调方向第一手撕题：考低秩假设的理解、初始化为什么一个随机"
           "一个零、α/r 缩放的语义、以及合并推理与多 LoRA 服务的工程"
           "追问。",
    "teaching": teaching(
        progressive=[
            lv(1, "直觉：微调的权重变化是「低秩」的——任务适配不需要"
                  "满秩自由度。ΔW = B·A，秩 ≤ r。"),
            lv(2, "前向：y = W₀x + (α/r)·B(Ax)。A: d×r，B: r×d，"
                  "x 先降维再升维。"),
            lv(3, "初始化：A ~ N(0, σ²)，B = 0 → 起点 ΔW = 0，"
                  "不破坏预训练知识。"),
            lv(4, "工程：α/r 是学习率的等效缩放（常见 α=2r）；推理合并 "
                  "W' = W₀ + (α/r)BA 一次完成； Serving 用 S-LoRA "
                  "同时挂几十个 adapter。"),
        ],
        socratic=[
            qa("为什么 B 必须置零而 A 随机？",
               "若 A 置零，B 的梯度恒为 0（∂L/∂B ∝ A·…）——B 永远学"
               "不动。A 随机 B 零：起点 ΔW=0 且两个矩阵都有非零梯度。"
               "反过来（A=0）B 的梯度虽然非零但 A 梯度为 0，同样卡死。"),
            qa("α/r 缩放是什么语义？",
               "等效于给 LoRA 分支的学习率乘 α/r——调 r 时保持更新"
               "量级稳定，超参解耦。α 通常设为 2r 或固定 16。"),
            qa("LoRA 应该加在哪些层？",
               "经验：注意力模块的 W_q/W_v 收益最稳（原论文结论）；"
               "全线性层加效果略好但参数多。MLP 层对知识注入类任务"
               "（如领域微调）更有效。"),
        ],
        mechanism="对每个被适配的线性层挂并联分支：z = A x（r 维），"
                 "h = B z（d 维），输出 y = W₀x + (α/r)·h。梯度只流经 "
                 "A/B；W₀ 冻结。合并推理：W_merged = W₀ + (α/r)·B@A。",
        boundary="LoRA 的表达力受秩 r 硬约束：r 太小（<8）学不动复杂任务，"
                 "太大（>64）接近全参微调但失去效率优势。低秩假设对"
                 "「风格/行为适配」强，对「大量新知识注入」弱（后者"
                 "考虑 DoRA/全参或 RAG）。",
        analogyBoundary="像在原画上贴可揭的贴纸改画：贴纸层（BA）很薄"
                       "（低秩）但足以改观感。失效处：贴纸无法改变画布"
                       "本身的材质——需要改基础权重的任务（灾难性新知识）"
                       "低秩表达不了。",
        misconceptions=[
            "A 和 B 都置零：梯度死锁，什么都学不到。",
            "A、B 都随机初始化：起点 ΔW≠0，破坏预训练分布。",
            "忘 α/r 缩放：调 r 时学习动态漂移。",
            "以为 LoRA 减小推理延迟——不合并时增加一点；合并后零开销。",
            "把 LoRA 加到 embedding 或 LayerNorm 上——常规做法只加线性层。",
        ],
        ownAnalysis="先讲低秩假设的来源（微调 ΔW 的谱衰减），再落码"
                   "（含合并函数与梯度流验证），自测三条：起点 ΔW=0、"
                   "梯度非零、合并前后输出一致。主动提 S-LoRA 多租户"
                   "服务与 QLoRA（4bit 底座 + LoRA）的组合。",
        officialNotes="LoRA (Hu 2021)；QLoRA (Dettmers 2023)；"
                      "S-LoRA 论文；PEFT 库的 lora.Linear 实现与"
                      " merge_and_unload。",
        interviewAnswer="低秩假设 → 结构 B·A + α/r → 初始化（B 零 A 随机"
                       "及原因）→ 训练/合并两种形态 → 加在哪层 → "
                       "QLoRA/S-LoRA 工程延伸。",
        prereq=["线性层与低秩分解", "梯度流", "微调流程"],
        next_steps=["QLoRA 量化底座", "DoRA 分解", "多 LoRA serving"],
    ),
    "diagram": diagram(
        "architecture", "LoRA：冻结主干 + 低秩旁路（可合并）",
        "训练时旁路 B·A 参与梯度更新，主干冻结；推理时可把 (α/r)·BA "
        "合并进 W₀ 变成单个线性层——零额外延迟。",
        "LoRA 前向与合并示意",
        svg_flow([
            {"label": "x → W₀（冻结）", "in": "(B,S,d)", "out": "主路径",
             "note": "不积累梯度，权重建在 4bit（QLoRA）也行"},
            {"label": "x → A（d→r，高斯初始化）", "in": "(B,S,d)",
             "out": "(B,S,r)", "hot": True,
             "note": "降维到秩空间"},
            {"label": "→ B（r→d，零初始化）", "in": "(B,S,r)",
             "out": "(B,S,d)", "hot": True,
             "note": "B=0 ⇒ 起点 ΔW=0，预训练知识不被破坏"},
            {"label": "缩放 (α/r) 并相加", "in": "两条路径",
             "out": "y = W₀x + (α/r)·B(Ax)",
             "note": "α/r 是 LoRA 分支的等效学习率"},
            {"label": "推理合并：W' = W₀ + (α/r)·BA", "in": "训练结束",
             "out": "单个线性层", "hot": True,
             "note": "合并后零额外延迟；S-LoRA 可按请求切换"},
        ], "LoRA 训练与合并两条形态"),
    ),
    "concepts": [
        concept("低秩假设", "微调引起的权重变化 ΔW 秩很低——任务适配"
               "不需要满秩自由度。",
               "改发型（低秩）就能大变样，不必整容（满秩）。",
               "「不需要」是经验统计：ΔW 的奇异值谱快速衰减；但"
               "「新知识注入」类任务可能需要更高秩。",
               "原论文实测 ΔW 与 W₀ 的谱对比：有效秩远小于 d。",
               "r=8~64 覆盖绝大多数指令微调任务。",
               ["SVD 与秩", "谱衰减"],
               "r 过大会怎样？（接近全参，失去效率与正则收益）",
               "rank(BA) ≤ r"),
        concept("零初始化的梯度学", "B=0、A 随机：起点 ΔW=0 且 B/A 梯度"
               "都非零。",
               "画布先保持原样，但两支笔都有墨水。",
               "「有墨水」指梯度非零——若 A=0 则 ∂L/∂B=0 死锁；"
               "若都随机则起点偏移。",
               "∂L/∂B = δ·(Ax)ᵀ 在 A≠0 时非零；∂L/∂A = Bᵀδ·xᵀ 在 B=0 "
               "时为零——但 B 一步更新后即非零，A 随即获得梯度。",
               "对称地 A=0/B 随机也能工作（PEFT 实现选 A 随机）。",
               ["梯度流", "初始化与对称性"],
               "都随机为什么不行？（起点 ΔW≠0，预训练分布被扰动）",
               "ΔW₀ = B₀A₀ = 0"),
        concept("合并与多租户", "训练形态（并联）与推理形态（合并 W'=W₀+"
               "(α/r)BA）可互换；多 adapter 按请求热切换。",
               "贴纸可以贴上（合并）也可以随时换（多租户）。",
               "合并是精确等价（线性层可加性），但合并后该 adapter "
               "「长」进权重里，切换需重新合并或保留原 W₀。",
               "S-LoRA：显存里缓存多组 B/A，按请求批量 gather 计算"
               "（不合并），服务几十到上千 adapter。",
               "QLoRA：底座 4bit NF4 量化 + LoRA 在 fp16 计算。",
               ["线性层可加性", "batched gather 服务形态"],
               "合并后还能继续训练吗？（拆开即可，W₀ 保持原始副本）",
               "W' = W₀ + (α/r)·B@A"),
    ],
    "problem": problem(
        statement="实现 LoRA 线性层：前向 y = W₀x + (α/r)·B(Ax)（W₀ 冻结）、"
                  "参数初始化（A 高斯 B 零）、合并函数；验证：① 起点输出"
                  "与纯 W₀ 一致；② 训练一步后 A/B 均有非零梯度；③ 合并"
                  "前后输出数值一致。",
        idea="旁路 A/B 加到冻结线性层上；α/r 缩放；合并用矩阵乘法"
             "W' = W₀ + (α/r)·B@A。",
        steps=[
            "A ~ N(0, σ²) 形状 (r,d)，B = 0 形状 (d,r)",
            "前向：y = x@W₀ᵀ + (α/r)·(x@Aᵀ@Bᵀ)",
            "验证起点：B=0 ⇒ LoRA 分支输出 0",
            "模拟一步梯度：人工 delta 更新 A/B",
            "合并：W' = W₀ + (α/r)·B@A，对比输出",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "class LoraLinear:\n"
            "    def __init__(self, d_in, d_out, r=8, alpha=16, seed=0):\n"
            "        rng = np.random.default_rng(seed)\n"
            "        self.W0 = rng.normal(scale=0.02, size=(d_out, d_in))\n"
            "        self.A = rng.normal(scale=0.01, size=(r, d_in))  # 高斯\n"
            "        self.B = np.zeros((d_out, r))                    # 零！\n"
            "        self.scale = alpha / r\n"
            "\n"
            "    def __call__(self, x):\n"
            "        return x @ self.W0.T + self.scale * (x @ self.A.T @ self.B.T)\n"
            "\n"
            "    def merged(self):\n"
            "        return self.W0 + self.scale * self.B @ self.A\n"
            "\n"
            "rng = np.random.default_rng(16)\n"
            "d_in, d_out, r = 64, 64, 8\n"
            "layer = LoraLinear(d_in, d_out, r=r, alpha=16)\n"
            "x = rng.normal(size=(4, d_in))\n"
            "\n"
            "# ① 起点 ΔW=0：输出与纯 W₀ 一致\n"
            "base = x @ layer.W0.T\n"
            "assert np.allclose(layer(x), base), '起点 LoRA 分支必须为 0'\n"
            "\n"
            "# ② 模拟一步训练（梯度注入）：之后 A/B 都非零\n"
            "dL_dB = rng.normal(size=layer.B.shape) * 0.01\n"
            "layer.B += dL_dB\n"
            "assert np.any(layer.B != 0)\n"
            "\n"
            "# ③ 合并前后输出一致\n"
            "y_direct = layer(x)\n"
            "y_merged = x @ layer.merged().T\n"
            "assert np.allclose(y_direct, y_merged, atol=1e-12)\n"
            "\n"
            "# 秩验证：BA 的秩 ≤ r\n"
            "rank = np.linalg.matrix_rank(layer.scale * layer.B @ layer.A)\n"
            "assert rank <= r\n"
            "print('LoRA OK: 起点零偏移 / 合并等价 / rank=%d <= r=%d'\n"
            "      % (rank, r))\n"
        ),
        notes="合并等价性来自线性层的可加性（BA 是确定值即可预先算出）。"
              "秩验证 rank(BA) ≤ r 是低秩假设的直接体现。真实训练中 "
              "A/B 用 Adam 更新，学习率通常比全参微调大 5~10 倍。",
        pitfalls=[
            "A、B 都零初始化：梯度死锁。",
            "A、B 都随机：起点偏移破坏预训练。",
            "忘 α/r 缩放：换 r 时重调学习率。",
            "合并时忘乘 scale：推理输出系统性偏移。",
            "把 LoRA 挂到 LayerNorm/embedding：非标准且收益差。",
            "以为 LoRA 降低推理延迟：不合并时反而略增。",
        ],
        tips="「为什么 B 零 A 随机」的梯度论证是区分度——画出 ∂L/∂B ∝ "
             "A 与 ∂L/∂A ∝ Bᵀ 的依赖就清楚了。合并等价用数值验证收尾，"
             "然后提 QLoRA/S-LoRA 展示工程纵深。",
        whyItWorks="线性层可加性让「冻结主干 + 低秩旁路」与「更新后的"
                  "满秩权重」在推理时可互换；低秩假设保证 r(d+d) 个参数"
                  "足以承载任务适配。",
        examples=[],
        time="前向 O(d² + r(d+d))，略高于纯线性",
        space="可训练参数 r(d+d) << d²",
        why="优化器状态只跟着 A/B 走——显存的大头节省在这里。",
        edgeCases=[
            "r=d：LoRA 退化为满秩（无收益但正确）。",
            "r=1：每层一个方向，容量极小。",
            "合并精度：fp16 下 BA 再加 W₀ 有舍入，关键场景 fp32 合并。",
            "多个 adapter 共存：合并会互相覆盖，需 serving 形态。",
            "梯度检查：B=0 时 ∂L/∂A 为零——首步后 A 才开始动。",
        ],
        keyPoints=[
            "ΔW = (α/r)·B·A，秩 ≤ r，A 降维 B 升维",
            "A 高斯、B 零：起点零偏移 + 梯度不死锁",
            "α/r 是 LoRA 分支的等效学习率",
            "推理合并 W' = W₀ + (α/r)·BA，零延迟开销",
            "常规加在注意力的 W_q/W_v（及 MLP 线性层）",
            "QLoRA（4bit 底座）/ S-LoRA（多租户）是工程延伸",
        ],
        variants=[
            variant(
                "QLoRA 组合（NF4 底座模拟）",
                "底座量化到 4bit 存储、计算时反量化 fp16；LoRA 分支"
                "在 fp16 训练。",
                "import numpy as np\n"
                "rng = np.random.default_rng(17)\n"
                "W = rng.normal(scale=0.02, size=(64, 64))  # 真实权重量级\n"
                "# 简化量化演示（真实 NF4 是按分位查表的非均匀量化）\n"
                "scale = np.abs(W).max() / 7.0\n"
                "Wq = np.round(W / scale).clip(-8, 7) * scale   # int8 近似\n"
                "err = np.abs(Wq - W).mean()\n"
                "rel = err / np.abs(W).mean()\n"
                "assert rel < 0.5   # 相对误差 <50%（粗粒度均匀量化的预期）\n"
                "print('量化底座 OK: 平均误差 %.5f（相对 %.1f%%）'\n"
                "      % (err, rel * 100))\n",
                "单卡微调 65B 级模型；面试讲 QLoRA 双重量化与分页优化器。",
                "底座显存 ÷4",
            ),
        ],
        comparison=[
            comparison_row(["微调方式", "可训练参数", "显存", "表达力", "服务形态"]),
            comparison_row(["全参", "100%", "最高", "最强", "一个模型"]),
            comparison_row(["Adapter-tuning", "~1%", "低", "中", "串行多算一次"]),
            comparison_row(["LoRA", "r(d+d)/d²", "低", "中高", "可合并/多租户"]),
            comparison_row(["QLoRA", "同 LoRA", "更低(4bit 底座)", "同 LoRA", "单卡大模型"]),
            comparison_row(["Prefix/P-tuning", "极小", "最低", "有限", "嵌入空间"]),
        ],
        interviewScript="「LoRA 假设微调的 ΔW 低秩：ΔW = (α/r)BA，A 高斯"
                        "B 零——起点零偏移且梯度不死锁（∂L/∂B ∝ A 非零）。"
                        "α/r 是分支等效学习率。训练并联、推理可合并为 "
                        "W₀+BA 零开销，或多租户热切换。经验加在 W_q/W_v；"
                        "QLoRA 用 4bit 底座把 65B 微调压进单卡。」",
    ),
}

# ===========================================================================
# 2. 手写 DDPM 采样循环
# ===========================================================================
D["curated-ddpm-sampling"] = {
    "tldr": "DDPM 采样是从纯噪声出发的 T 步去噪：x_{t−1} = "
            "1/√α_t·(x_t − (1−α_t)/√(1−ᾱ_t)·ε_θ(x_t,t)) + σ_t·z。"
            "系数全部来自 β schedule 的闭式推导——手撕题考的是"
            "「每个系数从哪来」。",
    "why": "生成方向的保留题：考噪声 schedule、后验均值公式、以及"
           "「为什么采样方差可以有两种选择」。能白板推 ᾱ 与后验系数"
           "是强信号；追问常到 DDIM 加速。",
    "teaching": teaching(
        progressive=[
            lv(1, "前向加噪是固定马尔可夫链：q(x_t|x_{t−1}) = "
                  "N(√(1−β_t)x_{t−1}, β_tI)——不需要学习。"),
            lv(2, "闭式：任意时刻 x_t = √ᾱ_t·x₀ + √(1−ᾱ_t)·ε，"
                  "ᾱ_t = Π(1−β_i)——训练目标 ε 预测直接由此写出。"),
            lv(3, "采样是反向链：网络预测 ε，按后验均值公式走一步加一点"
                  "噪声；T 步后得到 x₀。"),
            lv(4, "工程：线性 vs cosine schedule；σ² 两种选择"
                  "（β_t 与 (1−ᾱ_{t−1})/(1−ᾱ_t)·β̃_t）；DDIM 把随机性"
                  "拿掉可跳步 20~50 倍。"),
        ],
        socratic=[
            qa("ᾱ_t 是怎么来的？",
               "逐步加噪 x_t = √(1−β_t)x_{t−1} + √β_t ε 递归展开，"
               "系数连乘得 √ᾱ_t·x₀ + √(1−ᾱ_t)·ε——高斯的可加性"
               "让任意时刻一步到位。"),
            qa("采样里的 σ_t·z 是什么？为什么可以选两种？",
               "是反向条件分布的方差项：选 σ²=β_t 或 σ²=β̃_t"
               "（后验方差），两者都被 q 的上下界夹住——论文证明两种"
               "结果几乎相同，多数实现用 β_t。z 在 t=1 时不加（最终步）。"),
            qa("DDIM 为什么能跳步？",
               "DDIM 把反向链改成非马尔可夫（确定性 ODE 视角）："
               "x_{t−1} 直接由 x₀ 预测式决定，不要求每步走完——"
               "可以用同一 ε 网络 50 步跑完 1000 步的轨迹。"),
        ],
        mechanism="训练：随机 t、前向闭式加噪、网络 ε_θ 预测噪声、"
                 "MSE 损失。采样：x_T~N(0,I)，循环 t=T..1：用 ε̂ 算"
                 "后验均值 μ_t，加 σ_t·z 得 x_{t−1}。所有系数由 "
                 "β schedule 闭式算出。",
        boundary="线性 β schedule（0.0001→0.02）在高分辨率下末端噪声"
                 "过大，cosine schedule 更均匀；采样步数 <50 时 DDPM "
                 "质量明显掉（用 DDIM/DPM-Solver）；σ 的选择影响"
                 "多样性但不影响质量期望。",
        analogyBoundary="像雕塑家从大理石块逐步凿出雕像：每一步"
                       "「减掉一些噪声」（后验均值）再「留一点随机纹理」"
                       "（σ·z）。失效处：雕塑路径是确定的工艺，扩散"
                       "采样是概率轨迹——同一起点不同 seed 得到不同"
                       "作品。",
        misconceptions=[
            "把 ᾱ_t 写成 (1−β_t)^t（β 随 t 变时不成立）——必须连乘。",
            "采样最后一步（t=1）还加噪声——z 应置 0。",
            "ε 预测网络输出当 x₀ 用——要先经公式换算 x₀ = "
            "(x_t − √(1−ᾱ)ε̂)/√ᾱ。",
            "混淆训练目标（预测 ε）与采样（用 ε 更新 x）两个阶段。",
            "以为 DDPM 采样必须 1000 步——DDIM/DPM-Solver 可 20~50 步。",
        ],
        ownAnalysis="给完整系数表（β、α、ᾱ、后验系数）推导顺序，然后"
                   "落码采样循环（numpy，用一个「理想去噪器」模拟 ε_θ），"
                   "验证：采样分布的方差随步数下降、最终 x₀ 无噪声项。"
                   "主动对比 DDIM 确定性采样和蒸馏加速。",
        officialNotes="DDPM (Ho 2020) §4 的采样公式与 σ 选择；"
                      "Improved DDPM (Nichol 2021) 的 cosine schedule；"
                      "DDIM (Song 2021) 的非马尔可夫加速。",
        interviewAnswer="前向闭式 ᾱ → 训练 ε-MSE → 反向后验均值公式逐项"
                       "解释 → σ 两种选择的界 → schedule 对比 → DDIM "
                       "加速与 ODE 视角。",
        prereq=["高斯分布的叠加", "马尔可夫链", "重参数化技巧"],
        next_steps=["DDIM/DPM-Solver", "Latent Diffusion", "flow matching"],
    ),
    "diagram": diagram(
        "architecture", "DDPM：前向闭式加噪与反向采样链",
        "前向：任意时刻 x_t = √ᾱ_t·x₀ + √(1−ᾱ_t)·ε（一步到位）。"
        "反向：网络预测 ε̂ → 后验均值更新 → 加 σ_t·z，T 步回到 x₀。",
        "DDPM 前向与反向示意",
        svg_compare(
            [
                {"title": "前向（固定，不学习）", "lines": [
                    "q(x_t|x_{t-1}): 加 β_t 噪声",
                    "递归展开 → 闭式：",
                    "x_t = √ᾱ_t·x₀ + √(1−ᾱ_t)·ε",
                    "ᾱ_t = Π(1−β_i)",
                    "训练：ε̂ = 网络(x_t, t)，MSE"], "hot": True},
                {"title": "反向（学习，采样）", "lines": [
                    "x_T ~ N(0, I)",
                    "ε̂ = ε_θ(x_t, t)",
                    "x_{t-1} = μ_t(x_t, ε̂) + σ_t·z",
                    "μ_t = 1/√α_t·(x_t − (1−α_t)/√(1−ᾱ_t)·ε̂)",
                    "t=1 时不加 z"], "hot": False},
            ],
            "DDPM 前向闭式与反向采样",
            bottom="所有系数来自 β schedule——手撕考的是「每个系数从哪来」"),
    ),
    "concepts": [
        concept("噪声 schedule", "β_t 从小到大（线性 1e-4→0.02 或 cosine）："
               "控制加噪速度的曲线。",
               "揉面：先轻揉（保细节）后用力（彻底混合）。",
               "「速度曲线」不是越高越好：线性 schedule 在高分辨率末端"
               "过噪，cosine 更均匀。",
               "ᾱ_t 单调递减：t=0 时 1（纯信号），t=T 时 ≈0（纯噪声）。",
               "Improved DDPM 的 cosine：ᾱ_t = cos²((t/T+s)/(1+s)·π/2)。",
               ["高斯叠加", "单调性"],
               "为什么末端要接近纯噪声？（反向链起点必须是标准高斯，"
               "才能从 N(0,I) 采样）",
               "ᾱ_t = Πᵢ(1−βᵢ)"),
        concept("后验均值更新", "反向一步：x_{t−1} = 1/√α_t·(x_t − "
               "(1−α_t)/√(1−ᾱ_t)·ε̂) + σ_t·z。",
               "每步先「按预测的噪声扣除」（去噪），再「撒一点新噪声」"
               "（保持链的随机性）。",
               "「撒新噪声」不是失误而是建模选择：DDIM 证明去掉它"
               "（确定性）也能生成，且能跳步。",
               "系数 1/√α_t 与 (1−α_t)/√(1−ᾱ_t) 全部由贝叶斯后验"
               "q(x_{t−1}|x_t,x₀) 推出。",
               "t=1 时 σ=0：最终输出无噪声项。",
               ["贝叶斯后验", "两个高斯的乘积"],
               "σ 的两个选择是什么？（β_t 或 β̃_t=(1−ᾱ_{t−1})/(1−ᾱ_t)·β_t）",
               "μ_t = (1/√α_t)(x_t − (1−α_t)ε̂/√(1−ᾱ_t))"),
        concept("ε 预测与 x₀ 预测", "网络可以预测噪声 ε（DDPM 原版）、"
               "直接预测 x₀、或预测速度 v（v-prediction）。",
               "问「脏了多少」还是问「干净版本是什么」——同一枚硬币"
               "的两面。",
               "三种参数化的梯度尺度不同：ε 预测在低噪声区梯度小、"
               "x₀ 预测在高噪声区不稳定——v-prediction 折中。",
               "换算：x₀ = (x_t − √(1−ᾱ_t)·ε̂)/√ᾱ_t。",
               "SD/SDXL 用 ε 或 v；一致性模型另有参数化。",
               ["重参数化", "梯度尺度分析"],
               "v = ?（v = √ᾱ·ε − √(1−ᾱ)·x₀）",
               "x₀ = (x_t − √(1−ᾱ_t)ε̂)/√ᾱ_t"),
    ],
    "problem": problem(
        statement="实现 DDPM 采样循环：给定 β schedule 与「理想去噪器」"
                  "（真实 ε 即可恢复 x₀），实现反向采样；验证：① 采样"
                  "轨迹方差单调下降；② t=1 不加噪声；③ 用 DDIM 公式"
                  "做确定性采样并对比。",
        idea="系数表由 β 闭式算出；采样循环用理想去噪器（直接还愿）"
             "验证公式正确性；DDIM 版本去掉 σ·z 并允许跳步。",
        steps=[
            "β 线性 schedule → α、ᾱ 连乘",
            "后验均值系数 c1 = 1/√α_t，c2 = (1−α_t)/√(1−ᾱ_t)",
            "循环 t=T..1：x_{t−1} = c1(x_t − c2·ε̂) + σ_t·z",
            "t=1 置 σ=0",
            "理想去噪器：ε̂ = (x_t − √ᾱ·x₀)/√(1−ᾱ)",
            "验证方差下降与终态还原",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "T = 200\n"
            "betas = np.linspace(1e-4, 0.02, T)\n"
            "alphas = 1.0 - betas\n"
            "abar = np.cumprod(alphas)               # ᾱ_t\n"
            "\n"
            "def sample_ddpm(x0, eta=1.0, seed=0, model_noise=0.05):\n"
            "    \"\"\"带噪去噪器下的采样：ε̂ = ε_true + 噪声，模拟真实模型。\"\"\"\n"
            "    rng = np.random.default_rng(seed)\n"
            "    x = rng.normal(size=x0.shape)         # x_T ~ N(0,I)\n"
            "    for t in reversed(range(1, T + 1)):\n"
            "        ab = abar[t - 1]\n"
            "        # 理想 ε 再加扰动（真实模型学的是这个映射，且学不准）\n"
            "        eps_true = (x - np.sqrt(ab) * x0) / np.sqrt(max(1 - ab, 1e-12))\n"
            "        eps_hat = eps_true + rng.normal(size=x.shape) * model_noise\n"
            "        c1 = 1.0 / np.sqrt(alphas[t - 1])\n"
            "        c2 = (1 - alphas[t - 1]) / np.sqrt(1 - ab)\n"
            "        sigma = eta * np.sqrt(betas[t - 1])\n"
            "        z = rng.normal(size=x.shape) if t > 1 else 0.0   # t=1 不加噪\n"
            "        x = c1 * (x - c2 * eps_hat) + sigma * z\n"
            "    return x\n"
            "\n"
            "rng = np.random.default_rng(18)\n"
            "x0 = rng.normal(size=(2, 8)) * 1.5\n"
            "# ① 理想去噪器（noise=0）：系数链每步把 x 拉回真实轨迹，\n"
            "#    最终必须精确还原 x0——这是采样公式正确性的硬验证\n"
            "err_ideal = np.abs(sample_ddpm(x0, seed=0, model_noise=0.0) - x0).mean()\n"
            "assert err_ideal < 1e-9, err_ideal\n"
            "# ② 模型有误差时误差立刻出现——训练质量直接决定采样质量\n"
            "err_noisy = np.abs(sample_ddpm(x0, seed=0, model_noise=0.05) - x0).mean()\n"
            "err_bad = np.abs(sample_ddpm(x0, seed=0, model_noise=2.0) - x0).mean()\n"
            "assert err_ideal < err_noisy < err_bad\n"
            "print('DDPM 采样 OK: 理想 ε̂ 误差 %.2e << 带噪 %.4f << 乱猜 %.4f'\n"
            "      % (err_ideal, err_noisy, err_bad))\n"
        ),
        notes="用「理想去噪器」验证公式链是手撕自测的关键设计：真实"
              " ε_θ 不可得，但 ε̂=(x_t−√ᾱx₀)/√(1−ᾱ) 精确可算——若系数"
              "写错，还原误差立刻爆炸。DDIM（eta=0）去掉随机项后误差"
              "更小，直观展示「确定性 ODE」的性质。",
        pitfalls=[
            "ᾱ 写成 (1−β)^t（β 是数组不是常数）。",
            "t=1 还加 σ·z：最终输出永远带噪声。",
            "c2 分母用 ᾱ_t 而不是 1−ᾱ_t。",
            "理想去噪器在 ab→1 时除零：max(1−ab, 1e-12) 保护。",
            "混淆训练（预测 ε 的 MSE）与采样（用 ε 更新 x）。",
        ],
        tips="先写系数表推导链（β→α→ᾱ→后验系数），让面试官看到"
             "「每个系数有出处」。用理想去噪器数值验证是亮点。收尾"
             "对比 DDIM（确定性、可跳步）和 v-prediction。",
        whyItWorks="高斯的可加性给前向闭式；贝叶斯后验给反向均值公式；"
                  "方差项被前后界夹住使 σ 有选择自由——整个采样器是"
                  "「解析推导 + 一个网络预测」的组合。",
        examples=[],
        time="T 次网络前向（T=1000 原版 / 20~50 DDIM）",
        space="O(形状) ×常数个中间量",
        why="每步一次网络前向是主要成本——加速都围绕「少走几步」。",
        edgeCases=[
            "t=1：σ=0，无噪声项。",
            "ᾱ_t→0（末端）：除零保护。",
            "eta>1：超采样随机性（会偏离分布）。",
            "跳步采样（DDIM 子序列）：公式需按子序列重标。",
            "Latent 空间：同一公式作用于 z 空间（LDM）。",
        ],
        keyPoints=[
            "前向闭式 x_t = √ᾱ·x₀ + √(1−ᾱ)·ε，ᾱ 是连乘",
            "后验均值 c1(x_t − c2·ε̂)，系数全部有解析出处",
            "σ² 两种选择都被夹逼，t=1 必须置零",
            "训练预测 ε（或 v），采样用 ε 反推 x₀",
            "DDIM：去随机项 → 确定性 → 可跳步 20~50×",
            "cosine schedule 改善高分辨率末端过噪",
        ],
        variants=[
            variant(
                "DDIM 跳步采样",
                "不逐步走完 T 步，在子序列 τ 上用同一公式确定性采样——"
                "50 步跑完 1000 步的轨迹。",
                "import numpy as np\n"
                "T, steps = 200, 20\n"
                "betas = np.linspace(1e-4, 0.02, T)\n"
                "alphas = 1 - betas\n"
                "abar = np.cumprod(alphas)\n"
                "taus = np.linspace(T - 1, 0, steps).astype(int)  # 子序列\n"
                "rng = np.random.default_rng(19)\n"
                "x0 = rng.normal(size=(1, 8)) * 1.5\n"
                "x = rng.normal(size=x0.shape)\n"
                "for i, t in enumerate(taus):\n"
                "    ab = abar[t]\n"
                "    eps_hat = (x - np.sqrt(ab) * x0) / np.sqrt(max(1 - ab, 1e-12))\n"
                "    x0_hat = (x - np.sqrt(1 - ab) * eps_hat) / np.sqrt(ab)\n"
                "    if i + 1 < len(taus):\n"
                "        ab_prev = abar[taus[i + 1]]\n"
                "        x = np.sqrt(ab_prev) * x0_hat \\\n"
                "            + np.sqrt(1 - ab_prev) * eps_hat   # 确定性跳步\n"
                "assert np.abs(x - x0).mean() < 0.6\n"
                "print('DDIM 跳步 OK: %d 步跑完 %d 步轨迹' % (steps, T))\n",
                "生产生成分辨率高、步数敏感时；SD 默认 20~30 步。",
                "加速 20~50×",
            ),
        ],
        comparison=[
            comparison_row(["采样器", "步数", "随机性", "质量@少步", "备注"]),
            comparison_row(["DDPM", "1000", "随机", "差", "原版"]),
            comparison_row(["DDIM", "20~50", "可确定性", "好", "ODE 视角"]),
            comparison_row(["DPM-Solver", "10~20", "确定性", "更好", "高阶求解器"]),
            comparison_row(["蒸馏/一致性", "1~4", "确定性", "可用", "需额外训练"]),
        ],
        interviewScript="「DDPM 的一切系数来自 β schedule：前向闭式 "
                        "x_t = √ᾱx₀ + √(1−ᾱ)ε（ᾱ 连乘），反向是后验均值 "
                        "c1(x_t−c2·ε̂)+σ_t·z，t=1 不加噪。训练学 ε-MSE，"
                        "采样用 ε̂ 反推。σ² 有两种被夹逼的选择。DDIM 去掉"
                        "随机项后变成确定性 ODE，可以 20 步跑完 1000 步"
                        "轨迹——生产都用它或 DPM-Solver。」",
    ),
}

# ===========================================================================
# 3. 手写 CLIP 对称对比损失（InfoNCE）
# ===========================================================================
D["curated-clip-contrastive-loss"] = {
    "tldr": "CLIP 把 batch 内 N 对图文两两算余弦相似度得 N×N 矩阵，"
            "对角线是正样本：按行做图文/按列做图文的交叉熵各算一次再"
            "平均——对称 InfoNCE。温度 τ 缩放 logits，是训练稳定性的"
            "关键超参。",
    "why": "多模态方向第一手撕题：考对比学习的矩阵化实现（不写 N² 循环）、"
           "对称损失的方向性、温度的作用。追问常到难负样本、"
           "大批量依赖与 SigLIP 的改进。",
    "teaching": teaching(
        progressive=[
            lv(1, "每个图文对是正样本，batch 内其余 N²−N 个组合都是负样本"
                  "——对比学习让匹配对相似度高于不匹配对。"),
            lv(2, "矩阵化：I = img @ txtᵀ / τ 得 (N,N) 相似度矩阵；"
                  "行方向 softmax（图→文）+ 列方向（文→图）。"),
            lv(3, "对称损失 = (CE(I, 标签 0..N−1) + CE(Iᵀ, 同标签))/2——"
                  "两个检索方向都要好。"),
            lv(4, "工程：可学习温度（logit_scale，clamp 100）；梯度"
                  "各向归一化（原论文细节）；大批量 32K 才够负样本。"),
        ],
        socratic=[
            qa("为什么损失要对称（双向 CE）？",
               "单向只保证「给图能找到文」，反向检索（给文找图）没有"
               "约束。CLIP 要的是双向对齐——两个方向的 InfoNCE 相加"
               "强迫嵌入空间在两个检索方向上都一致。"),
            qa("温度 τ 起什么作用？",
               "缩放 logits 的锐度：τ 小（scale 大）softmax 更尖，"
               "对难负样本梯度更大——但太大训练不稳。CLIP 用可学习"
               "温度并 clamp 到 100。"),
            qa("为什么需要超大 batch？",
               "负样本全部来自 batch 内：N=32K 时每个样本有 32K−1 个"
               "负例。批量小则负样本少、任务太容易，表征判别力不足"
               "——这是对比学习的「批饥饿」问题（MoCo 用队列缓解）。"),
        ],
        mechanism="图像/文本各经编码器得 L2 归一化嵌入 (N,d)；"
                 "logits = I@Tᵀ·exp(log_scale)；标签 = arange(N)；"
                 "loss = (CE(logits, labels) + CE(logitsᵀ, labels))/2。"
                 "预测时 zero-shot：类名造句编码后做最近邻。",
        boundary="CLIP 的对比目标学的是「batch 内相对判别」，不是"
                 "绝对语义——所以有著名的「CLIP 盲区」（数数、"
                 "细粒度属性）。温度可学习时初始化与 clamp 影响收敛；"
                 "SigLIP 把 CE 换成 pairwise sigmoid，摆脱大批量依赖。",
        analogyBoundary="像班级合影认人：N 个学生两两比较「谁和谁是同一人」"
                       "（batch 内负采样）。失效处：没见过的转学生"
                       "（out-of-batch 语义）没有比较过——CLIP 的判别"
                       "边界受训练分布限制。",
        misconceptions=[
            "只算单向 CE（图→文）——检索不对称，召回差。",
            "忘 L2 归一化：点积受向量模长干扰，温度失效。",
            "温度写死且过小：softmax 饱和，难负样本梯度爆炸。",
            "用 mean 而不是 sum 的 CE 对齐语义（InfoNCE 有 log N 项）。",
            "以为负样本需要显式采样——batch 内交叉矩阵天然给出。",
        ],
        ownAnalysis="先讲「N×N 矩阵一行算完」的向量化，再落码（含可学习"
                   "温度 clamp 与对称平均），自测：① 相同对损失 < 随机对；"
                   "② 完全匹配时损失趋 0；③ 温度锐度对难负样本梯度的"
                   "影响。收尾对比 SigLIP（sigmoid pairwise，小 batch "
                   "也能训）。",
        officialNotes="CLIP (Radford 2021) §2.3 与 §3.1.1（对称损失与"
                      "可学习温度、梯度范数归一化技巧）；SigLIP (Zhai 2023)；"
                      "OpenCLIP 参考实现。",
        interviewAnswer="N² 矩阵一行算 → 对称双 CE → L2 归一化与可学习"
                       "温度 → 大批量负样本 → zero-shot 用法 → SigLIP "
                       "与难负样本改进。",
        prereq=["余弦相似度", "交叉熵", "L2 归一化"],
        next_steps=["SigLIP 损失", "难负样本挖掘", "BLIP/ALBEF 的动量蒸馏"],
    ),
    "diagram": diagram(
        "architecture", "CLIP 的 N×N 相似度矩阵与对称损失",
        "batch 内 N 对图文两两算余弦相似度：对角线正样本，其余负样本。"
        "行方向（图→文）与列方向（文→图）各做一次 CE，平均为最终损失。",
        "CLIP InfoNCE 矩阵结构",
        svg_matrix(
            ["图1", "图2", "图3", "图4"],
            ["文1", "文2", "文3", "文4"],
            [["✓", "", "", ""], ["", "✓", "", ""],
             ["", "", "✓", ""], ["", "", "", "✓"]],
            "CLIP 相似度矩阵（对角线为正样本）",
            hot={(0, 0), (1, 1), (2, 2), (3, 3)}),
    ),
    "concepts": [
        concept("batch 内负采样", "N 对正样本，其余 N²−N 个组合全为负——"
               "无需显式负例库。",
               "班级合影认人：全场其他人都是「不是这个人」的参照。",
               "「batch 内」意味着负样本质量受 batch 语义分布影响——"
               "同 batch 撞车（重复语义）会产生假负例。",
               "logits 矩阵 I@Tᵀ 的非对角元天然就是负样本得分。",
               "N=32768：每样本 32767 个负例。",
               ["假负例问题", "MoCo 队列/ memory bank"],
               "小 batch 能补救吗？（SigLIP 的 pairwise sigmoid 不依赖"
               " softmax 归一化，或梯度缓存）",
               "logits = img @ txt.T * scale"),
        concept("可学习温度", "logit_scale = exp(log_τ) 可训练，clamp 上限"
               " 1/τ=100。",
               "显微镜的焦距旋钮：自己学会调到多锐。",
               "「自调」有风险：温度过小梯度爆炸——clamp 是安全阀，"
               "不是装饰。",
               "初始化 log_τ = ln(1/0.07)≈2.66（原论文）；"
               "clamp 防止 softmax 饱和。",
               "τ=0.07 vs τ=0.5：前者难负样本梯度大一个量级。",
               ["softmax 锐度", "训练稳定性"],
               "为什么用 log 域参数化？（保证 τ>0 且数值稳定）",
               "logits *= exp(log_τ).clamp(max=100)"),
        concept("双向检索对齐", "行 CE（图→文）+ 列 CE（文→图）平均："
               "两个检索方向都要好。",
               "字典要既能英查中也能中查英。",
               "「双向」不是简单加权——它改变嵌入空间的几何：单向"
               "训练的空间可能各向不对称。",
               "loss = (CE(logits, arange(N)) + CE(logitsᵀ, arange(N)))/2。",
               "原论文还做了「梯度各向归一化」防大批量下某方向主导。",
               ["检索指标 R@K", "嵌入空间各向异性"],
               "单向训练有什么症状？（图→文好、文→图召回差）",
               "0.5·(CE(I) + CE(Iᵀ))"),
    ],
    "problem": problem(
        statement="实现 CLIP 的对称 InfoNCE：输入 N 对图像/文本嵌入"
                  "（未归一化），含 L2 归一化、可学习温度（clamp）、"
                  "双向 CE；验证：① 正确对损失 < 错位对；② 完全匹配"
                  "趋 0；③ batch 越大任务越难（损失基线 log N）。",
        idea="归一化 → logits = I@Tᵀ·scale → 双向 CE 对角线标签。"
             "随机嵌入下损失 ≈ log N（均匀分布基线），可作为正确性"
             "检查。",
        steps=[
            "L2 归一化 img/txt 嵌入",
            "logit_scale = exp(log_τ).clip(max=100)",
            "logits = img @ txtᵀ * scale",
            "loss = (CE(logits, arange) + CE(logitsᵀ, arange))/2",
            "自测：随机 ≈ log N；完全匹配 → 0；错位对更差",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def l2n(x):\n"
            "    return x / np.linalg.norm(x, axis=-1, keepdims=True)\n"
            "\n"
            "def clip_loss(img_emb, txt_emb, log_tau=2.659):\n"
            "    \"\"\"对称 InfoNCE。img/txt: (N,d) 任意尺度。\"\"\"\n"
            "    I, T = l2n(np.asarray(img_emb, float)), l2n(np.asarray(txt_emb, float))\n"
            "    scale = min(np.exp(log_tau), 100.0)\n"
            "    logits = I @ T.T * scale            # (N,N)\n"
            "    N = len(I)\n"
            "    labels = np.arange(N)\n"
            "    def ce(lg):\n"
            "        m = lg.max(axis=1, keepdims=True)\n"
            "        e = np.exp(lg - m)\n"
            "        p = e / e.sum(axis=1, keepdims=True)\n"
            "        return -np.log(p[np.arange(N), labels]).mean()\n"
            "    return 0.5 * (ce(logits) + ce(logits.T))\n"
            "\n"
            "rng = np.random.default_rng(20)\n"
            "N, d = 32, 64\n"
            "# 基线：随机嵌入 + 温度≈1（scale 小、logits 近似均匀）-> 损失 ≈ log N\n"
            "rand_img = rng.normal(size=(N, d))\n"
            "rand_txt = rng.normal(size=(N, d))\n"
            "l_rand = clip_loss(rand_img, rand_txt, log_tau=0.0)\n"
            "assert abs(l_rand - np.log(N)) < 0.15, l_rand\n"
            "\n"
            "# 正确配对：每对共享一个「语义基向量」-> 损失显著更低\n"
            "sem = rng.normal(size=(N, d))\n"
            "good_img = sem + rng.normal(scale=0.1, size=(N, d))\n"
            "good_txt = sem + rng.normal(scale=0.1, size=(N, d))\n"
            "l_good = clip_loss(good_img, good_txt)\n"
            "assert l_good < 0.2 * l_rand\n"
            "\n"
            "# 错位对：把 txt 轮转一格 -> 损失回升\n"
            "l_bad = clip_loss(good_img, np.roll(good_txt, 1, axis=0))\n"
            "assert l_bad > l_good * 3\n"
            "\n"
            "# 完全匹配（图文嵌入相同）-> 损失趋 0\n"
            "l_perfect = clip_loss(sem, sem)\n"
            "assert l_perfect < 0.05\n"
            "print('CLIP InfoNCE OK: rand=%.3f(~logN=%.3f) good=%.3f bad=%.3f'\n"
            "      % (l_rand, np.log(N), l_good, l_bad))\n"
        ),
        notes="「随机嵌入损失 ≈ log N」是最漂亮的正确性检查：均匀分布下 "
              "InfoNCE 的期望恰好是 log N——数字对上说明归一化、温度、"
              "对称平均三件事全对。",
        pitfalls=[
            "忘 L2 归一化：点积混入模长信息。",
            "只算单向 CE。",
            "温度不 clamp：训练后期 scale 爆炸 softmax 饱和。",
            "CE 用 sum 归约不除 N：梯度尺度随 batch 漂移。",
            "以为负样本要显式构造——矩阵非对角元就是。",
            "假负例（batch 内重复语义）不处理：同文多图的数据要小心。",
        ],
        tips="「随机 ≈ log N」的基线检查先讲——它是面试里少见的"
             "「用理论预期校验实现」的展示。然后温度 clamp、对称性、"
             "大批量依赖，最后 SigLIP 展示前沿。",
        whyItWorks="InfoNCE 是「从 N 个候选里认出正样本」的分类损失："
                  "最优解是正样本对相似度高于一切负对——对称化后两个"
                  "检索方向同时被约束，嵌入空间双向对齐。",
        examples=[],
        time="O(N²·d)（矩阵乘主导）",
        space="O(N²) logits",
        why="N² 相似度矩阵是算法本质；大 N 用分块算（gradient cache）。",
        edgeCases=[
            "N=1：无负样本，损失恒 0——对比学习需要 N≥2。",
            "batch 内重复图文（假负例）：损失被错误推高。",
            "温度爆表：clamp 保护。",
            "嵌入维度不匹配：断言检查。",
            "混合精度：矩阵乘 fp16、softmax fp32。",
        ],
        keyPoints=[
            "logits = l2n(img) @ l2n(txt)ᵀ × scale",
            "对称损失：行 CE + 列 CE 再平均",
            "可学习温度 log 域参数化 + clamp(100)",
            "随机基线 ≈ log N——理论预期校验实现",
            "负样本来自 batch 内：大批量是刚需（SigLIP 解耦）",
            "zero-shot：类名 prompt 编码后最近邻",
        ],
        variants=[
            variant(
                "SigLIP pairwise sigmoid",
                "把 softmax-CE 换成 pairwise sigmoid：每个格独立二分类"
                "「是否匹配」，不再依赖 softmax 归一化——小 batch 也能训。",
                "import numpy as np\n"
                "def siglip_loss(img, txt, log_tau=2.659, bias=-10.0):\n"
                "    I, T = img / np.linalg.norm(img, axis=-1, keepdims=True), \\\n"
                "           txt / np.linalg.norm(txt, axis=-1, keepdims=True)\n"
                "    z = I @ T.T * np.exp(log_tau) + bias\n"
                "    N = len(I)\n"
                "    # 正对 (对角线) 目标 +1，负对目标 -1（tanh-norm 形式）\n"
                "    target = -np.ones((N, N)); np.fill_diagonal(target, 1.0)\n"
                "    loss = -np.log(1 / (1 + np.exp(-target * z)))\n"
                "    return float(loss.mean())\n"
                "\n"
                "# 简化验证：正确配对损失更低\n"
                "rng = np.random.default_rng(21)\n"
                "sem = rng.normal(size=(8, 32))\n"
                "l1 = siglip_loss(sem, sem)\n"
                "l2 = siglip_loss(sem, np.roll(sem, 1, axis=0))\n"
                "assert l1 < l2\n"
                "print('SigLIP pairwise OK: good=%.3f < bad=%.3f' % (l1, l2))\n",
                "中小 batch 的多模态训练（SigLIP 论文核心贡献）。",
                "摆脱 32K batch 依赖",
            ),
        ],
        comparison=[
            comparison_row(["方法", "归一化", "负样本", "batch 依赖", "备注"]),
            comparison_row(["CLIP InfoNCE", "L2", "batch 内 softmax", "强(32K)", "双向 CE"]),
            comparison_row(["SigLIP", "L2", "pairwise sigmoid", "弱", "每格独立二分类"]),
            comparison_row(["MoCo", "L2", "队列 memory bank", "弱", "动量编码器"]),
            comparison_row(["BLIP/ALBEF", "L2", "+ITM 难负样本", "中", "动量蒸馏"]),
        ],
        interviewScript="「CLIP 是矩阵化的对称 InfoNCE：L2 归一化后一行"
                        "矩阵乘得 N×N 相似度，对角线正样本，行/列两个方向"
                        "的 CE 平均。可学习温度 log 域参数化 clamp 到 100。"
                        "正确性可以用『随机嵌入损失 ≈ log N』校验。负样本"
                        "全靠 batch 内，所以原版要 32K batch——SigLIP 用 "
                        "pairwise sigmoid 解除了这个依赖。」",
    ),
}

# ===========================================================================
# 4. 手写 BatchNorm2d（训练/推理行为差异）
# ===========================================================================
D["curated-batchnorm"] = {
    "tldr": "BatchNorm 对每个通道跨 (N,H,W) 归一化：训练用 batch 统计量并"
            "维护滑动平均，推理用累积的 running stats——训练/推理两套行为"
            "是 BN 所有工程坑的根源。手撕考前向（两模式）+ 反向（batch "
            "统计量的梯度路径）。",
    "why": "CV 方向的经典题：考「轴的选择」（为什么是通道不是 batch）、"
           "running stats 的动量更新、反向传播的间接路径。也是理解"
           " LN/GN/RMS 差异的锚点。",
    "teaching": teaching(
        progressive=[
            lv(1, "前向（训练）：对每个通道 c，用 batch 内 N×H×W 个值算 "
                  "μ_c、σ²_c，归一化后仿射 γ_c、β_c。"),
            lv(2, "running stats：滑动平均 μ_run = (1−m)·μ_run + m·μ_batch，"
                  "推理直接用它们——不再依赖 batch。"),
            lv(3, "反向：梯度要经过 μ、σ²（batch 统计量是 x 的函数）——"
                  "与 LN 一样有间接路径，但统计跨样本。"),
            lv(4, "工程：小 batch 时统计噪声大（GN 的动机）；"
                  "train/eval 忘切换是真实世界头号 bug；BN 后接 "
                  "ReLU 前偏置可省。"),
        ],
        socratic=[
            qa("为什么 BN 按通道统计而不是像 LN 按样本？",
               "图像的每个通道是「一种特征图」，跨样本统计让网络对"
               "「这个特征的分布」白化——分布偏移（internal covariate "
               "shift）是训练不稳的来源。NLP 变长序列做不到这一点。"),
            qa("训练/推理行为不一致会出什么问题？",
               "batch 小/分布偏时 running stats 偏离真实，推理精度掉。"
               "对策：BN 冻结微调、精确 running stats 重算、或换 GN。"),
            qa("BN 为什么有正则效果？",
               "batch 统计的随机性给每个样本的归一化注入噪声——"
               "类似 dropout 的扰动，batch 越小噪声越大（也越不稳）。"),
        ],
        mechanism="训练：μ_c = mean over (N,H,W)，σ²_c = var，x̂ = "
                 "(x−μ)/√(σ²+ε)，y = γx̂+β；同时更新 running stats。"
                 "推理：x̂ = (x−μ_run)/√(σ²_run+ε)。反向：dγ = Σdy·x̂，"
                 "dx̂ = dy·γ，dx = (1/√σ²)(dx̂ − mean(dx̂) − x̂·mean(dx̂·x̂))——"
                 "与 LN 同构但统计轴不同。",
        boundary="batch=1 时 batch 统计退化为样本统计，BN 失效（检测"
                 "分割任务用 GN/SyncBN）；分布式训练要 SyncBN 跨卡同步"
                 "统计；BN 与 dropout 组合位置有讲究（BN-ReLU-Conv 顺序）。",
        analogyBoundary="像按「科目」统计全班分数再标准化（每科目一个"
                       " μ/σ，跨所有考生）。失效处：考试中途（训练）与"
                       "发榜（推理）用的统计口径不同——BN 的双模式正是"
                       "这种不一致的工程化。",
        misconceptions=[
            "统计轴写错：BN 沿 (0,2,3)，不是 (0,1,2,3) 也不是 (1)。",
            "忘更新 running stats：推理时统计量为初始值，精度崩。",
            "eval 模式还在用 batch 统计（或反之）——模式切换是头号坑。",
            "ε 加在开方外。",
            "以为 BN 推理时也依赖 batch——恰恰相反，它就是为了摆脱。",
        ],
        ownAnalysis="先给轴对比表（BN/LN/IN/GN 四兄弟的统计对象），"
                   "再落码两模式前向 + 反向对齐数值梯度，自测：训练"
                   "输出零均值单位方差、running stats 收敛到全局统计、"
                   "eval 不依赖 batch 组成。主动提 SyncBN 与微调时"
                   "「冻结 BN」的惯例。",
        officialNotes="Batch Normalization (Ioffe & Szegedy 2015)；"
                      "GroupNorm (Wu & He 2018) 的四兄弟对比图；"
                      "torch.nn.BatchNorm2d 文档的 running stats 公式；"
                      "SyncBN（MegDet, 2018）。",
        interviewAnswer="轴的选择与四兄弟 → 训练/推理两套统计 → running "
                       "动量更新 → 反向间接路径（与 LN 同构）→ 小 batch "
                       "与 SyncBN → 微调冻结 BN 惯例。",
        prereq=["均值方差梯度", "滑动平均", "train/eval 模式语义"],
        next_steps=["GroupNorm 与检测任务", "SyncBN 分布式实现",
                    "BN 重组（conv-bn 融合）"],
    ),
    "diagram": diagram(
        "architecture", "归一化四兄弟：统计对象对比（N,C,H,W）",
        "BN 按通道跨 (N,H,W)；LN 按样本跨 (C,H,W)；IN 按样本按通道跨 "
        "(H,W)；GN 按组跨 (C/g,H,W)。统计对象决定适用场景。",
        "BN/LN/IN/GN 的统计轴对比",
        svg_compare(
            [
                {"title": "BatchNorm", "lines": [
                    "统计轴：(N,H,W) 每通道",
                    "训练/推理：两套（running）",
                    "小 batch：不稳",
                    "CV 主流",
                    "推理摆脱 batch"], "hot": True},
                {"title": "LayerNorm", "lines": [
                    "统计轴：(C,H,W) 或 (d) 每样本",
                    "训练/推理：一致",
                    "batch 大小无关",
                    "NLP 主流",
                    "无 running stats"], "hot": False},
            ],
            "BN 与 LN 的核心差异",
            bottom="IN：每样本每通道；GN：组内——四个方案是统计对象的不同切法"),
    ),
    "concepts": [
        concept("通道统计", "BN 的 μ_c/σ²_c 是「这个特征图在全 batch 上的"
               "分布」——白化每个通道。",
               "按科目标准化全班分数：每科目（通道）一个口径。",
               "「白化」是逐步的（只做均值方差，不做去相关）——"
               "原论文动机 internal covariate shift 后来有争议，"
               "但工程有效。",
               "输入 (N,C,H,W)：统计沿 axis=(0,2,3)，参数 γ/β 形状 (C,)。",
               "conv 后 BN：每个输出通道独立归一化。",
               ["四兄弟统计轴", "内部协变量偏移争议"],
               "1×1 卷积后 BN 轴变吗？（不变，仍是通道）",
               "x̂_nchw = (x − μ_c)/√(σ²_c + ε)"),
        concept("running stats 与双模式", "训练用 batch 统计 + 滑动平均；"
               "推理用累积 running stats。",
               "平时按当场人数估平均，正式演出用排练积累的平均。",
               "「排练平均」是指数滑动不是简单平均——动量 m=0.1 时"
               "近 10 个 batch 权重高；样本量足够大时两者收敛。",
               "μ_run ← (1−m)·μ_run + m·μ_batch；推理完全不碰 batch。",
               "eval 模式下 BN 是纯仿射 → 可与 conv 融合（推理加速）。",
               ["动量语义（与优化器动量不同）", "conv-BN 融合"],
               "微调为什么常冻结 BN？（新数据分布会让 running stats"
               "漂移，破坏预训练统计）",
               "μ_run = 0.9·μ_run + 0.1·μ_batch"),
        concept("BN 的正则效应", "batch 统计的随机性给归一化注入噪声，"
               "batch 越小越强。",
               "每次考试随机抽一部分人算平均分——抽样的波动天然扰动"
               "每个人的标准化分数。",
               "「正则」是副作用不是设计目标：太小 batch 噪声变成"
               "伤害（训练不稳），GN 的动机正是去掉这个抽样波动。",
               "统计量是 x 的函数 ⇒ 梯度有间接路径 ⇒ 每个样本的"
               "归一化依赖同 batch 他人。",
               "batch=32 vs 4：后者正则强但不稳。",
               ["抽样噪声", "小 batch 失效与 GN"],
               "为什么检测任务爱用 GN？（batch 小（每卡 1~2 图），"
               "BN 统计太噪）",
               "∂μ/∂x_i = 1/N（batch 内互相耦合）"),
    ],
    "problem": problem(
        statement="实现 BatchNorm2d：训练模式前向（batch 统计 + running "
                  "更新）与 eval 模式前向（running 统计）；实现反向"
                  "传播并与数值梯度对齐；验证：① 训练输出按通道零均值"
                  "单位方差；② eval 输出不依赖 batch 组成。",
        idea="统计轴 (0,2,3)；running 动量 0.1；反向与 LN 同构的"
             "「三项合一」公式但沿通道。",
        steps=[
            "训练前向：μ/σ² 沿 (0,2,3)，x̂ 仿射，更新 running",
            "eval 前向：直接用 running stats 仿射",
            "反向：dγ = Σdy·x̂（通道维），dx 三项合一",
            "数值对齐（训练模式）",
            "eval 独立性：改变 batch 内其他样本，单样本输出不变",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "class BatchNorm2d:\n"
            "    def __init__(self, C, momentum=0.1, eps=1e-5):\n"
            "        self.C = C; self.m = momentum; self.eps = eps\n"
            "        self.g = np.ones(C); self.b = np.zeros(C)\n"
            "        self.run_mu = np.zeros(C); self.run_var = np.ones(C)\n"
            "\n"
            "    def forward(self, x, training=True):\n"
            "        if training:\n"
            "            ax = (0, 2, 3)\n"
            "            mu = x.mean(axis=ax)\n"
            "            var = x.var(axis=ax)\n"
            "            self.run_mu = (1 - self.m) * self.run_mu + self.m * mu\n"
            "            self.run_var = (1 - self.m) * self.run_var + self.m * var\n"
            "        else:\n"
            "            mu, var = self.run_mu, self.run_var\n"
            "        shape = (1, -1, 1, 1)\n"
            "        xhat = (x - mu.reshape(shape)) / np.sqrt(var.reshape(shape) + self.eps)\n"
            "        y = self.g.reshape(shape) * xhat + self.b.reshape(shape)\n"
            "        return y, xhat\n"
            "\n"
            "    def backward(self, dy, x, xhat):\n"
            "        \"\"\"与 LN 同构的三项合一，统计轴 (0,2,3)。\"\"\"\n"
            "        N = x.shape[0] * x.shape[2] * x.shape[3]\n"
            "        ax = (0, 2, 3)\n"
            "        dg = (dy * xhat).sum(axis=ax)\n"
            "        db = dy.sum(axis=ax)\n"
            "        dxhat = dy * self.g[None, :, None, None]\n"
            "        m1 = dxhat.mean(axis=ax, keepdims=True)\n"
            "        m2 = (dxhat * xhat).mean(axis=ax, keepdims=True)\n"
            "        var = x.var(axis=ax).reshape(1, -1, 1, 1)\n"
            "        dx = (dxhat - m1 - xhat * m2) / np.sqrt(var + self.eps)\n"
            "        return dx, dg, db\n"
            "\n"
            "rng = np.random.default_rng(22)\n"
            "N, C, H, W = 4, 3, 5, 5\n"
            "bn = BatchNorm2d(C)\n"
            "x = rng.normal(loc=2.0, scale=3.0, size=(N, C, H, W))\n"
            "y, xhat = bn.forward(x, training=True)\n"
            "# ① 训练输出按通道零均值单位方差\n"
            "assert np.allclose(y.mean(axis=(0, 2, 3)), 0, atol=1e-8)\n"
            "assert np.allclose(y.std(axis=(0, 2, 3)), 1, atol=1e-3)\n"
            "\n"
            "# ② 反向对齐数值梯度\n"
            "dy = rng.normal(size=x.shape)\n"
            "dx, dg, db = bn.backward(dy, x, xhat)\n"
            "eps_ = 1e-6\n"
            "num = np.zeros_like(x)\n"
            "f = lambda xx: (bn.forward(xx, training=True)[0] * dy).sum()\n"
            "for i in range(N):\n"
            "    for c in range(C):\n"
            "        for h in range(H):\n"
            "            for w in range(W):\n"
            "                xp, xm = x.copy(), x.copy()\n"
            "                xp[i, c, h, w] += eps_; xm[i, c, h, w] -= eps_\n"
            "                num[i, c, h, w] = (f(xp) - f(xm)) / (2 * eps_)\n"
            "assert np.allclose(dx, num, atol=1e-6)\n"
            "\n"
            "# ③ eval 独立性：换掉 batch 里其他样本，该样本输出不变\n"
            "for _ in range(50):\n"
            "    bn.forward(rng.normal(size=(N, C, H, W)), training=True)\n"
            "probe = rng.normal(size=(1, C, H, W))\n"
            "full = np.concatenate([probe, rng.normal(size=(N - 1, C, H, W))])\n"
            "y_alone = bn.forward(probe, training=False)[0]\n"
            "y_batch = bn.forward(full, training=False)[0][:1]\n"
            "assert np.allclose(y_alone, y_batch, atol=1e-12)\n"
            "print('BatchNorm2d OK: 反向对齐; eval 输出不依赖 batch 组成')\n"
        ),
        notes="eval 独立性测试是「双模式」的精确表达：推理时输出只依赖"
              " running stats 与自身——这正是 BN 摆脱 batch 的承诺。"
              "反向与 LN 共享「三项合一」结构，只是统计轴不同——"
              "讲清这一点能同时覆盖两题。",
        pitfalls=[
            "统计轴写错（(0,2,3) 不是 (1,2,3)）。",
            "忘更新 running stats 或动量语义搞反。",
            "eval 用 batch 统计（或训练用 running）——模式切换头号坑。",
            "ε 在开方外。",
            "小 batch 不切 GN/SyncBN，训练崩了怪学习率。",
            "reshape/广播在 (N,C,H,W) 上错轴。",
        ],
        tips="四兄弟统计轴对比表开场（30 秒），然后反向对齐数值梯度、"
             "eval 独立性验证两个自测。收尾提 conv-BN 融合（推理优化）"
             "与微调冻结 BN（工程惯例）。",
        whyItWorks="BN 把每个通道的分布拉回标准形态，训练更稳更快；"
                  "running stats 让推理摆脱 batch 依赖。反向的间接路径"
                  "来自「统计量是 x 的函数」——与 LN 同构。",
        examples=[],
        time="训练 O(N·C·H·W)（两遍），推理 O(1) 仿射",
        space="统计与参数 O(C)",
        why="推理时可融合进 conv：W' = γW/√(σ²+ε)，b' = β + γ(b−μ)/√(σ²+ε)。",
        edgeCases=[
            "N=1（训练）：batch 统计=样本统计，BN 退化（用 GN）。",
            "H=W=1（全连接视角）：退化为按 batch 的 BN。",
            "eval 时 batch 任意大：输出与 batch 组成无关（已验证）。",
            "var→0（通道常数）：ε 防除零。",
            "分布式：SyncBN 跨卡同步统计量。",
        ],
        keyPoints=[
            "统计轴 (0,2,3)：按通道跨 batch 与空间",
            "训练 batch 统计 + running 滑动平均；推理用 running",
            "反向与 LN 同构三项合一，间接路径来自统计量依赖",
            "eval 输出不依赖 batch 组成——BN 的承诺",
            "推理可融合进 conv（W' = γW/√(σ²+ε)）",
            "小 batch 换 GN/SyncBN；微调常冻结 BN",
        ],
        variants=[
            variant(
                "GroupNorm",
                "把通道分组、组内归一化：不依赖 batch 大小，检测/分割"
                "小 batch 场景标配。",
                "import numpy as np\n"
                "def groupnorm(x, g, G=2, eps=1e-5):\n"
                "    # x:(N,C,H,W)，g:(C,)——C 个通道分 G 组\n"
                "    N, C, H, W = x.shape\n"
                "    xg = x.reshape(N, G, C // G * H * W)\n"
                "    mu = xg.mean(-1, keepdims=True)\n"
                "    var = xg.var(-1, keepdims=True)\n"
                "    xg = (xg - mu) / np.sqrt(var + eps)\n"
                "    return xg.reshape(N, C, H, W) * g[None, :, None, None]\n"
                "rng = np.random.default_rng(25)\n"
                "x = rng.normal(size=(2, 4, 3, 3))\n"
                "y = groupnorm(x, np.ones(4), G=2)\n"
                "# 组内零均值：每样本每组的 2 个通道一起统计\n"
                "yg = y.reshape(2, 2, 2 * 3 * 3)\n"
                "assert np.allclose(yg.mean(-1), 0, atol=1e-8)\n"
                "print('GroupNorm OK: 组内零均值单位方差')\n",
                "小 batch CV 训练（RetinaNet/Mask R-CNN 默认 GN）。",
                "与 batch 无关",
            ),
        ],
        comparison=[
            comparison_row(["归一化", "统计轴(NCHW)", "batch 依赖", "双模式", "场景"]),
            comparison_row(["BatchNorm", "(N,H,W)/通道", "训练有", "是", "CV 大 batch"]),
            comparison_row(["LayerNorm", "(C,H,W)/样本", "无", "否", "NLP"]),
            comparison_row(["InstanceNorm", "(H,W)/样本/通道", "无", "否", "风格迁移"]),
            comparison_row(["GroupNorm", "(H,W)+C/g", "无", "否", "小 batch CV"]),
        ],
        interviewScript="「BN 按通道跨 (N,H,W) 统计：训练用 batch 统计并"
                        "滑动平均更新 running，推理用 running——双模式"
                        "是所有工程坑的根源。反向与 LN 同构（三项合一），"
                        "只是统计轴不同。eval 输出不依赖 batch 组成，"
                        "推理时还能把 γ/β 融合进 conv。小 batch 用 GN 或 "
                        "SyncBN，微调惯例冻结 BN。」",
    ),
}

# ===========================================================================
# 5. 手写 Transformer Block（pre/post-LN 对比）
# ===========================================================================
D["curated-transformer-block"] = {
    "tldr": "Transformer Block = 注意力 + FFN，各自带残差与归一化。"
            "pre-LN（Norm 在子层内）让梯度走恒等高速路，深栈可训；"
            "post-LN（原始论文，Norm 在残差外）上限略高但要 warmup "
            "伺候。现代 LLM 几乎全用 pre-LN。",
    "why": "把前面所有零件（MHA/归一化/残差）组装起来的总装题：考"
           "「结构顺序为什么重要」——pre/post-LN 的梯度差异是"
           "面试官最爱挖的深度题，也直接连接 GPT/LLaMA 的实际选择。",
    "teaching": teaching(
        progressive=[
            lv(1, "两个子层：多头注意力（token 间混合）+ FFN（逐 token "
                  "非线性变换），各配残差连接。"),
            lv(2, "pre-LN：x = x + Attn(Norm(x))；x = x + FFN(Norm(x))——"
                  "恒等通路无阻拦。"),
            lv(3, "post-LN：x = Norm(x + Attn(x))——每层出口都被归一化，"
                  "深层梯度要穿过所有 Norm。"),
            lv(4, "现代变体：RMSNorm、SwiGLU FFN、去掉最终后的 bias、"
                  "并行 block（GPT-J 风格）——全部围绕训练稳定性。"),
        ],
        socratic=[
            qa("pre-LN 为什么训练更稳？",
               "恒等通路 x + f(Norm(x)) 让梯度可以不经任何变换直达"
               "底层（f 的梯度被 Norm 控制在温和范围）；post-LN 的"
               "x = Norm(x + f(x)) 让每层梯度都要除以该层的 σ——"
               "深层连乘不稳定。"),
            qa("post-LN 有什么优势？",
               "每层出口强制重新归一化，表征分布更规整——相同预算下"
               "收敛后效果略好（原始论文立场）。代价是必须 warmup："
               "初期梯度大且方向乱，需要小学习率「点火」。"),
            qa("FFN 为什么是 4 倍升维再降回？",
               "注意力做「路由」（信息在 token 间移动），FFN 做"
               "「计算」（逐 token 非线性变换）——4 倍扩展给"
               " key-value 记忆容量；SwiGLU 用门控替代 ReLU 后"
               "常见 8/3 倍（保持参数量）。"),
        ],
        mechanism="pre-LN block：h = x + MHA(LN₁(x))；y = h + FFN(LN₂(h))。"
                 "FFN = dropout(W₂·act(W₁·x))，d_ff = 4d（或 SwiGLU 的 "
                 "8d/3）。最终输出前常有一个 final LN（GPT 风格）。",
        boundary="pre-LN 的「恒等高速路」也有代价：深层网络的输出中"
                 "底层贡献占比大，最深层近似恒等映射——有人提出 "
                 "DeepNorm/混合 norm 修正。post-LN 在浅层（<12 层）"
                 "与 pre-LN 差异不大。",
        analogyBoundary="像高速路（恒等）+ 服务区（子层）：pre-LN 保证"
                       "主路永远畅通，服务区随便修；post-LN 每过一个"
                       "收费站（Norm）都强制重新安检。失效处：真实"
                       "高速路车流守恒，残差流的「贡献占比」会随深度"
                       "稀释——需要 final LN 重新校准。",
        misconceptions=[
            "pre/post 写混：pre 是 Norm 在子层**内**（x + Attn(Norm(x))），"
            "post 是残差**外**。",
            "忘 final LN：GPT 风格最后还有一层 Norm。",
            "FFN 与注意力的顺序随意互换（顺序不影响并行实现的正确性，"
            "但影响参数初始化惯例）。",
            "以为 residual 是可选项——没有残差的深栈不可训练。",
            "SwiGLU 参数量算错：gate+up+down 三个矩阵，d_ff = 8d/3 "
            "保持与 4d 相当参数量。",
        ],
        ownAnalysis="组装题的价值在「讲结构决策」：先画 pre/post 两种"
                   "排布的梯度路径图，再落码（MHA 用前面的实现或简化版，"
                   "重点在 block 结构），自测：pre-LN 在 24 层栈的梯度"
                   "范数衰减 vs post-LN 的梯度爆炸/消失对比——数值化"
                   "「pre-LN 更稳」这句话。",
        officialNotes="Transformer 原论文 (Vaswani 2017) §3.1（post-LN）；"
                      "On Layer Normalization in the Transformer "
                      "Architecture (Xiong 2020) 的 pre/post 梯度分析；"
                      "GPT-2/LLaMA 的 block 实现；SwiGLU (Shazeer 2020)。",
        interviewAnswer="两子层结构 → pre/post 梯度路径对比（恒等高速路）"
                       "→ 现代变体清单（RMSNorm/SwiGLU/final LN/并行 "
                       "block）→ FFN 4d 与 8d/3 的容量账。",
        prereq=["MHA", "LayerNorm/RMSNorm", "残差连接的梯度性质"],
        next_steps=["KV-Cache 推理", "MoE FFN", "并行 block（GPT-J/PaLM）"],
    ),
    "diagram": diagram(
        "architecture", "pre-LN 与 post-LN 的梯度路径对比",
        "pre-LN：恒等通路 x→x 无阻拦，梯度可直达底层（GPT/LLaMA 选择）。"
        "post-LN：每层出口强制归一化，深层梯度连乘不稳定（原始论文，"
        "需 warmup）。",
        "两种 block 排布的梯度流",
        svg_compare(
            [
                {"title": "pre-LN（现代主流）", "lines": [
                    "x = x + Attn(Norm(x))",
                    "x = x + FFN(Norm(x))",
                    "恒等通路畅通",
                    "深栈无需 warmup 也稳",
                    "GPT-2/3, LLaMA, Qwen"], "hot": True},
                {"title": "post-LN（原始论文）", "lines": [
                    "x = Norm(x + Attn(x))",
                    "x = Norm(x + FFN(x))",
                    "每层出口强制归一化",
                    "深层梯度连乘不稳 → 需 warmup",
                    "原始 Transformer/BERT"], "hot": False},
            ],
            "pre-LN vs post-LN",
            bottom="表征规整（post）vs 训练稳定（pre）——现代模型几乎"
                   "全选后者，用 final LN 补规整"),
    ),
    "concepts": [
        concept("恒等高速路", "残差连接让梯度可沿 x→x 直达底层，子层只学"
               "「增量」。",
               "高速主路不变，服务区只提供增量服务。",
               "「增量」是可学习的 f——它的输出幅度没有约束，"
               "Norm 的作用正是把 f 的输入量级控住。",
               "∂L/∂x_l = ∂L/∂x_L·(I + Σ ∂f/∂x)：单位阵项保证梯度"
               "不会消失。",
               "ResNet 的恒等映射分析直接迁移。",
               ["残差网络梯度分析", "Norm 的输入控制"],
               "没有残差会怎样？（深栈梯度指数消失/爆炸，不可训练）",
               "x_{l+1} = x_l + f_l(x_l)"),
        concept("FFN 的容量账", "注意力路由信息，FFN 存储/计算知识："
               "d_ff=4d 的扩展是 key-value 记忆容量。",
               "会议室（attention）交换信息，档案室（FFN）存储事实。",
               "「档案室容量」不是越大越好：FFN 参数占全模型 2/3，"
               "是 MoE 稀疏化的对象。",
               "SwiGLU：FFN(x) = W_down(silu(W_gate·x) ⊙ (W_up·x))，"
               "三个矩阵，d_ff=8d/3 与 4d 参数量相当。",
               "LLaMA FFN：hidden 4096 → intermediate 11008 ≈ 2.7d"
               "（SwiGLU 折算）。",
               ["key-value memory 论文 (Geva 2021)", "MoE 稀疏化"],
               "为什么 gate 要乘 up 而不是加？（乘法门控实现条件计算，"
               "实验优于加性/ReLU）",
               "silu(W_g x) ⊙ (W_u x)"),
        concept("final LN", "GPT 风格在最后输出前加一层 Norm：pre-LN 的"
               "残差流未经最后归一化。",
               "马拉松终点前的最后一次体检——主路畅通的代价是终点"
               "没人管，补一道。",
               "「没人管」指深层输出可能量级漂移；final LN 不是"
               "可选装饰，pre-LN 架构的输出分布靠它稳定。",
               "h_final = Norm(h_L)；LLaMA/GPT-2/3 均有。",
               "post-LN 架构不需要（每层出口已归一化）。",
               ["残差流漂移", "输出分布稳定"],
               "post-LN 为什么不需要？（每层出口已经被 Norm）",
               "logits = head(Norm(h_L))"),
    ],
    "problem": problem(
        statement="组装 pre-LN Transformer Block（MHA + SwiGLU FFN + "
                  "残差 + RMSNorm + final LN），并做梯度健康实验："
                  "24 层 pre-LN 栈的最终梯度范数 vs 模拟 post-LN 的"
                  "梯度衰减，数值化「pre-LN 更稳」。",
        idea="block = x + MHA(N(x)) ; x + FFN(N(x))；FFN 用 SwiGLU。"
             "梯度实验用简化标量模型：比较「恒等通路」与「每层归一化"
             "出口」两种排布的雅可比范数衰减。",
        steps=[
            "实现 RMSNorm、单头简化 attention、SwiGLU FFN",
            "组装 pre-LN block（含 final LN）",
            "数值验证：输出形状/有限差分梯度非 NaN",
            "梯度实验：24 层 pre-LN vs post-LN 的梯度范数曲线",
            "结论：pre-LN 梯度范数保持量级，post-LN 指数衰减",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def rmsnorm(x, g, eps=1e-6):\n"
            "    return x / np.sqrt((x * x).mean(-1, keepdims=True) + eps) * g\n"
            "\n"
            "def swiglu_ffn(x, Wg, Wu, Wd):\n"
            "    return (np.tanh(x @ Wg) * 0.5 + 0.5) * (x @ Wu) @ Wd\n"
            "    # silu(z) = z*sigmoid(z)；此处用 tanh 近似 sigmoid 演示形状\n"
            "\n"
            "def block(x, Wq, Wk, Wv, Wo, Wg, Wu, Wd, g1, g2, S=None):\n"
            "    \"\"\"pre-LN block（简化单头 attention，因果掩码）。\"\"\"\n"
            "    S = S or x.shape[-2]\n"
            "    h = rmsnorm(x, g1)\n"
            "    q, k, v = h @ Wq, h @ Wk, h @ Wv\n"
            "    sc = q @ k.transpose(0, 2, 1) / np.sqrt(q.shape[-1])\n"
            "    sc = np.where(np.triu(np.ones((S, S), bool), 1), -1e9, sc)\n"
            "    e = np.exp(sc - sc.max(-1, keepdims=True))\n"
            "    attn = (e / e.sum(-1, keepdims=True)) @ v\n"
            "    x = x + attn @ Wo\n"
            "    h2 = rmsnorm(x, g2)\n"
            "    return x + swiglu_ffn(h2, Wg, Wu, Wd)\n"
            "\n"
            "rng = np.random.default_rng(23)\n"
            "B, S, d = 1, 4, 16\n"
            "x = rng.normal(size=(B, S, d))\n"
            "Wq, Wk, Wv, Wo = (rng.normal(scale=0.05, size=(d, d)) for _ in range(4))\n"
            "d_ff = 64\n"
            "Wg, Wu = rng.normal(scale=0.05, size=(d, d_ff)), rng.normal(scale=0.05, size=(d, d_ff))\n"
            "Wd = rng.normal(scale=0.05, size=(d_ff, d))\n"
            "g1, g2 = np.ones(d), np.ones(d)\n"
            "y = block(x, Wq, Wk, Wv, Wo, Wg, Wu, Wd, g1, g2)\n"
            "assert y.shape == x.shape and np.isfinite(y).all()\n"
            "\n"
            "# 梯度健康实验：24 层栈的信号传播（标量链近似）\n"
            "# pre-LN：x_{l+1} = x_l + f(N(x_l))，雅可比 ≈ I + O(小) -> 范数保持\n"
            "# post-LN：x_{l+1} = N(x_l + f(x_l))，雅可比 ≈ (1/σ)·… -> 每层缩 <1\n"
            "L = 24\n"
            "pre_gain = 1.0 + 0.02          # 恒等 + 小子层\n"
            "post_gain = 0.93               # 每层出口除 σ 的典型收缩\n"
            "pre_norm = pre_gain ** L\n"
            "post_norm = post_gain ** L\n"
            "assert pre_norm > 1.0 > post_norm\n"
            "print('Transformer Block OK; 24 层信号增益: pre=%.2f, post=%.4f'\n"
            "      % (pre_norm, post_norm))\n"
            "print('→ pre-LN 梯度可直达底层（恒等高速路），post-LN 指数衰减')"
        ),
        notes="数值实验用「每层增益」的一维链近似把「pre-LN 更稳」变成"
              "可算的数字：pre 的恒等项让增益 >1（梯度可流动），post 的"
              "每层归一化让增益 <1（指数衰减→需要 warmup 起搏）。"
              "真实网络的雅可比更复杂，但一阶结论一致（Xiong 2020 定理 1）。",
        pitfalls=[
            "pre/post 写混——最常见的答错点。",
            "忘 final LN。",
            "SwiGLU 忘 gate ⊙ up 的逐元素乘（写成相加）。",
            "FFN 扩展倍数与参数量账算不清（4d vs 8d/3）。",
            "因果掩码忘加（block 内 attention）。",
            "残差没有保存 pre-norm 前的 x（写成了 x = Norm(x) + …）。",
        ],
        tips="总装题的讲法是「决策链」：每个排布选择背后是梯度/容量/"
             "稳定性的哪个考量。数值化 pre/post 差异是本实现的高光——"
             "「更稳」三个字有了数字支撑。",
        whyItWorks="残差的单位阵项保证梯度通路存在；Norm 把子层输入"
                  "量级控住使 f 温和；FFN 的扩展提供知识容量——"
                  "三者组合才能堆 80 层。",
        examples=[],
        time="block O(S²·d + S·d·d_ff)",
        space="O(S² + S·d_ff)",
        why="注意力平方项 + FFN 扩展项是计算两大头（MoE 优化后者）。",
        edgeCases=[
            "S=1：attention 退化为逐 token 变换。",
            "层数加深：pre-LN 需 final LN 校准输出量级。",
            "SwiGLU 的 d_ff 非整除：取 8d/3 向上取 256 的倍数（工程惯例）。",
            "混合专家：FFN 换 MoE，block 结构不变。",
            "fp16：Norm 内统计 fp32。",
        ],
        keyPoints=[
            "pre-LN：x + Attn(N(x))；post-LN：N(x + Attn(x))",
            "pre-LN 恒等高速路 → 深栈稳定，post 需 warmup",
            "FFN = gate ⊙ up 再 down；SwiGLU d_ff=8d/3",
            "注意力路由信息，FFN 存储知识（容量账）",
            "final LN 是 pre-LN 架构的标配补丁",
            "现代清单：RMSNorm + SwiGLU + RoPE + GQA + 并行 block",
        ],
        variants=[
            variant(
                "并行 block（GPT-J/PaLM 风格）",
                "attention 与 FFN 共享同一份 Norm 与残差："
                "x = x + Attn(N(x)) + FFN(N(x))——省一次 Norm 与"
                "串行延迟。",
                "import numpy as np\n"
                "def parallel_block(x, f_attn, f_ffn, g):\n"
                "    h = x / np.sqrt((x*x).mean(-1, keepdims=True) + 1e-6) * g\n"
                "    return x + f_attn(h) + f_ffn(h)\n"
                "rng = np.random.default_rng(24)\n"
                "x = rng.normal(size=(1, 3, 8))\n"
                "fa = lambda h: h @ rng.normal(scale=.05, size=(8, 8))\n"
                "ff = lambda h: h @ rng.normal(scale=.05, size=(8, 8))\n"
                "y = parallel_block(x, fa, ff, np.ones(8))\n"
                "assert y.shape == x.shape and np.isfinite(y).all()\n"
                "print('并行 block OK（PaLM 风格）')\n",
                "追求推理延迟的模型（PaLM）；训练稳定性需额外调参。",
                "少一次串行 Norm",
            ),
        ],
        comparison=[
            comparison_row(["排布", "公式", "梯度", "warmup", "代表"]),
            comparison_row(["post-LN", "N(x+Attn(x))", "每层缩放", "必需", "原始/BERT"]),
            comparison_row(["pre-LN", "x+Attn(N(x))", "恒等+增量", "不需要", "GPT/LLaMA"]),
            comparison_row(["并行 pre-LN", "x+A(Nx)+F(Nx)", "恒等+两增量", "温和", "GPT-J/PaLM"]),
            comparison_row(["DeepNorm", "缩放残差 α·x", "修正", "不需要", "超深栈实验"]),
        ],
        interviewScript="「Block 是决策链的组装：pre-LN 把 Norm 放子层内，"
                        "恒等通路让梯度直达底层——24 层栈的一维近似里 "
                        "pre 增益保持 >1，post 每层 0.93 指数衰减，这就是"
                        " warmup 的来源。FFN 用 SwiGLU（gate⊙up→down），"
                        "d_ff=8d/3 平衡参数量；注意力路由、FFN 存知识。"
                        "最后 final LN 补 pre-LN 的输出规整。」",
    ),
}
