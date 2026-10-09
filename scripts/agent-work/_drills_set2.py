# -*- coding: utf-8 -*-
"""_drills_set2.py — 模型手撕深度解析 · 对齐与 RL（2 题：DPO / GAE+GRPO）。"""

from _drills_helpers import (
    diagram, teaching, lv, qa, concept, variant, comparison_row,
    problem, svg_flow, svg_compare,
)

D = {}

# ===========================================================================
# 1. 手写 DPO 损失
# ===========================================================================
D["curated-dpo-loss"] = {
    "tldr": "DPO 把 RLHF 的「奖励模型 + PPO」压成一个监督损失：用「策略与"
            "参考策略的对数概率比」隐式定义奖励，对 chosen 比 rejected 做 "
            "logistic 回归。核心是 β 控制偏离参考模型的力度——一行损失，"
            "绕开整个 RL 循环。",
    "why": "对齐方向第一道手撕题：考「从 RLHF 到 DPO 的等价变换」是否真懂，"
           "包括参考模型为什么冻结、β 的作用、completion-only masking。"
           "追问常到「DPO 何时不如 PPO」。",
    "teaching": teaching(
        progressive=[
            lv(1, "监督版直觉：让 policy 对 chosen 的对数概率变高、对 "
                  "rejected 变低，差值过 sigmoid 做二分类。"),
            lv(2, "加参考模型：不用绝对 logprob，用 log π_θ − log π_ref 衡量"
                  "「相对参考偏了多少」，防止策略整体漂移。"),
            lv(3, "理论身份：这个对数比在 RLHF 目标闭式解里就是隐式奖励 "
                  "r = β·log(π/π_ref)——DPO 是推导出来的，不是启发式。"),
            lv(4, "工程细节：mask 掉 prompt 只算 completion；β 是 KL 约束"
                  "强度（β 小偏离大）；负样本难度影响梯度——IPO/SimPO "
                  "由此出发。"),
        ],
        socratic=[
            qa("为什么必须冻结参考模型？",
               "π_ref 是 KL 约束的锚点：损失定义在相对 π_ref 的偏移上。"
               "锚点跟着更新，偏移失去意义。实现上 π_ref 只前向不反传。"),
            qa("β 变小会怎样？",
               "β 是 KL 强度的倒数代理：β 小，隐式奖励 scale 大，允许更大"
               "偏离——对齐信号强但易 reward hacking（长度爆炸、风格坍缩）。"
               "经验 0.05~0.5。"),
            qa("为什么只对 completion 算概率？",
               "prompt 在两个样本里相同，logprob 项相减完全抵消——数学上"
               "无影响，算进去只浪费算力、稀释梯度。"),
        ],
        mechanism="对偏好对 (x, y_w, y_l)：π_θ 与 π_ref 各算 y_w/y_l 的逐 "
                 "token logprob（token 求和）；Δ = [logπ_θ(y_w)−logπ_ref(y_w)]"
                 " − [logπ_θ(y_l)−logπ_ref(y_l)]；loss = −log σ(β·Δ)。"
                 "σ 饱和自带「分对就松手」的自抑制。",
        boundary="隐式奖励只相对 π_ref，只能表达偏好比较，不能给绝对奖励——"
                "无法 best-of-n 或奖励塑形。偏好数据有噪声/长短偏置时 DPO "
                "放大偏置（rejected 往往更长 → 学到「短即好」反向偏置）。",
        analogyBoundary="教练不给分数只说「这个比那个好」，学员相对旧动作"
                       "（π_ref）改进。失效处：教练判断完全来自数据，偏好"
                       "数据有偏则学偏——数据质量是 DPO 天花板。",
        misconceptions=[
            "忘减参考 logprob——退化成无约束偏好分类，策略整体漂移。",
            "对整个序列（含 prompt）算 logprob——抵消但浪费、梯度稀释。",
            "β 含义搞反：β 是 KL 强度不是学习率，小 β 更激进。",
            "以为 DPO 里有奖励模型前向——隐式奖励只是对数比的名字，"
            "实现里没有这个网络。",
            "对 logprob 做 mean 而非 sum——变长序列被稀释，与论文不一致"
            "（除非有意做 length 归一化变体）。",
        ],
        ownAnalysis="写码前先画 2×2 矩阵：policy/ref × chosen/rejected 的"
                   "四个 logprob。最容易错的是 response_mask 的位置"
                   "（gather 后求和）。主动对比 PPO：DPO 无采样、无 value、"
                   "无 clip，稳定性来自闭式解；代价是没有在线探索，天花板"
                   "受数据质量限制。",
        officialNotes="DPO 论文 (Rafailov 2023) §4 完整推导；HF TRL "
                      "DPOTrainer 源码；IPO (Azar 2023) 分析 DPO 在确定性"
                      "偏好下的过拟合。",
        interviewAnswer="从 RLHF 目标推隐式奖励 → 一行损失 → 落码（四 "
                       "logprob + mask + −logσ(βΔ)）→ β/参考模型/"
                       "completion-only 三工程点 → 对比 PPO 与 IPO/SimPO "
                       "方向。",
        prereq=["RLHF 两阶段流程", "KL 约束的策略梯度", "logistic 回归"],
        next_steps=["GRPO/GAE", "IPO/SimPO/KTO", "RLAIF 与偏好数据构造"],
    ),
    "diagram": diagram(
        "architecture", "DPO：偏好对上的四路对数概率与损失装配",
        "policy 与参考模型各前向两次（chosen/rejected）得四个序列级对数"
        "概率；两两相减得相对偏移 Δ，经 β 缩放做 logistic 回归。",
        "DPO 损失的数据流",
        svg_flow([
            {"label": "π_θ(y_w|x)  chosen 的策略对数概率", "in": "(x, y_w)",
             "out": "logp_w", "hot": True,
             "note": "只对 completion 求和（response_mask）"},
            {"label": "π_ref(y_w|x)  chosen 的参考对数概率", "in": "(x, y_w)",
             "out": "ref_w", "note": "参考模型冻结：不积累梯度"},
            {"label": "π_θ(y_l|x) / π_ref(y_l|x)  rejected 同理", "in": "(x, y_l)",
             "out": "logp_l, ref_l", "hot": True,
             "note": "四个量是损失的全部输入"},
            {"label": "Δ = (logp_w − ref_w) − (logp_l − ref_l)",
             "in": "四个标量", "out": "Δ（每对一个）",
             "note": "相对参考模型的偏好偏移"},
            {"label": "loss = −log σ(β·Δ)", "in": "β·Δ", "out": "标量",
             "hot": True,
             "note": "softplus(−x) 数值稳定实现"},
        ], "DPO 四路对数概率装配成单个损失"),
    ),
    "concepts": [
        concept("隐式奖励", "r(x,y) = β·log[π(y|x)/π_ref(y|x)]——RLHF 最优解"
               "的反解形式，DPO 用它替代显式奖励模型。",
               "汇率：不直接标价，只标相对基准货币（参考模型）的兑换率。",
               "汇率可双向换算，隐式奖励只有相对意义——不同 π_ref 下的"
               "「隐式奖励」不可比较。",
               "把 r 代回 KL 约束 RL 目标，π* ∝ π_ref·exp(r/β) 恒成立——"
               "奖励被吸收进策略的 Bradley-Terry 推导。",
               "logp_w − ref_w = 2.0 → 隐式奖励 2β。",
               ["Bradley-Terry 模型", "KL 约束 RL 闭式解"],
               "为什么不需要 value 网络？（损失是序列级闭式，无信用分配）",
               "r̂ = β·(log π_θ − log π_ref)"),
        concept("β 与 KL 约束", "β 是隐式奖励 scale，等价 RLHF 中 KL 惩罚"
               "强度的旋钮。",
               "风筝线松紧：线紧（β 大）飞不高但稳，线松（β 小）飞得高"
               "但易断线。",
               "风筝线是硬约束，KL 是软惩罚——β 再大也只是「强烈建议」。",
               "β→∞：微小偏移即主导损失，策略几乎不动；β→0：σ 近似线性"
               "失去饱和自抑制。经验 0.05~0.5。",
               "β=0.1 时 Δ=5 → σ(0.5)≈0.62 仍有梯度；Δ=20 → σ(2)≈0.88。",
               ["损失饱和与梯度消失", "β 与 reward hacking"],
               "β=0.1 与 0.5 哪个易长度爆炸？（0.1，偏离更自由）",
               "loss = −log σ(β·Δ)"),
        concept("completion-only masking", "logprob 只在 response token 上"
               "求和，prompt 位置乘 0。",
               "只给答案判卷，题目不计分。",
               "不只是规则：两样本 prompt 相同，计分项精确抵消——"
               "mask 是纯收益。",
               "mask = response 位置 1；logp = (token_logprobs·mask).sum(-1)。"
               "gather 取 target token 的 logprob。",
               "[prompt 512][response 128]：只累加后 128 个位置。",
               ["gather 与 onehot 等价", "padding 位置处理"],
               "多轮拼接 prompt 不同时抵消还成立吗？（不成立，mask 仍是"
               "优化但语义上 prompt 项不再抵消）",
               "logp = (logp_tok * resp_mask).sum(-1)"),
    ],
    "problem": problem(
        statement="用 numpy 实现 DPO 损失：输入 chosen/rejected 各自的逐 "
                  "token logprobs（policy 与 ref 各一份）、response_mask、β；"
                  "输出标量损失与逐对 margin。要求 completion-only 求和、"
                  "数值稳定的 log σ。",
        idea="四路序列 logprob（mask 求和）→ Δ = 相对偏移之差 → "
             "loss = −logσ(βΔ)，用 softplus(−x) 稳定形式。",
        steps=[
            "序列 logprob：sum(token_logprobs · response_mask)",
            "四个标量：logp_w, ref_w, logp_l, ref_l（batch 逐对）",
            "Δ = (logp_w − ref_w) − (logp_l − ref_l)",
            "数值稳定：−logσ(x) = max(−x,0) + log1p(exp(−|x|))",
            "返回 loss 与 margin（βΔ 均值，训练监控用）",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def seq_logprobs(token_lp, mask):\n"
            "    \"\"\"(B,S) 逐 token logprob 与 response mask -> (B,)。\"\"\"\n"
            "    return (token_lp * mask).sum(axis=-1)\n"
            "\n"
            "def dpo_loss(lp_w, lp_l, ref_w, ref_l, beta=0.1):\n"
            "    \"\"\"四个 (B,) 序列级 logprob -> (loss, margin)。\"\"\"\n"
            "    delta = (lp_w - ref_w) - (lp_l - ref_l)\n"
            "    x = beta * delta\n"
            "    loss = np.maximum(-x, 0) + np.log1p(np.exp(-np.abs(x)))\n"
            "    return loss.mean(), delta.mean()\n"
            "\n"
            "# 自测 1：chosen 更优时 loss 更小\n"
            "rng = np.random.default_rng(6)\n"
            "B, S = 4, 16\n"
            "mask = np.ones((B, S))\n"
            "lp_w  = rng.normal(-1.0, 0.5, (B, S))\n"
            "lp_l  = rng.normal(-3.0, 0.5, (B, S))\n"
            "ref_w = rng.normal(-1.2, 0.5, (B, S))\n"
            "ref_l = rng.normal(-2.8, 0.5, (B, S))\n"
            "loss_good, m1 = dpo_loss(seq_logprobs(lp_w, mask),\n"
            "                         seq_logprobs(lp_l, mask),\n"
            "                         seq_logprobs(ref_w, mask),\n"
            "                         seq_logprobs(ref_l, mask))\n"
            "loss_bad, m2 = dpo_loss(seq_logprobs(lp_l, mask),\n"
            "                        seq_logprobs(lp_w, mask),\n"
            "                        seq_logprobs(ref_w, mask),\n"
            "                        seq_logprobs(ref_l, mask))\n"
            "assert loss_good < loss_bad\n"
            "\n"
            "# 自测 2：completion-only —— prompt 换成任何内容都不影响\n"
            "prompt_lp = rng.normal(size=(B, 8))\n"
            "full1 = np.concatenate([prompt_lp, lp_w], axis=1)\n"
            "full2 = np.concatenate([prompt_lp * 3 + 1, lp_w], axis=1)\n"
            "m = np.concatenate([np.zeros((B, 8)), np.ones((B, S))], axis=1)\n"
            "assert np.allclose(seq_logprobs(full1, m), seq_logprobs(full2, m))\n"
            "\n"
            "# 自测 3：β 单调性——同样 Δ，β 越大已越「分对」\n"
            "l1, _ = dpo_loss(np.array([0.]), np.array([-5.]),\n"
            "                 np.array([0.]), np.array([0.]), beta=0.1)\n"
            "l2, _ = dpo_loss(np.array([0.]), np.array([-5.]),\n"
            "                 np.array([0.]), np.array([0.]), beta=1.0)\n"
            "assert l2 < l1\n"
            "print('DPO OK: good=%.4f < bad=%.4f' % (loss_good, loss_bad))\n"
        ),
        notes="数值稳定关键：−logσ(x) 写成 softplus(−x) 的分段形式。"
              "margin（βΔ 均值）是核心监控指标：应缓升，骤升伴随长度膨胀"
              "要立刻查数据偏置。",
        pitfalls=[
            "四路 logprob 混入 prompt token——mask 拼接错一格。",
            "先 sigmoid 再 log：σ 下溢为 0 时 log(0)=−inf；必须 softplus。",
            "参考模型忘 no_grad：显存翻倍梯度错误。",
            "β 与学习率混淆，同时拉大导致策略崩溃。",
            "batch 内配对被打乱：chosen_i 必须与 rejected_i 配对。",
            "mean-over-tokens 替代 sum：与论文不一致，长回答被压低。",
        ],
        tips="先讲推导再写码：KL 约束 RL 目标 → 隐式奖励 → Bradley-Terry，"
             "30 秒讲清「DPO 是推导出来的」。落码后主动说 margin 监控与"
             "失败模式（长度偏置、β 过小）。",
        whyItWorks="RLHF 的 KL 约束目标有闭式最优解 π* ∝ π_ref·exp(r/β)，"
                  "反解 r 代入 Bradley-Terry，奖励项消去，只剩 π_θ 与 π_ref "
                  "的对数比——两阶段变一个监督损失。",
        examples=[],
        time="4 次前向 + O(B·S) 损失",
        space="policy + ref 两份激活（ref 无梯度可省优化器态）",
        why="无采样、无奖励网络、无 value 模型——在线 RL 三件套全换两次"
            "额外前向。",
        edgeCases=[
            "Δ 极大：σ 饱和梯度→0，自带停止信号。",
            "Δ=0：损失 = log2，梯度最大。",
            "两样本只差一个 token：margin 信号极弱，最难样本。",
            "β=0：退化为线性，必须 β>0。",
            "初始时 π_θ == π_ref：Δ=0，损失从 log2 起步。",
        ],
        keyPoints=[
            "隐式奖励 r = β·log(π/π_ref)，参考模型必须冻结",
            "Δ = 相对偏移之差，四路 logprob 缺一不可",
            "completion-only mask：prompt 项抵消，也必须做",
            "−logσ(βΔ) 用 softplus 稳定实现",
            "β 是 KL 强度旋钮：小 β 激进易 hack，大 β 保守",
            "无在线探索：上限 = 偏好数据质量（IPO/SimPO 起点）",
        ],
        variants=[
            variant(
                "IPO",
                "把 −logσ 换成 (Δ − 1/(2β))² 平方形式，确定性偏好下"
                "不再把 margin 推向无穷（DPO 会过拟合）。",
                "import numpy as np\n"
                "def ipo_loss(lp_w, lp_l, ref_w, ref_l, beta=0.5):\n"
                "    delta = (lp_w - ref_w) - (lp_l - ref_l)\n"
                "    tau = 1.0 / (2 * beta)\n"
                "    return float(((delta - tau) ** 2).mean())\n"
                "l = ipo_loss(np.array([0.]), np.array([-3.]),\n"
                "             np.array([0.]), np.array([0.]))\n"
                "assert l > 0\n"
                "print('IPO OK, loss=%.3f（margin 目标 1/(2β)=1）' % l)\n",
                "偏好数据基本无噪、担心 DPO margin 失控时。",
                "同 DPO",
            ),
            variant(
                "SimPO 思路（长度归一化 + 无参考模型）",
                "用平均 logprob 替代求和并去掉参考模型，抑制「短回答"
                "偏好」反向偏置。",
                "import numpy as np\n"
                "def simpo_margin(lp_w, len_w, lp_l, len_l,\n"
                "                 beta=2.0, gamma=0.5):\n"
                "    nw, nl = lp_w / len_w, lp_l / len_l\n"
                "    x = beta * (nw - nl) - gamma\n"
                "    return float(np.log1p(np.exp(-x)).mean())\n"
                "l = simpo_margin(np.array([-10.]), np.array([10.]),\n"
                "                 np.array([-30.]), np.array([10.]))\n"
                "assert l >= 0\n"
                "print('SimPO 风格 OK, loss=%.3f' % l)\n",
                "观察到长度偏置、想省参考模型前向时。",
                "省 1 次前向",
            ),
        ],
        comparison=[
            comparison_row(["方法", "需要 RM", "采样", "value 网络", "在线", "代表问题"]),
            comparison_row(["PPO-RLHF", "是", "是", "是", "是", "训练复杂超参多"]),
            comparison_row(["DPO", "否(隐式)", "否", "否", "否", "受数据限、长度偏置"]),
            comparison_row(["IPO", "否", "否", "否", "否", "修 DPO 过拟合"]),
            comparison_row(["SimPO", "否", "否", "否", "否", "长度归一化无参考"]),
            comparison_row(["KTO", "否", "否", "否", "否", "不需成对数据"]),
        ],
        interviewScript="「推导链：KL 约束 RLHF 最优解 π* ∝ π_ref·exp(r/β) "
                        "→ 反解隐式奖励 → 代入 Bradley-Terry 得一行损失 "
                        "−logσ(βΔ)，Δ 是 policy 与 ref 对数概率偏移之差。"
                        "实现四点：参考模型冻结、completion-only mask、"
                        "softplus 稳定、β 即 KL 强度。对比 PPO 省掉采样/"
                        "RM/value 三件套，代价是没有在线探索——IPO、SimPO "
                        "等变体由此出发。」",
    ),
}

