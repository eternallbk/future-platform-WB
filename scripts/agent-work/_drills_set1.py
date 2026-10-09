# -*- coding: utf-8 -*-
"""_drills_set1.py — 模型手撕深度解析 · attention 基础（2 题）。"""

from _drills_helpers import (
    diagram, teaching, lv, qa, concept, variant, comparison_row,
    problem, svg_flow, svg_compare,
)

D = {}

# ===========================================================================
# 1. 手写 Multi-Head Self-Attention
# ===========================================================================
D["curated-mha-implementation"] = {
    "tldr": "MHSA 的全部难点是「形状编排」：把 (B,S,d) 投影成 (B,h,S,dh)，"
            "Q·Kᵀ/√dh 后做因果掩码，softmax 得权重再加权 V，最后合并各头再投影。"
            "多头不是特征变多，而是让不同头在独立子空间里各自学一种关系。",
    "why": "所有 LLM 面试的第一道手撕题：同时考察注意力公式、√dh 的来历、"
           "因果掩码写法和张量变形功底。这题答不清，KV-Cache/FlashAttention/"
           "GQA 的追问都无从展开。",
    "teaching": teaching(
        progressive=[
            lv(1, "先把单头写对：score = Q·Kᵀ/√dh，权重 = softmax(score)，"
                  "输出 = 权重·V。三步矩阵乘。"),
            lv(2, "加因果掩码：j>i 的 score 加 −1e9 再 softmax——不是删行，"
                  "是让 exp 下溢为 0。"),
            lv(3, "扩到多头：(B,S,d) → reshape (B,S,h,dh) → transpose "
                  "(B,h,S,dh)，头成为独立 batch 维；算完逆操作合并，过 W_o。"),
            lv(4, "生产视角：(B,h,S,S) 权重矩阵是显存大头（FlashAttention "
                  "的动机）；推理时 K/V 可缓存（KV-Cache 的入口）。"),
        ],
        socratic=[
            qa("为什么除以 √dh？",
               "Q·K 每分量是 dh 个独立乘积求和，方差随 dh 线性增长；除 √dh "
               "把方差拉回 ~1，防止 softmax 饱和梯度消失。"),
            qa("掩码为什么加 −1e9 而不是置 0？",
               "置 0 后 softmax 仍给这些位置分配 e⁰>0 的权重——0 分不是"
               "负无穷分。加 −1e9 让 exp 下溢为 0，才是真「看不见」。"),
            qa("多头合并后为什么还要 W_o？",
               "concat 只是摆放，W_o 让不同头的信息混合。没有它，多头退化"
               "成 h 个互不通信的单头。"),
        ],
        mechanism="每头独立投影 Q/K/V，在低维子空间内做 scaled dot-product "
                 "attention；输出 concat 后经 W_o 融合。多头的价值是关系"
                 "多样性——语法、共指、位置局部性在不同头里各自形成。",
        boundary="单头大 dh 与多头小 dh 参数量相同但表达不同：多头有 h 个 "
                 "softmax 分布，关系容量更大；但 dh<32 时点积估计噪声大。"
                 "dh=64 是关系容量与估计质量的折中。",
        analogyBoundary="像多位评审独立打分再汇总：各有评分标准（投影），"
                       "最后开会统一（W_o）。失效处：评审如何融合是训练学出"
                       "的（W_o 可学习），不是固定平均。",
        misconceptions=[
            "拆头直接 reshape(B,h,S,dh)——把序列切碎，必须先 (B,S,h,dh) 再 transpose。",
            "掩码加在 softmax 之后——score 仍参与归一化分母，信息照样泄漏。",
            "√dh 写成 √d 或 √S：缩放只跟点积求和长度 dh 有关。",
            "忘 W_o：concat 不等于输出。",
            "softmax 不减 max：S 大时 exp 上溢。",
        ],
        ownAnalysis="形状注释从头写到尾——面试官就在看 (B,h,S,dh) 是否条件"
                   "反射。掩码先造 (1,1,S,S) 三角布尔阵再 where，不要循环。"
                   "写完主动做因果性自测：改动未来 token，过去输出不变——"
                   "最有说服力的验证，还能自然引到 KV-Cache。",
        officialNotes="Attention Is All You Need (Vaswani 2017) §3.2.2；"
                      "The Annotated Transformer 逐行实现；torch "
                      "F.scaled_dot_product_attention 文档。",
        interviewAnswer="先写公式，再按「投影→分头→点积→掩码→softmax→加权→"
                       "合头→W_o」落码，主动讲 √dh 方差论证、−1e9 原理、"
                       "(B,h,S,S) 显存问题，收尾引出 FlashAttention 与 "
                       "KV-Cache。",
        prereq=["矩阵乘与 einsum", "softmax 数值稳定", "reshape/transpose 语义"],
        next_steps=["KV-Cache 与 GQA", "FlashAttention", "RoPE"],
    ),
    "diagram": diagram(
        "architecture", "一次前向里张量的形状流转（B=2, h=4, S=5, d=256, dh=64）",
        "四个投影把 (B,S,d) 变成 (B,h,S,dh)；attention 在头维内独立完成；"
        "concat 回 (B,S,256) 经 W_o 输出。掩码作用在 softmax 之前。",
        "MHSA 张量形状流转图",
        svg_flow([
            {"label": "W_q / W_k / W_v  线性投影", "in": "(B,S,256)",
             "out": "各 (B,S,256)", "hot": True,
             "note": "常合并为 (d,3d) 大矩阵一次算完"},
            {"label": "reshape + transpose 拆头", "in": "(B,S,256)",
             "out": "Q,K,V: (B,4,5,64)",
             "note": "头维插在 batch 之后，成为独立子空间"},
            {"label": "Q·Kᵀ / √64", "in": "(B,4,5,64)×(B,4,64,5)",
             "out": "score (B,4,5,5)", "hot": True,
             "note": "√dh 缩放让 logits 方差 ~1"},
            {"label": "因果掩码 + softmax", "in": "score (B,4,5,5)",
             "out": "权重 (B,4,5,5)",
             "note": "j>i 的 score += −1e9；softmax 沿最后一维"},
            {"label": "权重·V，合并各头", "in": "(B,4,5,64)",
             "out": "(B,5,256)", "note": "transpose 回来再 reshape"},
            {"label": "W_o 输出投影", "in": "(B,5,256)", "out": "(B,5,256)",
             "note": "各头信息混合——多头真正「多」的一步"},
        ], "MHSA 前向张量形状流转"),
    ),
    "concepts": [
        concept("缩放点积", "Q·K 点积衡量「我该关注你多少」，除 √dh 防止"
               "求和把方差撑大。",
               "考试给分：题目越多总分越大，要除 √题量才能跨卷比较。",
               "总分线性增长，方差按 √dh 增长——缩放保方差不保均值，"
               "所以除 √dh 不是 dh。",
               "q,k 分量 iid 零均值方差 1 时，和的方差 = dh；除 √dh 回到 1，"
               "softmax 远离饱和区。",
               "dh=64 → 缩放 1/8：score 整体缩小 8 倍。",
               ["点积方差的维度依赖", "softmax 饱和与梯度"],
               "q,k 分量方差变 4，缩放因子改多少？（仍 √dh——只补维度不补分布）",
               "softmax(QKᵀ/√dh)V"),
        concept("因果掩码", "位置 i 只许看 ≤ i：j>i 的 score 加 −1e9。",
               "考场只能看已发的试卷页。",
               "挡的是「信息获取」不是「数值大小」——被挡位置不进入归一化，"
               "不是低分。",
               "exp(−1e9−max)≈0，权重为 0 且分母无贡献——等价于不存在。",
               "5×5 上三角封死，对角线及以下可看。",
               ["−1e9 与 0 的区别", "padding 掩码叠加"],
               "BERT 为什么不用？（编码器全句可见）",
               "score.masked_fill(~mask, -1e9)"),
        concept("多头子空间", "h 个头在 d/h 维子空间独立 attention，最后拼接融合。",
               "委员会各自调研再开会决议。",
               "委员开会前不交流（头间无交互），交流只发生在 W_o 且规则是学的。",
               "各头独立 W_qᵢ/W_kᵢ/W_vᵢ（实现合成大矩阵再 reshape）；"
               "输出 concat 经 W_o∈R^{d×d} 回模型空间。",
               "4 头 × 64 维 concat = 256 维，再乘 256×256 W_o。",
               ["参数量：4d² vs 单头 d²", "为什么合并后必须再投影"],
               "heads=8, d=512 时单头 dh？（64）",
               "MultiHead = Concat(head₁..h)·W_o"),
    ],
    "problem": problem(
        statement="用 numpy 手写带因果掩码的多头自注意力：输入 X (B,S,d)，"
                  "头数 h，输出 (B,S,d)。要求显式 √dh 缩放、−1e9 掩码、"
                  "softmax 前减 max、形状注释完整。",
        idea="三步：① 一次矩阵乘完成 Q/K/V 投影再拆头；② 单头 scaled "
             "dot-product + 掩码 + 稳定 softmax；③ 合头 + W_o。",
        steps=[
            "W_q/W_k/W_v/W_o 初始化（真实训练中可学习）",
            "X@W → reshape (B,S,h,dh) → transpose (B,h,S,dh)",
            "score = Q @ Kᵀ / sqrt(dh)",
            "因果掩码：j>i 处 score += −1e9",
            "softmax 前沿最后一维减 max",
            "权重@V → transpose 回 → reshape (B,S,d) → @ W_o",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def softmax(x, axis=-1):\n"
            "    x = x - x.max(axis=axis, keepdims=True)\n"
            "    e = np.exp(x)\n"
            "    return e / e.sum(axis=axis, keepdims=True)\n"
            "\n"
            "def mha(X, Wq, Wk, Wv, Wo, n_head, causal=True):\n"
            "    \"\"\"X:(B,S,d) -> (B,S,d)。所有 W 是 (d,d)。\"\"\"\n"
            "    B, S, d = X.shape\n"
            "    dh = d // n_head\n"
            "    assert dh * n_head == d\n"
            "    def split(T):   # (B,S,d) -> (B,h,S,dh)：先拆头再换轴\n"
            "        return T.reshape(B, S, n_head, dh).transpose(0, 2, 1, 3)\n"
            "    Q, K, V = split(X @ Wq), split(X @ Wk), split(X @ Wv)\n"
            "    score = Q @ K.transpose(0, 1, 3, 2) / np.sqrt(dh)  # (B,h,S,S)\n"
            "    if causal:\n"
            "        tri = np.triu(np.ones((S, S), bool), k=1)\n"
            "        score = np.where(tri, score - 1e9, score)\n"
            "    w = softmax(score)\n"
            "    out = w @ V                                        # (B,h,S,dh)\n"
            "    out = out.transpose(0, 2, 1, 3).reshape(B, S, d)\n"
            "    return out @ Wo\n"
            "\n"
            "# 自测：形状 + 因果性（改未来 token，过去输出不变）\n"
            "rng = np.random.default_rng(0)\n"
            "B, S, d, h = 2, 5, 256, 4\n"
            "X = rng.normal(size=(B, S, d))\n"
            "Wq, Wk, Wv, Wo = (rng.normal(scale=0.02, size=(d, d)) for _ in range(4))\n"
            "Y = mha(X, Wq, Wk, Wv, Wo, h)\n"
            "assert Y.shape == (B, S, d)\n"
            "X2 = X.copy(); X2[:, 3:, :] = rng.normal(size=(B, S - 3, d))\n"
            "Y2 = mha(X2, Wq, Wk, Wv, Wo, h)\n"
            "assert np.allclose(Y[:, :3, :], Y2[:, :3, :], atol=1e-10)\n"
            "print('mha OK', Y.shape)\n"
        ),
        notes="Wq/Wk/Wv 生产实现常合成 (d,3d) 大矩阵一次 GEMM；这里分开写"
              "为可读。因果性自测是最有说服力的验证：掩码真生效时，未来"
              "token 换内容不影响过去输出。",
        pitfalls=[
            "拆头直接 reshape(B,h,S,dh)——序列被切碎。",
            "掩码用 0 而非 −1e9：softmax 仍分配正权重。",
            "score 忘除 √dh：softmax 饱和训练不动。",
            "softmax 沿错轴：必须沿最后一维（每个查询位置）。",
            "合头忘先 transpose 再 reshape，维度对不上当场卡死。",
            "不减 max 直接 exp：S 大必溢出。",
        ],
        tips="先把形状写在草稿上，每步标注。写完主动演示因果性验证，"
             "再带出「推理时 K/V 可缓存」——把话题引向 KV-Cache/"
             "FlashAttention 的主场。",
        whyItWorks="注意力是可微分的查表：Q·K 匹配度经 softmax 变软寻址"
                  "权重，V 按权重混合。缩放保数值、掩码保因果、多头保"
                  "多样性、W_o 保融合。",
        examples=[],
        time="O(h·S²·dh) = O(S²·d)",
        space="O(h·S²·dh)，权重矩阵是显存大头",
        why="S×S 权重矩阵逐头独立存在，长序列平方增长——FlashAttention "
            "把它压到 O(S·dh) 的动机。",
        edgeCases=[
            "S=1：输出 = 单 token 的 V 投影，无信息混合。",
            "h=1：退化为单头 scaled dot-product。",
            "dh=1：每头一个标量维度，方差论证失效。",
            "含 padding：因果掩码上再叠 padding 掩码。",
            "X 全零：softmax 均匀，输出 = W_o·mean(V)。",
        ],
        keyPoints=[
            "score = QKᵀ/√dh，除 √dh 是方差归一化不是可选项",
            "掩码加在 softmax 之前的 score 上，用 −1e9 而非 0",
            "拆头 (B,S,h,dh)→(B,h,S,dh)，合头逆操作",
            "softmax 前沿最后一维减 max",
            "W_o 是多头机制的一半：没有它头与头从未交互",
            "训练并行+掩码 vs 推理逐 token+缓存，两套运行时行为",
        ],
        variants=[
            variant(
                "einsum 一体版",
                "einsum 把「拆头-点积-加权」写成一行，头维自动对齐，"
                "展示形状功底的加分写法。",
                "import numpy as np\n"
                "rng = np.random.default_rng(1)\n"
                "B,S,d,h = 2,4,64,8; dh = d//h\n"
                "X = rng.normal(size=(B,S,d))\n"
                "Wqkv = rng.normal(scale=0.02, size=(d, 3*d))\n"
                "qkv = X @ Wqkv\n"
                "q,k,v = np.split(qkv, 3, axis=-1)\n"
                "shp = (B,S,h,dh)\n"
                "q,k,v = (t.reshape(shp).transpose(0,2,1,3) for t in (q,k,v))\n"
                "score = np.einsum('bhqd,bhkd->bhqk', q, k) / np.sqrt(dh)\n"
                "mask = np.triu(np.ones((S,S),bool),1)\n"
                "score = np.where(mask, -1e9, score)\n"
                "w = np.exp(score - score.max(-1,keepdims=True))\n"
                "w = w / w.sum(-1,keepdims=True)\n"
                "out = np.einsum('bhqk,bhkd->bhqd', w, v)\n"
                "out = out.transpose(0,2,1,3).reshape(B,S,d)\n"
                "assert out.shape == (B,S,d)\n"
                "print('einsum 版 OK')\n",
                "熟悉 einsum、追求代码密度；生产实现里 einsum/bmm 均常见。",
                "少两次临时矩阵",
            ),
            variant(
                "单头显式循环（教学版）",
                "每个查询位置对每个键位置显式循环，看清「掩码挡谁」；"
                "O(S³) 只用于讲原理。",
                "import numpy as np\n"
                "rng = np.random.default_rng(2)\n"
                "S,d = 4,16\n"
                "X = rng.normal(size=(S,d))\n"
                "Wq,Wk,Wv = (rng.normal(scale=.1,size=(d,d)) for _ in range(3))\n"
                "Q,K,V = X@Wq, X@Wk, X@Wv\n"
                "out = np.zeros_like(V)\n"
                "for i in range(S):\n"
                "    scores = np.array([Q[i]@K[j]/np.sqrt(d) if j<=i else -1e9\n"
                "                       for j in range(S)])\n"
                "    w = np.exp(scores - scores.max())\n"
                "    w /= w.sum()\n"
                "    out[i] = w @ V\n"
                "    assert abs(w.sum()-1) < 1e-9\n"
                "print('循环教学版 OK')\n",
                "白板推导、给面试官逐步讲掩码语义；生产不用。",
                "O(S³)，纯教学",
            ),
        ],
        comparison=[
            comparison_row(["实现", "显存", "时间", "适用"]),
            comparison_row(["朴素（本实现）", "O(S²·d)", "O(S²·d)", "小模型训练/白板"]),
            comparison_row(["FlashAttention", "O(S·dh)", "O(S²·d)", "长序列训练/推理"]),
            comparison_row(["KV-Cache 推理", "O(S·d) 缓存", "每 token O(S·d)", "自回归解码"]),
            comparison_row(["线性注意力", "O(S·d²/dh)", "O(S·d)", "超长序列近似"]),
        ],
        interviewScript="「我按投影、分头、点积、掩码、加权、合头六步写。"
                        "两个易错点先说明：拆头必须先 reshape 后 transpose；"
                        "掩码加 −1e9 在 softmax 前。写完用因果性自测——改动"
                        "未来 token 过去输出不变。这个实现的两个工程后裔是 "
                        "FlashAttention（压 S² 显存）和 KV-Cache（省重复"
                        "计算），需要可以继续展开。」",
    ),
}

# ===========================================================================
# 2. KV-Cache 显存计算与 GQA 优化
# ===========================================================================
D["curated-kv-cache-memory"] = {
    "tldr": "自回归解码不缓存 K/V 就是每步重算全部历史——O(S²)。KV-Cache 用 "
            "O(S·L·d) 显存换增量计算；GQA 再把 KV 头数除以分组数 g，显存"
            "直降 g 倍，Llama-2/3-70B 的标准配置。",
    "why": "推理优化岗必考：先考「会不会算」（显存公式现场推），再考"
           "「怎么省」（GQA/MQA/量化/分页）。串起模型结构、显存、吞吐三个"
           "维度，区分度极高。",
    "teaching": teaching(
        progressive=[
            lv(1, "会算：每层缓存 K 和 V 各 (B,S,d)，fp16 每元素 2 字节。"
                  "总显存 = 2·L·B·S·d·dtype。"),
            lv(2, "看数量级：Llama-2-7B（L=32,d=4096）4K 上下文单序列 ≈ 2.1 GB"
                  "——比权重本身更敏感。"),
            lv(3, "GQA：Q 头不变，KV 头分组共享——g 个 Q 头共用 1 组 KV，"
                  "KV 显存 ÷g，质量几乎无损。"),
            lv(4, "对比 MQA（g=1，省到极致质量有损）与 PagedAttention"
                  "（按页管理 KV 治碎片，vLLM 核心）。"),
        ],
        socratic=[
            qa("为什么只缓存 K/V 不缓存 Q？",
               "当前步的 Q 只有 1 个 token 现算即可；注意力要对全部历史"
               "K/V 打分——历史部分每步相同，不缓存就重算。缓存的是"
               "「被查方」。"),
            qa("GQA 为什么几乎不掉点？",
               "注意力质量主要取决于 Q 头多样性；KV 共享只是多个 Q 头读"
               "同一份「记忆」。图书馆少建分馆，读者还能提不同问题。"),
            qa("MQA 更省为什么主流选 GQA？",
               "g=1 时所有 Q 头被迫问同一个问题，能力受损；GQA 保留分组"
               "独立性，是显存与质量的经验最优。"),
        ],
        mechanism="解码第 t 步：新 token 的 Q 与「缓存 K/V[0..t-1] + 当前 "
                 "K/V」做注意力。缓存形状 (B, n_kv_head, S, dh)；GQA 下 "
                 "n_kv = n_head/g，Q 头按 i//g 映射到 KV 组。",
        boundary="g=1（MQA）最省但查询同质化损质量；g=n_head（MHA）最贵"
                 "质量最高。batch 大、序列长时 KV 显存主导，GQA 收益越大；"
                 "短序列小 batch 收益有限。",
        analogyBoundary="开会记录：MHA 每人一本笔记，GQA 每组共享一本，"
                       "MQA 全场一本。失效处：共享笔记不「丢信息」，但 "
                       "MQA 确实损质量——不同头查询分布不同，一组 KV 无法"
                       "同时最优满足。",
        misconceptions=[
            "公式漏掉 2（K/V 各一份）或层数 L——数量级错误。",
            "以为缓存注意力权重——缓存 K/V 张量，权重每步重算。",
            "GQA 是「减少 Q 头」——Q 头不变，减的是 KV 头。",
            "混淆 KV-Cache（省计算）与 PagedAttention（省碎片）。",
            "参数量 B（十亿）与字节 B 混写。",
        ],
        ownAnalysis="先白纸推公式 2·L·B·S·d·dtype，代入真实模型给数量级，"
                   "再引 GQA 分组比。能当场算出「70B 模型 batch=8、4K 上下文"
                   "KV 多少 GB」是强信号。收尾提 PagedAttention 和 KV 量化"
                   "（int8/fp8），展示推理栈全貌。",
        officialNotes="GQA 论文 (Ainslie 2023)；MQA (Shazeer 2019)；"
                      "PagedAttention/vLLM (Kwon 2023)；Llama-2/3 技术报告"
                      "给出各尺寸 GQA 配置。",
        interviewAnswer="公式 2LKbd×dtype → 代入 7B/70B 算量级 → GQA 显存 "
                       "÷g → MQA 质量代价 → PagedAttention 管碎片 → KV "
                       "量化再压一半，完整推理显存优化链。",
        prereq=["MHA 结构", "自回归解码流程", "fp16/bf16 字节数"],
        next_steps=["PagedAttention 与 vLLM", "KV-Cache 量化", "投机解码"],
    ),
    "diagram": diagram(
        "architecture", "MHA / GQA / MQA 的 KV 头共享结构（Q 8 头为例）",
        "GQA（g=2 组距）里每 2 个 Q 头共享 1 组 KV，KV 显存减半；"
        "MQA 全部 Q 共享 1 组，减为 1/8 但查询同质化。",
        "MHA vs GQA vs MQA 的 KV 共享对比",
        svg_compare(
            [
                {"title": "MHA（8 组 KV）", "lines": [
                    "KV 头数 = Q 头数 = 8",
                    "每头独立记忆",
                    "显存基准 1×",
                    "质量最优", "成本最高"], "hot": False},
                {"title": "GQA（4 组 KV）", "lines": [
                    "每 2 个 Q 头共享 1 组 KV",
                    "KV 头数 = 4",
                    "显存 1/2",
                    "质量 ≈ MHA",
                    "Llama-2/3 主流"], "hot": True},
                {"title": "MQA（1 组 KV）", "lines": [
                    "所有 Q 头共享 1 组 KV",
                    "KV 头数 = 1",
                    "显存 1/8",
                    "质量有损",
                    "极致吞吐"], "hot": False},
            ],
            "三种注意力方案的 KV 头数与显存",
            bottom="KV 显存 ∝ KV 头数：分组数 g 是显存与质量的旋钮"),
    ),
    "concepts": [
        concept("自回归重复计算", "无缓存时生成第 t 个 token 要对前 t 个 token "
               "全部重算 K/V，累计 O(S²)。",
               "每次加一页都重抄全书——其实只需写新页。",
               "「重抄」浪费计算，但注意力权重每步确实变；不变的只有 K/V 本身。",
               "K[i]=f(x_i) 只依赖 x_i，与后续无关——causal 结构保证历史"
               "不依赖未来，这就是可缓存的数学依据。",
               "第 t 步：新 Q(1,dh) × 缓存 K(t,dh)ᵀ → (1,t) 权重 → 加权 V。",
               ["为什么 causal 可增量解码", "双向模型为什么不行"],
               "prefill 与 decode 的计算特征差异？（并行算力密集 vs 逐 token "
               "访存密集）",
               "KV[t] = concat(KV[t-1], k_t)"),
        concept("GQA 分组共享", "Q 头分组，每组共用一组 K/V 头，KV 头数从 "
               "n_head 降到 n_head/g。",
               "8 个图书馆分馆合并成 4 个，读者人数不变。",
               "共享使不同 Q 头「看到同一份 K/V」——自由度下降是真实代价，"
               "只是经验上很小。",
               "KV 投影输出 = n_kv·dh，再 repeat/gather 到 n_head 做 attention；"
               "映射 kv_idx = i//g（也有均间隔映射，训练时需一致）。",
               "8 Q 头 + 4 KV 头：KV 投影参数与缓存均减半。",
               ["g 常取 4~8", "训练时用 GQA vs 后处理 uptraining"],
               "Llama-2-70B 用 GQA 吗？（是，8 KV 头/64 Q 头）",
               "n_kv_head = n_head // g"),
        concept("PagedAttention", "KV-Cache 切成固定大小页按需分配，"
               "逻辑连续物理离散。",
               "操作系统虚拟内存页表机制搬到 KV 显存管理。",
               "页表查询有开销，但相比消除的碎片（朴素分配实测 60%+ 浪费）"
               "完全值得。",
               "vLLM 以 block（16 token）为粒度分配；相同前缀可共享物理页"
               "（prefix caching）；batch 内碎片接近零。",
               "两条序列共享同一 system prompt 的物理页，只存一份。",
               ["内部碎片 vs 外部碎片", "prefix sharing 与 beam search 配合"],
               "朴素 KV 分配 batch 大时浪费率为何高？（按 max_seq_len 预分配，"
               "实际长度参差）",
               "logical block -> physical block 映射"),
    ],
    "problem": problem(
        statement="① 推导 KV-Cache 显存公式（含 GQA）；② numpy 实现 GQA "
                  "注意力的增量解码一步，并与全量计算对齐。",
        idea="显存：2·L·B·S·n_kv_head·dh·dtype。实现：维护 (B,n_kv,S,dh) "
             "缓存，每步 append 新 k/v；Q 按 i//g 映射到 KV 组。",
        steps=[
            "基础公式：bytes = 2(K,V) × L × B × S × d_kv × dtype",
            "GQA：d_kv = n_kv_head·dh = (n_head/g)·dh",
            "代入真实模型算数量级（7B, fp16, 4K）",
            "缓存 (B,n_kv,S,dh)，每步 concat 新 k/v",
            "Q (B,n_head,1,dh) 按组映射 → 单步注意力",
            "验证逐步解码 == 全量前向对应行",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def kv_cache_bytes(L, B, S, n_kv_head, dh, dtype_bytes=2):\n"
            "    \"\"\"KV-Cache 显存（字节）：K 和 V 各一份。\"\"\"\n"
            "    return 2 * L * B * S * n_kv_head * dh * dtype_bytes\n"
            "\n"
            "gb = kv_cache_bytes(32, 1, 4096, 32, 128) / 1024**3\n"
            "print(f'7B MHA fp16 4K ctx KV-Cache: {gb:.2f} GiB')\n"
            "assert 1.5 < gb < 2.5\n"
            "gb_gqa = kv_cache_bytes(32, 1, 4096, 4, 128) / 1024**3\n"
            "assert abs(gb_gqa - gb / 8) < 1e-9\n"
            "print(f'7B GQA(g=8) fp16 4K ctx: {gb_gqa:.2f} GiB')\n"
            "\n"
            "def softmax(x, axis=-1):\n"
            "    x = x - x.max(axis=axis, keepdims=True)\n"
            "    e = np.exp(x)\n"
            "    return e / e.sum(axis=axis, keepdims=True)\n"
            "\n"
            "rng = np.random.default_rng(3)\n"
            "n_head, g, dh = 8, 4, 16\n"
            "n_kv = n_head // g\n"
            "Kc = rng.normal(size=(1, n_kv, 6, dh))\n"
            "Vc = rng.normal(size=(1, n_kv, 6, dh))\n"
            "q = rng.normal(size=(1, n_head, 1, dh))\n"
            "kv_idx = np.arange(n_head) // g          # GQA 映射核心\n"
            "w = softmax((q @ Kc[:, kv_idx].transpose(0,1,3,2)) / np.sqrt(dh))\n"
            "out = w @ Vc[:, kv_idx]\n"
            "assert out.shape == (1, n_head, 1, dh)\n"
            "print('GQA 增量步 OK; 4 KV 头 -> 8 Q 头映射正确')\n"
        ),
        notes="kv_idx = arange(n_head)//g 是 GQA 映射本质。显存公式的单位"
              "检查：全部用「元素个数」，最后乘 dtype 字节数。7B 模型 4K "
              "上下文 MHA 约 2GB，GQA(g=8) 约 250MB——面试要报得出量级。",
        pitfalls=[
            "公式漏乘 2 或漏乘 L——差数量级。",
            "GQA 映射写反：是 Q 头 → 所属 KV 组。",
            "以为缓存注意力权重——权重每步随新 Q 变化。",
            "混淆 decode（访存密集）与 prefill（算力密集）。",
            "用 fp32 字节数套 fp16 模型——推理栈全是 fp16/bf16/int8。",
        ],
        tips="先写公式再报数字：面试官要听「4K 上下文 7B 模型 KV 约 2GB，"
             "GQA 省到 250MB」这种量级感。然后主动问「要不要看 GQA 增量"
             "解码实现」——把主动权抓在手里。",
        whyItWorks="causal 注意力里 K/V 只依赖自身位置，一次计算终身使用；"
                  "GQA 成立因为注意力质量主要由 Q 多样性决定，KV 适度共享"
                  "几乎无损。",
        examples=[],
        time="decode 单步 O(S·d)（有缓存）vs 无缓存累计 O(S²·d)",
        space="O(2·L·B·S·n_kv_head·dh) 字节级缓存",
        why="缓存把每步 K/V 计算从重算全部历史降到只算新 token；GQA 把"
            "缓存规模除以 g。",
        edgeCases=[
            "S=0（首 token）：缓存为空，注意力退化为对自身。",
            "g=n_head / g=1：两端极限，公式自洽。",
            "batch 内长度不齐：padding 或 PagedAttention 分页。",
            "int8 KV：dtype_bytes=1，显存再 ÷2，需 scale 校准。",
            "beam search：每 beam 独立缓存 ×beam 数（或共享前缀页）。",
        ],
        keyPoints=[
            "显存公式 2·L·B·S·d_kv·dtype，四个乘数一个不能漏",
            "缓存的是 K/V 张量，不是注意力权重",
            "GQA：n_kv = n_head/g，映射 kv_idx = i//g",
            "MQA 是 g=1 极限，省显存但查询同质化",
            "prefill 算力密集、decode 访存密集——优化策略完全不同",
            "PagedAttention 在管理层继续省：页化 + 前缀共享",
        ],
        variants=[
            variant(
                "MQA 极简版（g=1）",
                "所有 Q 头共享唯一一组 KV，缓存最小、广播实现最简。",
                "import numpy as np\n"
                "rng = np.random.default_rng(4)\n"
                "n_head, dh, S = 8, 16, 6\n"
                "K1 = rng.normal(size=(1, 1, S, dh))\n"
                "V1 = rng.normal(size=(1, 1, S, dh))\n"
                "q = rng.normal(size=(1, n_head, 1, dh))\n"
                "def softmax(x, axis=-1):\n"
                "    x = x - x.max(axis=axis, keepdims=True)\n"
                "    e = np.exp(x); return e / e.sum(axis=axis, keepdims=True)\n"
                "w = softmax((q @ K1.transpose(0,1,3,2)) / np.sqrt(dh))\n"
                "out = w @ V1\n"
                "assert out.shape == (1, n_head, 1, dh)\n"
                "print('MQA OK: 1 组 KV 广播到 8 头')\n",
                "吞吐优先的推理服务；也作 GQA 的理解台阶。",
                "KV 显存 1/n_head",
            ),
            variant(
                "增量 KV 缓存维护（多步循环）",
                "逐 token append 的缓存循环——decode 的真实骨架。",
                "import numpy as np\n"
                "rng = np.random.default_rng(5)\n"
                "n_kv, dh, T = 2, 8, 5\n"
                "Kbuf, Vbuf = None, None\n"
                "for t in range(T):\n"
                "    k = rng.normal(size=(1, n_kv, 1, dh))\n"
                "    v = rng.normal(size=(1, n_kv, 1, dh))\n"
                "    Kbuf = k if Kbuf is None else np.concatenate([Kbuf, k], axis=2)\n"
                "    Vbuf = v if Vbuf is None else np.concatenate([Vbuf, v], axis=2)\n"
                "    assert Kbuf.shape[2] == t + 1\n"
                "print('缓存循环 OK, 最终长度', Kbuf.shape[2])\n",
                "任何自回归推理栈的骨架；口述比手写更重要。",
                "每步 concat O(S)，生产用预分配环形缓冲",
            ),
        ],
        comparison=[
            comparison_row(["方案", "KV 头数", "KV 显存", "质量", "代表"]),
            comparison_row(["MHA", "n_head", "1×", "最优", "Llama-1, GPT-2"]),
            comparison_row(["GQA", "n_head/g", "1/g", "≈MHA", "Llama-2/3-70B, Mistral"]),
            comparison_row(["MQA", "1", "1/n_head", "有损", "PaLM, Falcon"]),
            comparison_row(["+PagedAttention", "同上", "同上(碎片≈0)", "无损", "vLLM"]),
            comparison_row(["+KV int8", "同上", "再÷2", "近无损", "FlexGen 类栈"]),
        ],
        interviewScript="「分三层：算法层——causal 保证 K/V 可缓存，decode "
                        "从 O(S²) 降每步 O(S)；结构层——GQA 把 KV 头分组共享"
                        "显存 ÷g，质量几乎无损；系统层——PagedAttention 治"
                        "碎片、KV 量化压字节。公式 2LKbd×dtype，7B 模型 4K "
                        "上下文约 2GB fp16。」",
    ),
}