# ===========================================================================
# 2. 手写 GAE 与 GRPO 目标函数
# ===========================================================================
D["curated-gae-and-grpo"] = {
    "tldr": "GAE 用 λ 在「低方差有偏的 TD」与「无偏高方差的 MC」间插值出"
            "优势；GRPO 扔掉 value 网络，用同一 prompt 一组采样的组内均值"
            "当 baseline——群体相对策略优化，名字即实现。",
    "why": "RLHF/推理 RL（DeepSeek-R1 路线）核心更新规则。考两点：GAE 的"
           "λ-递推白板展开；GRPO 为什么能去 value 模型、组基线与 REINFORCE "
           "with baseline 的关系。",
    "teaching": teaching(
        progressive=[
            lv(1, "优势定义 A(s,a) = Q − V：比「平均回报」好多少。GAE 给它"
                  "一个低方差估计。"),
            lv(2, "TD 残差 δ_t = r_t + γV(s_{t+1}) − V(s_t) 是优势的单步成分；"
                  "GAE(λ) = Σ (γλ)^l δ_{t+l}，λ 是偏差-方差旋钮。"),
            lv(3, "GRPO：同一 prompt 采 G 个回答，A_i = (r_i − mean)/std，"
                  "直接当每个 token 的优势——不要 value 网络不要 GAE。"),
            lv(4, "组合：loss = −min(ratio·A, clip(ratio)·A) + β·KL，"
                  "KL 用 k3 = exp(Δ)−Δ−1 估计器。"),
        ],
        socratic=[
            qa("λ=0 和 λ=1 分别是什么？",
               "λ=0 → Â = δ，纯 TD(0)：方差最小、依赖 V 准确性（有偏）；"
               "λ=1 → 折扣 MC：无偏但方差大。GAE 是指数加权混合，经验 "
               "λ≈0.95。"),
            qa("GRPO 为什么可以不要 value 网络？",
               "value 的作用是给「同状态不同动作」共同基线；同组 G 个回答"
               "的均值天然构成基线，且与单条采样无关（不引入偏差）。"),
            qa("组内标准化有什么隐患？",
               "全对/全错组（std=0）没有梯度信号——难题易题都学不到，"
               "需要过采样过滤或 ε 防除零；归一化也让不同难度题的梯度"
               "规模一致，隐式加权。"),
        ],
        mechanism="GAE 递推：Â_T = δ_{T-1}；Â_t = δ_t + γλ·Â_{t+1}，反向一遍。"
                 "GRPO：组内 reward z-score 得标量优势 → 广播到回答所有 "
                 "token → ratio = exp(logπ_θ − logπ_old) → PPO 式 clip + "
                 "参考策略 KL。",
        boundary="GAE 偏差来自 V 的误差：V 差时 λ 要小，V 准时 λ 可大。"
                 "GRPO 依赖「组内可比」：全对/全错信号塌缩；G 是方差与"
                 "算力的交换（R1 用 64）。",
        analogyBoundary="GAE 像按可信度加权汇总多人汇报；λ 是「最近的话权重"
                       "高」。失效处：衰减是指数的且带折扣 γ，汇总对象是 "
                       "TD 残差不是回报。GRPO 像同题作文互评取相对名次——"
                       "全员满分时名次无意义，正对应 std=0 塌缩。",
        misconceptions=[
            "GAE 递推方向写反——必须反向递推，正向展开 O(T²)。",
            "γ 和 λ 混淆：γ 折扣未来回报（环境性质），λ 混合 TD/MC（估计器）。",
            "GRPO 优势忘 detach——基线被梯度拉扯，训练发散。",
            "std 不加 eps，全同组除零 NaN。",
            "以为 GRPO = PPO 去 clip——clip 还在，去掉的是 value 网络，"
            "KL 换了 k3 估计器。",
        ],
        ownAnalysis="GAE 给 5 步轨迹手推一遍（δ 与 Â 两行表）最能展示理解。"
                   "GRPO 强调三个梯度细节：基线 detach、ratio 的 log 域计算、"
                   "KL 用 k3（无偏恒正低方差）。收尾对比 RLOO（去自身均值"
                   "基线）：对组内相关更稳健。",
        officialNotes="GAE (Schulman 2016) §3 递推推导；GRPO 出自 "
                      "DeepSeekMath (Shao 2024) §4，DeepSeek-R1 推向推理 RL；"
                      "PPO (Schulman 2017) 附录的 clip 与 k1/k3 估计器。",
        interviewAnswer="δ_t 定义 → GAE 反向递推一行 → λ 偏差方差权衡 → "
                       "GRPO 组内标准化 + clip + k3 KL → 为什么能去 value "
                       "网络 → 全对全错塌缩与对策。",
        prereq=["策略梯度与 baseline", "TD 学习", "PPO clip 目标"],
        next_steps=["R1 的规则奖励", "RLOO/ReMax", "过程奖励模型 PRM + GRPO"],
    ),
    "diagram": diagram(
        "architecture", "GAE 反向递推与 GRPO 组内标准化",
        "左：优势从最后一步反向累积 TD 残差（λ 控制混合）。右：同一 prompt "
        "的 G 个回答经组内 z-score 得优势，广播到每个 token 进入 PPO 式更新。",
        "GAE 递推与 GRPO 组基线示意",
        svg_compare(
            [
                {"title": "GAE（有 value 网络）", "lines": [
                    "δ_t = r + γV(s') − V(s)",
                    "Â_T = δ_{T-1}",
                    "Â_t = δ_t + γλÂ_{t+1}（反向）",
                    "λ=0: TD 低方差有偏",
                    "λ=1: MC 无偏高方差"], "hot": True},
                {"title": "GRPO（无 value 网络）", "lines": [
                    "采 G 个回答/题",
                    "A_i = (r_i − μ)/σ（组内）",
                    "广播到回答每个 token",
                    "ratio + clip + KL(k3)",
                    "全对/全错 → 信号塌缩"], "hot": False},
            ],
            "GAE 与 GRPO 的优势来源对比",
            bottom="两者不互斥：带 value/PRM 的 GRPO 变体仍可用 GAE"),
    ),
    "concepts": [
        concept("TD 残差", "δ_t = r_t + γV(s_{t+1}) − V(s_t)：一步真实与估计"
               "的差，优势的单步成分。",
               "预期外的惊喜：实际拿到的比预期的 V(s) 好多少。",
               "「惊喜」大小依赖 V 估得准——V 不准则 δ 有偏，这正是 GAE "
               "需要混合的原因。",
               "V = 真值时 E[δ_t]=0；k 步优势估计 = Σ γ^l δ_{t+l}。",
               "r=1, γ=0.9, V(s')=5, V(s)=4 → δ = 1 + 4.5 − 4 = 1.5。",
               ["贝尔曼方程", "优势函数定义"],
               "δ 期望是 0 吗？（V=真值时是；V 有偏时不是——GAE 偏差来源）",
               "δ_t = r_t + γV(s_{t+1}) − V(s_t)"),
        concept("λ 的偏差-方差插值", "GAE(λ) = Σ (γλ)^l δ_{t+l}：λ 从 0 到 1 "
               "在 TD 与 MC 间指数插值。",
               "听证词：只听最近的（λ=0）信息少但清晰；全信（λ=1）信息全"
               "但噪声大。",
               "证词清晰度外生；δ 的偏差来自 V 本身——V 越准 λ 可越大。",
               "k 步回报 A^(k) = Σ_{l<k} γ^l δ_{t+l} + γ^k V(s_{t+k})；"
               "实现用反向递推 O(T)。",
               "γλ = 0.9×0.95 = 0.855：每远一步权重乘 0.855。",
               ["k 步回报展开", "γ 与 λ 独立作用"],
               "为什么反向递推？（正向 O(T²)，反向 O(T)）",
               "Â_t = δ_t + γλ·Â_{t+1}"),
        concept("组内基线", "GRPO 对同 prompt 的 G 个回答算 reward 的"
               "均值/方差，优势标准化。",
               "同题作文互排名：不必知道绝对多少分算好。",
               "名次只在该题内可比；但策略梯度本就只需组内相对优势，无碍。",
               "A_i = (r_i − μ)/(σ + ε)，detach 后广播到 token 维；"
               "μ_group 是该状态的蒙特卡洛 value 估计。",
               "G=8，reward [1,1,0,0,1,0,0,0] → μ=0.375 按位标准化。",
               ["baseline 无偏性条件", "eps 防除零"],
               "组内全对时梯度？（优势全 0，无更新——难点信号丢失）",
               "A = (r − r.mean()) / (r.std() + eps)"),
    ],
    "problem": problem(
        statement="① 实现 GAE：输入 rewards/values/dones/γ/λ，输出优势与"
                  "回报（反向递推），并验证 λ=0/1 两个端点；② 实现 GRPO "
                  "一步：组内标准化优势、ratio、clip、k3 KL，验证梯度方向。",
        idea="GAE：δ_t 逐位算，Â_t = δ_t + γλ·Â_{t+1} 反向扫描。GRPO："
             "组维 z-score（detach），ratio log 域相减后 exp，"
             "min(unclipped, clipped) − β·KL。",
        steps=[
            "δ_t = r_t + γ·V_{t+1}·(1−done) − V_t",
            "Â 反向递推，returns = Â + V",
            "GRPO：rewards 组维 z-score → A 广播 (G,T)",
            "ratio = exp(logp_θ − logp_old)，clip [1−ε, 1+ε]",
            "surrogate = min(ratio·A, clip(ratio)·A)",
            "loss = −mean(surr) + β·mean(k3)",
        ],
        python=(
            "import numpy as np\n"
            "\n"
            "def gae(rewards, values, last_value, dones, gamma=0.99, lam=0.95):\n"
            "    T = len(rewards)\n"
            "    adv = np.zeros(T)\n"
            "    gae_next = 0.0\n"
            "    for t in reversed(range(T)):\n"
            "        v_next = last_value if t == T - 1 else values[t + 1]\n"
            "        nonterm = 0.0 if dones[t] else 1.0\n"
            "        delta = rewards[t] + gamma * v_next * nonterm - values[t]\n"
            "        gae_next = delta + gamma * lam * nonterm * gae_next\n"
            "        adv[t] = gae_next\n"
            "    return adv, adv + values\n"
            "\n"
            "# 端点自测：λ=0 -> 纯 TD 残差；λ=1 -> 折扣 MC\n"
            "r = np.array([1.0, 0.0, 1.0, 0.0, 1.0])\n"
            "v = np.array([0.5, 0.6, 0.7, 0.8, 0.9])\n"
            "done = np.zeros(5)\n"
            "adv0, _ = gae(r, v, 1.0, done, gamma=0.9, lam=0.0)\n"
            "delta0 = r + 0.9 * np.concatenate([v[1:], [1.0]]) - v\n"
            "assert np.allclose(adv0, delta0)\n"
            "adv1, _ = gae(r, v, 1.0, done, gamma=0.9, lam=1.0)\n"
            "mc = np.array([sum(0.9**(k-t) * r[k] for k in range(t, 5))\n"
            "               + 0.9**(5-t) * 1.0 - v[t] for t in range(5)])\n"
            "assert np.allclose(adv1, mc, atol=1e-9)\n"
            "\n"
            "def grpo_step(logp_new, logp_old, ref_logp, rewards,\n"
            "              clip=0.2, beta=0.04, eps=1e-6):\n"
            "    \"\"\"logp: (G,T) 同一 prompt 的 G 个回答 -> 标量损失。\"\"\"\n"
            "    r = np.asarray(rewards, float)\n"
            "    mu, sd = r.mean(), r.std() + eps\n"
            "    A = np.broadcast_to(((r - mu) / sd)[:, None], logp_new.shape)\n"
            "    ratio = np.exp(logp_new - logp_old)\n"
            "    surr = np.minimum(ratio * A,\n"
            "                      np.clip(ratio, 1 - clip, 1 + clip) * A)\n"
            "    kl = np.exp(logp_new - ref_logp) - (logp_new - ref_logp) - 1\n"
            "    return float(-surr.mean() + beta * kl.mean())\n"
            "\n"
            "rng = np.random.default_rng(7)\n"
            "G, T = 8, 4\n"
            "base = rng.normal(size=(G, T)) * 0.1\n"
            "rewards = np.array([1, 1, 1, 0, 0, 0, 1, 0.])\n"
            "# 只改变「好回答」(reward>0) 的 logp：这才是策略更新会做的事\n"
            "good = (rewards > 0).astype(float)[:, None]\n"
            "l_good = grpo_step(base + 0.3 * good, base, base, rewards)\n"
            "l_bad  = grpo_step(base - 0.3 * good, base, base, rewards)\n"
            "assert l_good < l_bad, '提高好回答概率应降低损失'\n"
            "l_flat = grpo_step(base + 0.3, base, base, np.ones(G))\n"
            "print('GAE+GRPO OK: good=%.4f < bad=%.4f, 全对组=%.4f（仅 KL）'\n"
            "      % (l_good, l_bad, l_flat))\n"
        ),
        notes="端点自测是 GAE 的灵魂：λ=0/1 分别对齐 TD 与折扣 MC。GRPO "
              "的 A broadcast 到 token 维；真实实现 logp 在 torch 反向，"
              "numpy 版用「好回答概率升 → 损失降」验证方向。全对组只剩 "
              "KL 项——信号塌缩的现场演示。",
        pitfalls=[
            "GAE 正向展开 O(T²)——结果对但面试官必追问复杂度。",
            "dones 处理漏掉：终止步后状态值必须截断。",
            "GRPO 优势没 detach（torch 里）——基线被拉扯发散。",
            "std 不加 eps：全对/全错组 NaN。",
            "KL 用 k1 = log_ratio：可正可负，会奖励「偏离后回来」；k3 恒正。",
            "ratio 在概率域相除下溢，应 log 域相减再 exp。",
        ],
        tips="GAE 讲「λ 两个端点」一句话定位深度；GRPO 强调名字即实现——"
             "group relative，基线就是组内均值。主动提全对/全错塌缩与 "
             "RLOO 对比，跟到 R1 前沿。",
        whyItWorks="GAE 递推是 λ 加权 k 步回报的闭式整理；GRPO 组均值 "
                  "baseline 与单条动作无关 ⇒ 不引入偏差，value 网络被组"
                  "采样天然替代。",
        examples=[],
        time="GAE O(T)；GRPO O(G·T) 前向 ×2（policy + ref）",
        space="GAE O(T)；GRPO 存 G 个回答的 logp（ref 可在线算）",
        why="两者都把「信用分配」变成可估的差分：GAE 用 V 差分，GRPO 用"
            "组间差分。",
        edgeCases=[
            "T=1：退化为单步 δ。",
            "全 done：nonterm 截断，adv 只含当前步。",
            "组内 std=0：优势全零，需过滤或留 KL 项。",
            "G=2：组基线方差极大，近似二元比较（DPO 的在线版）。",
            "λ=0/1 端点必须能被单元测试对齐（本实现已验证）。",
        ],
        keyPoints=[
            "δ_t = r + γV(s') − V(s)；Â_t = δ_t + γλÂ_{t+1} 反向递推",
            "λ=0 → TD（低方差有偏），λ=1 → MC（无偏高方差）",
            "GRPO 优势 = 组内 z-score，detach 后广播到 token",
            "ratio 在 log 域算，clip 仍保留",
            "KL 用 k3 = exp(Δ)−Δ−1：恒正、低方差",
            "全对/全错组塌缩：过滤、ε、或过程奖励补充",
        ],
        variants=[
            variant(
                "RLOO（leave-one-out 基线）",
                "基线 = 组内其余样本均值（去掉自己），对组内相关更稳健，"
                "实现更简单。",
                "import numpy as np\n"
                "def rloo_advantage(rewards, eps=1e-6):\n"
                "    r = np.asarray(rewards, float)\n"
                "    G = len(r)\n"
                "    base = (r.sum() - r) / (G - 1)\n"
                "    return r - base\n"
                "adv = rloo_advantage([1, 1, 0, 0, 1, 0, 0, 0])\n"
                "assert abs(adv.sum()) < 1e-9\n"
                "print('RLOO OK:', np.round(adv, 3))\n",
                "GRPO 的稳健替代（HF TRL 有实现）；组小 G<8 时尤佳。",
                "同 GRPO，少一个 std",
            ),
            variant(
                "带长度惩罚的 GRPO 奖励",
                "推理 RL 在规则奖励上加长度惩罚抑制冗长——奖励塑形发生在"
                "组标准化之前。",
                "import numpy as np\n"
                "def shaped_rewards(correct, lengths, alpha=0.01):\n"
                "    r = np.asarray(correct, float) - alpha * np.asarray(lengths)\n"
                "    return (r - r.mean()) / (r.std() + 1e-6)\n"
                "a = shaped_rewards([1, 1, 0], [120, 40, 80])\n"
                "assert a[1] > a[0]   # 同对，短者优势更大\n"
                "print('长度塑形 OK:', np.round(a, 3))\n",
                "R1 类推理任务防「think 得又长又水」。",
                "同 GRPO",
            ),
        ],
        comparison=[
            comparison_row(["估计器", "需要 V", "基线来源", "偏差", "方差", "备注"]),
            comparison_row(["REINFORCE", "否", "无", "无", "极高", "原始策略梯度"]),
            comparison_row(["REINFORCE+baseline", "可选", "状态值", "低", "高", "需学 V"]),
            comparison_row(["GAE(λ)", "是", "V 差分", "λ 调节", "λ 调节", "AC 系标配"]),
            comparison_row(["GRPO", "否", "组均值/std", "低", "随 G 降", "R1/DeepSeekMath"]),
            comparison_row(["RLOO", "否", "去自身组均值", "无", "随 G 降", "更稳健"]),
        ],
        interviewScript="「GAE 先写 δ_t 再反向递推 Â，端点 λ=0/1 对齐 TD 和 "
                        "MC，λ 是偏差方差旋钮。GRPO 把信用分配换成组内比较："
                        "G 个回答 z-score 得优势，detach、广播、进 PPO 式 "
                        "clip，KL 用 k3。value 网络被组均值替代——这正是 R1 "
                        "推理 RL 能跑起来的工程前提。全对全错组会塌缩，"
                        "实际要过采样过滤或加长度塑形。」",
    ),
}
