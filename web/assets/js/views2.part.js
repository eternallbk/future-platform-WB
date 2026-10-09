/* ============================================================================
 * Future · 求职学习工作台 — views2.js (part 3)
 * 公式剖析 · 题库定位 · 仓库与课程 · 岗位看板 · 技能矩阵 · 学习路线 ·
 * 进度统计 · 收藏夹 · 采集运行 · 详情抽屉 · 启动引导
 * ========================================================================= */

/* ============================== FORMULAS =============================== */

const FORMULA_SEED = [
  {
    id: 'f-attention', name: '缩放点积注意力 (Scaled Dot-Product Attention)', category: 'foundation', glyph: 'A',
    tags: ['transformer', 'attention', 'mha'],
    latex: 'Attention(Q,K,V) = softmax( Q Kᵀ / √d_k ) V',
    html: `<var>Attention</var>(<var>Q</var>,<var>K</var>,<var>V</var>) =
      softmax<span style="font-size:1.35em">(</span>
      <span class="frac"><span><var>Q</var><var>K</var><sup>⊤</sup></span><span>√<var>d</var><sub>k</sub></span></span>
      <span style="font-size:1.35em">)</span><var>V</var>`,
    symbols: [
      ['Q ∈ ℝ^{n×d_k}', '查询矩阵：n 个 token 各自「想找什么」'],
      ['K ∈ ℝ^{m×d_k}', '键矩阵：m 个位置「能提供什么」'],
      ['V ∈ ℝ^{m×d_v}', '值矩阵：真正被加权求和的内容'],
      ['√d_k', '缩放因子，防止点积随维度增大而方差爆炸、softmax 进入饱和区'],
    ],
    derivation: [
      '假设 Q、K 各维独立、均值 0、方差 1，则点积 q·k 的方差为 d_k，量级随维度线性增长。',
      '把 logits 除以 √d_k，方差回到 1 量级，softmax 的梯度不会因饱和而消失。',
      '对每一行做 softmax 得到行随机矩阵，再右乘 V 得到上下文向量。',
      '多头：把 d_model 拆成 h 份并行做上式，再拼接并过 W^O —— 让不同子空间学不同的对齐关系。',
    ],
    analogy: '像查字典：Q 是你要查的词，K 是每个词条的索引，点积衡量「匹配度」，softmax 把匹配度变成抽取比例，V 是你真正抄下来的释义。除以 √d_k 相当于把音量调到合适档位——太大会削波（饱和），太小听不见（梯度平坦）。',
    code: `import math, torch, torch.nn as nn

class MHA(nn.Module):
    def __init__(self, d_model=512, n_head=8):
        super().__init__()
        assert d_model % n_head == 0
        self.h, self.dk = n_head, d_model // n_head
        self.qkv = nn.Linear(d_model, 3 * d_model)
        self.proj = nn.Linear(d_model, d_model)

    def forward(self, x, causal=True):
        B, T, C = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        # (B, h, T, dk)
        q, k, v = (t.view(B, T, self.h, self.dk).transpose(1, 2) for t in (q, k, v))
        att = q @ k.transpose(-2, -1) / math.sqrt(self.dk)
        if causal:
            mask = torch.triu(torch.ones(T, T, dtype=torch.bool, device=x.device), 1)
            att = att.masked_fill(mask, float("-inf"))
        att = att.softmax(-1)
        out = (att @ v).transpose(1, 2).reshape(B, T, C)
        return self.proj(out)`,
    pitfalls: [
      '忘了 mask 要在 softmax 之前使用 -inf，而不是置 0。',
      '缩放用 √d_k 而不是 √d_model；d_k = d_model / h。',
      'softmax 前若不减最大值，fp16 下容易溢出（面试常问「数值稳定」）。',
    ],
    sources: [{ title: 'Attention Is All You Need', url: 'https://arxiv.org/abs/1706.03762' }],
  },
  {
    id: 'f-dpo', name: 'DPO 直接偏好优化损失', category: 'posttraining', glyph: 'D',
    tags: ['dpo', 'alignment', 'rlhf'],
    html: `<var>L</var><sub>DPO</sub> = −𝔼<sub>(x, y<sub>w</sub>, y<sub>l</sub>)</sub>
      log σ<span style="font-size:1.35em">(</span><var>β</var> log
      <span class="frac"><span><var>π</var><sub>θ</sub>(<var>y</var><sub>w</sub>|<var>x</var>)</span><span><var>π</var><sub>ref</sub>(<var>y</var><sub>w</sub>|<var>x</var>)</span></span>
      − <var>β</var> log
      <span class="frac"><span><var>π</var><sub>θ</sub>(<var>y</var><sub>l</sub>|<var>x</var>)</span><span><var>π</var><sub>ref</sub>(<var>y</var><sub>l</sub>|<var>x</var>)</span></span>
      <span style="font-size:1.35em">)</span>`,
    symbols: [
      ['π_θ', '当前策略（正在训练的语言模型）'],
      ['π_ref', '参考策略（SFT 模型，冻结）'],
      ['y_w / y_l', '偏好数据中的 chosen / rejected 回答'],
      ['β', 'KL 约束强度：越大越贴合参考模型，越小越敢优化'],
    ],
    derivation: [
      '从带 KL 约束的 RLHF 目标出发：max_π E[r(x,y)] − β·KL(π ‖ π_ref)。',
      '该目标的最优解有闭式形式：π*(y|x) ∝ π_ref(y|x)·exp(r(x,y)/β)。',
      '反解得 r(x,y) = β·log(π*(y|x)/π_ref(y|x)) + β·log Z(x)，而配分项 Z(x) 与 y 无关，在 Bradley-Terry 成对比较中会抵消。',
      '把隐式奖励代回偏好似然，即得上式——不再需要单独训练奖励模型，也不需要在线采样。',
    ],
    analogy: '像老师批改作文：参考模型（π_ref）是学生的原有水平，DPO 不直接给分数，而是"相较原来的你，这篇进步了多少"——chosen 进步幅度大于 rejected 就增大它的概率。β 决定你多信任老师的评分标准：β 大则保守，只敢小幅调整。',
    code: `import torch.nn.functional as F

def dpo_loss(policy_chosen_logp, policy_rejected_logp,
             ref_chosen_logp, ref_rejected_logp, beta=0.1):
    """所有 logp 都是「整段回答的对数概率之和」。"""
    pi_logratios  = policy_chosen_logp - policy_rejected_logp
    ref_logratios = ref_chosen_logp  - ref_rejected_logp
    logits = beta * (pi_logratios - ref_logratios)
    losses = -F.logsigmoid(logits)
    # 隐式奖励，便于监控：β·(log π_θ − log π_ref)
    chosen_reward   = beta * (policy_chosen_logp   - ref_chosen_logp).detach()
    rejected_reward = beta * (policy_rejected_logp - ref_rejected_logp).detach()
    return losses.mean(), chosen_reward.mean(), rejected_reward.mean()`,
    pitfalls: [
      'logp 必须在 completion 的 token 上求平均或求和，且要屏蔽 prompt 部分。',
      'π_ref 必须真正冻结；忘记 eval() / no_grad 会导致参考模型漂移。',
      'β 与学习率耦合：β 很小的时候学习率要相应调低，否则训练不稳。',
    ],
    sources: [{ title: 'Direct Preference Optimization', url: 'https://arxiv.org/abs/2305.18290' }],
  },
  {
    id: 'f-grpo', name: 'GRPO 组相对优势', category: 'rl', glyph: 'G',
    tags: ['grpo', 'rlhf', 'advantage'],
    html: `<var>A</var><sub>i</sub> =
      <span class="frac"><span><var>r</var><sub>i</sub> − mean(<var>r</var><sub>1..G</sub>)</span><span>std(<var>r</var><sub>1..G</sub>)</span></span>
      &nbsp;&nbsp;·&nbsp;&nbsp;
      <var>J</var> = 𝔼<span style="font-size:1.35em">[</span>
      <span class="frac"><span>1</span><span><var>G</var></span></span> Σ<sub>i</sub> min<span style="font-size:1.35em">(</span>
      <var>ρ</var><sub>i</sub><var>A</var><sub>i</sub>, clip(<var>ρ</var><sub>i</sub>, 1−ε, 1+ε)<var>A</var><sub>i</sub>
      <span style="font-size:1.35em">)</span> <span style="font-size:1.35em">]</span>`,
    symbols: [
      ['G', '同一 prompt 采样出的回答条数（组大小）'],
      ['r_i', '第 i 条回答的奖励（规则校验或奖励模型）'],
      ['A_i', '组内归一化优势，替代 PPO 的 critic'],
      ['ρ_i', '重要性比 π_θ/π_old，用于离线多次更新'],
      ['ε', 'clip 范围，限制单步策略偏移'],
    ],
    derivation: [
      'PPO 需要 value network 估计 baseline，显存与训练成本翻倍。',
      'GRPO 改用「同一问题采样一组回答」的组内均值作为 baseline：A_i = (r_i − mean)/std。',
      'baseline 与 r_i 相关，因此方差不增；同时完全省掉 critic 网络。',
      '配合 clip 的重要性采样目标，可对同一批数据做多轮更新，提升样本效率。',
    ],
    analogy: '同一道题让 G 个同学各写一份，不给绝对分，只看"你比这组的平均水平高多少"。这样不需要一个单独的老师（critic）来预估绝对分数线，成本更低，也天然抑制了奖励量纲带来的抖动。std 归一化相当于把不同题目的难度差异抹平。',
    code: `import torch

def grpo_advantage(rewards: torch.Tensor) -> torch.Tensor:
    """rewards: (G,) 同一 prompt 下 G 条回答的奖励。
    返回组内标准化优势。G=1 时退化为 0，需在采样端保证 G>=4。"""
    mean = rewards.mean()
    std = rewards.std(unbiased=False) + 1e-4   # 防止除零
    return (rewards - mean) / std

def grpo_loss(logp, logp_old, advantages, clip_eps=0.2):
    ratio = torch.exp(logp - logp_old)          # ρ_i
    unclipped = ratio * advantages
    clipped = torch.clamp(ratio, 1 - clip_eps, 1 + clip_eps) * advantages
    return -torch.min(unclipped, clipped).mean()`,
    pitfalls: [
      '组内 std 为 0（所有回答奖励相同）时优势全为 0，该样本对梯度无贡献，需要过滤。',
      '重要性比要用 token 级 logp 之和，注意与 KL 惩罚项的配合。',
      'G 太小时 baseline 噪声大；工程上常见 G = 4~16。',
    ],
    sources: [{ title: 'DeepSeekMath (GRPO)', url: 'https://arxiv.org/abs/2402.03300' }],
  },
  {
    id: 'f-ddpm', name: 'DDPM 简化训练目标', category: 'generative', glyph: 'ε',
    tags: ['diffusion', 'ddpm', 'generative'],
    html: `<var>L</var><sub>simple</sub> = 𝔼<sub><var>t</var>,<var>x</var><sub>0</sub>,<var>ε</var></sub>
      <span style="font-size:1.4em">‖</span>
      <var>ε</var> − <var>ε</var><sub>θ</sub>
      <span style="font-size:1.4em">(</span>√<var>ᾱ</var><sub>t</sub> <var>x</var><sub>0</sub> + √(1−<var>ᾱ</var><sub>t</sub>) <var>ε</var>, <var>t</var><span style="font-size:1.4em">)</span>
      <span style="font-size:1.4em">‖</span><sup>2</sup>`,
    symbols: [
      ['x_0', '干净样本（图像 / 潜变量 / 视频帧）'],
      ['ε ~ N(0, I)', '当步注入的高斯噪声'],
      ['ᾱ_t = Π α_s', '累积保留系数，决定第 t 步保留多少信号'],
      ['ε_θ', '噪声预测网络（通常为 U-Net 或 DiT）'],
    ],
    derivation: [
      '前向过程 q(x_t|x_0) 可重参数化为一步采样：x_t = √ᾱ_t·x_0 + √(1−ᾱ_t)·ε。',
      '对变分下界逐项化简，去掉与 θ 无关的项，剩下的 KL 项在高斯假设下等价于预测噪声的 MSE。',
      '再丢掉随时间变化的时间权重，得到更简单、实际效果更好的 L_simple。',
      '采样时迭代 x_{t−1} = 1/√α_t (x_t − (1−α_t)/√(1−ᾱ_t)·ε_θ(x_t,t)) + σ_t z，即逐步去噪。',
    ],
    analogy: '像把一张照片反复复印到只剩噪点（前向），再训练一个"去噪师傅"看着模糊程度（时间步 t）把噪点擦掉（反向）。训练时不需要真的走完全部 1000 步——用闭式公式直接跳到任意模糊程度，让师傅每次只负责一步，任务简单且可并行。',
    code: `import torch

def q_sample(x0, t, alphas_bar):
    """闭式加噪：一步得到任意时刻的 x_t"""
    a = alphas_bar[t].view(-1, 1, 1, 1)
    eps = torch.randn_like(x0)
    return a.sqrt() * x0 + (1 - a).sqrt() * eps, eps

def train_step(model, x0, alphas_bar):
    t = torch.randint(0, len(alphas_bar), (x0.shape[0],), device=x0.device)
    x_t, eps = q_sample(x0, t, alphas_bar)
    eps_pred = model(x_t, t)                    # 预测注入的噪声
    return torch.nn.functional.mse_loss(eps_pred, eps)`,
    pitfalls: [
      'ᾱ_t 的数值要预先算好并放到正确 device/dtype，fp16 下容易精度不足。',
      '采样步数与训练步数可以不一致（DDIM / 蒸馏加速就是利用这点）。',
      '和 score matching 的联系常被追问：ε_θ ≈ −√(1−ᾱ_t)·∇log p(x_t)。',
    ],
    sources: [{ title: 'Denoising Diffusion Probabilistic Models', url: 'https://arxiv.org/abs/2006.11239' }],
  },
  {
    id: 'f-rope', name: 'RoPE 旋转位置编码', category: 'foundation', glyph: 'R',
    tags: ['rope', 'position', 'llm'],
    html: `<var>f</var>(<var>x</var>, <var>m</var>) =
      <var>R</var><sub>Θ,<var>m</var></sub><var>x</var> &nbsp;&nbsp;⇒&nbsp;&nbsp;
      ⟨<var>f</var>(<var>q</var>,<var>m</var>), <var>f</var>(<var>k</var>,<var>n</var>)⟩ =
      <var>g</var>(<var>q</var>, <var>k</var>, <var>m</var>−<var>n</var>)`,
    symbols: [
      ['R_{Θ,m}', '按位置 m 构造的分块旋转矩阵'],
      ['Θ = {θ_i = 10000^{-2i/d}}', '每个维度对的旋转基频'],
      ['m − n', '注意力只依赖相对距离，内积形式保持不变'],
    ],
    derivation: [
      '把 d 维向量两两分组，每组视为复平面上的一个数。',
      '位置 m 的编码就是把每个复数乘以 e^{i·m·θ_i}，即按不同频率旋转。',
      '两个向量分别旋转后做内积，旋转角相减，结果只依赖 m−n —— 天然编码相对位置。',
      '外推：NTK-aware / YaRN 通过缩放基频 θ 让模型在训练长度之外依然可用。',
    ],
    analogy: '像钟表：每个维度对是一只走速不同的指针，位置就是各指针的角度组合。比较两个位置时，只有"角度差"有意义，因此绝对位置被自动转成相对距离。调整基频相当于换一套齿轮比，让同一只表还能读出更长的时段（长度外推）。',
    code: `import torch

def rope(x, position, base=10000.0):
    """x: (B, T, H, D)，D 为偶数。原地实现省略，便于阅读。"""
    D = x.shape[-1]
    i = torch.arange(0, D, 2, device=x.device, dtype=torch.float32)
    theta = base ** (-i / D)                      # (D/2,)
    ang = position.float().unsqueeze(-1) * theta  # (T, D/2)
    cos, sin = ang.cos(), ang.sin()
    x1, x2 = x[..., 0::2], x[..., 1::2]           # 复数实部/虚部
    return torch.stack([x1 * cos - x2 * sin,
                        x1 * sin + x2 * cos], dim=-1).flatten(-2)`,
    pitfalls: [
      '缓存 KV 时 RoPE 必须按绝对位置施加，不能用相对偏移直接套。',
      'd 必须为偶数；奇数维要补齐或换用 ALiBi。',
      'sin/cos 缓存的 dtype 与精度会影响长上下文表现。',
    ],
    sources: [{ title: 'RoFormer: Enhanced Transformer with Rotary Position Embedding', url: 'https://arxiv.org/abs/2104.09864' }],
  },
  {
    id: 'f-clip', name: 'CLIP 对比损失 (InfoNCE)', category: 'multimodal', glyph: 'C',
    tags: ['clip', 'contrastive', 'multimodal'],
    html: `<var>L</var> = −
      <span class="frac"><span>1</span><span>2<var>N</var></span></span>
      <span style="font-size:1.4em">(</span>
      Σ<sub>i</sub> log
      <span class="frac"><span>exp(<var>s</var><sub>ii</sub>/<var>τ</var>)</span><span>Σ<sub>j</sub> exp(<var>s</var><sub>ij</sub>/<var>τ</var>)</span></span>
      +
      Σ<sub>i</sub> log
      <span class="frac"><span>exp(<var>s</var><sub>ii</sub>/<var>τ</var>)</span><span>Σ<sub>j</sub> exp(<var>s</var><sub>ji</sub>/<var>τ</var>)</span></span>
      <span style="font-size:1.4em">)</span>`,
    symbols: [
      ['s_ij = ⟨I_i, T_j⟩', '第 i 张图与第 j 条文本的归一化相似度'],
      ['τ', '可学习温度，控制分布的锐度'],
      ['N', 'batch 内的图-文对数量，负样本即其余 2N−1 条'],
    ],
    derivation: [
      '对一个 batch 内的 N 对图-文，构造 N×N 的相似度矩阵，对角线为正样本。',
      '按行做 softmax 得到「图 → 文」的检索分布，按列做 softmax 得到「文 → 图」的分布。',
      '两个方向的交叉熵之和即为对称 InfoNCE 损失。',
      '温度 τ 越小，模型越关注最难的负样本，但训练越不稳定；CLIP 把 τ 设为可学习参数。',
    ],
    analogy: '像把 N 个人和 N 把钥匙混在一起，让模型学会"只把自己的钥匙配给自己的锁"。batch 里其他 N−1 把锁都是干扰项（负样本），batch 越大干扰越多，学到的表示越细致——这也解释了 CLIP 依赖超大 batch 的原因。',
    code: `import torch, torch.nn.functional as F

def clip_loss(img_emb, txt_emb, logit_scale):
    """img_emb / txt_emb: (N, D) 已经各自做过线性投影，未归一化。"""
    img = F.normalize(img_emb, dim=-1)
    txt = F.normalize(txt_emb, dim=-1)
    logits = logit_scale.exp() * img @ txt.t()          # (N, N)
    labels = torch.arange(len(img), device=img.device)  # 对角线为正样本
    l_i = F.cross_entropy(logits, labels)                # 图→文
    l_t = F.cross_entropy(logits.t(), labels)            # 文→图
    return (l_i + l_t) / 2`,
    pitfalls: [
      '务必先 L2 归一化，否则相似度尺度失控。',
      'logit_scale 需要 clamp 上限，否则温度塌缩导致 NaN。',
      '跨卡训练时负样本要 all-gather，否则 batch 语义被破坏（常见追问点）。',
    ],
    sources: [{ title: 'CLIP', url: 'https://arxiv.org/abs/2103.00020' }],
  },
];

function formulaList() {
  const base = state.formulas.length ? state.formulas : FORMULA_SEED;
  return base.map((f, i) => normalizeFormula(f, i));
}

function normalizeFormula(f, i) {
  return {
    id: String(f.id || `f-auto-${i}`),
    name: String(f.name || f.title || `公式 ${i + 1}`),
    category: CAT_BY_ID[f.category] ? f.category : mapCatGuess(f.category || f.tags || []),
    glyph: f.glyph || (f.name || 'ƒ').slice(0, 1).toUpperCase(),
    tags: f.tags || [],
    latex: f.latex || '',
    formula: f.formula || '',
    html: f.html || '',
    symbols: (f.symbols || []).map((s) => (Array.isArray(s) ? s : [s.sym || s.symbol || '', s.meaning || s.desc || ''])),
    derivation: f.derivation || f.steps || [],
    analogy: f.analogy || f.intuition || '',
    code: f.code || f.referenceCode || '',
    pitfalls: f.pitfalls || [],
    sources: f.sources || [],
    usedIn: f.usedIn || [],
  };
}

function mapCatGuess(x) {
  const s = Array.isArray(x) ? x.join(' ') : String(x || '');
  if (/diffus|ddpm|flow|gener/.test(s)) return 'generative';
  if (/dpo|sft|rlhf|align|post/.test(s)) return 'posttraining';
  if (/grpo|ppo|rl|advantage/.test(s)) return 'rl';
  if (/clip|multi|vlm|vision/.test(s)) return 'multimodal';
  if (/rope|attention|transformer|found/.test(s)) return 'foundation';
  if (/world|vla|embodied/.test(s)) return 'worldmodel';
  return 'paper';
}

export const FormulasView = {
  title: '公式剖析',
  render(params) {
    const list = formulaList();
    const cats = new Map();
    for (const f of list) cats.set(f.category, (cats.get(f.category) || 0) + 1);
    if (params.id) {
      const f = list.find((x) => x.id === params.id);
      if (f) return formulaDetailHtml(f);
    }
    return `
    <div class="section-head">
      <div><h2 class="section-title">公式剖析</h2>
      <p class="section-desc">每个公式都拆成「符号表 → 推导步骤 → 生活类比 → 可运行代码 → 易错点」五层。
      目标不是记住符号，而是能在面试里从第一性原理讲清楚它为什么长这样。</p></div>
    </div>
    <div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-4)">
      ${CATEGORIES.filter((c) => cats.get(c.id)).map((c) => `
        <button class="chip${state.filters.cat.has(c.id) ? ' is-on' : ''}" data-cat="${c.id}" data-act="toggle-cat">
          <span class="chip-dot"></span>${esc(c.zh)} <span class="tnum" style="opacity:.7">${cats.get(c.id)}</span></button>`).join('')}
    </div>
    <div class="col" style="gap:var(--sp-4)">
      ${list.filter((f) => !state.filters.cat.size || state.filters.cat.has(f.category)).map((f, i) => `
        <div data-cat="${f.category}" style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 40}ms">
          ${formulaDetailHtml(f, i > 1)}
        </div>`).join('')}
    </div>`;
  },
  after() {},
};

function formulaDetailHtml(f, collapsed = false) {
  const bodyId = `fx-${f.id}`;
  // One rendering engine for every formula in the app: prefer real LaTeX
  // (compiled by our own tex()), fall back to hand-written HTML, then to code.
  const mathHtml = f.latex ? tex(f.latex) : (f.html || (f.code ? '' : esc(f.formula || '')));
  const display = mathHtml || f.html || '';
  return `
  <article class="formula" data-cat="${f.category}">
    <div class="formula-head" data-act="toggle-expand" data-target="${bodyId}" role="button" tabindex="0"
      aria-expanded="${!collapsed}" aria-controls="${bodyId}">
      <span class="formula-glyph">${esc(f.glyph)}</span>
      <div class="grow">
        <div class="formula-title">${esc(f.name)}</div>
        <div class="formula-sub">${esc((CAT_BY_ID[f.category] || {}).zh || '')}${f.tags.length ? ' · ' + esc(f.tags.slice(0, 4).join(' / ')) : ''}</div>
      </div>
      <span class="badge badge-mute">${f.derivation.length} 步推导</span>
      ${icon('i-chevrondown', collapsed ? '' : 'is-open')}
    </div>
    <div class="formula-body" id="${bodyId}"${collapsed ? ' hidden' : ''}>
      ${display ? `<div class="math" data-tex="${attr(f.latex || '')}">${display}</div>` : ''}
      ${f.latex ? `<div class="math-source"><span class="eyebrow">LaTeX 源码</span>
        <code>${esc(f.latex)}</code>
        <button class="icon-btn" data-act="copy" data-copy="${attr(f.latex)}" data-copy-msg="LaTeX 已复制" aria-label="复制 LaTeX">${icon('i-copy')}</button>
      </div>` : ''}

      ${f.symbols.length ? `<dl class="sym-table">${f.symbols.map(([s, m]) => `<dt>${esc(s)}</dt><dd>${esc(m)}</dd>`).join('')}</dl>` : ''}

      ${f.derivation.length ? `<div>
        <div class="eyebrow" style="margin-bottom:var(--sp-2)">推导链条</div>
        <div class="derive">${f.derivation.map((d, i) => `<div class="derive-step"><b>${i + 1}</b><span>${esc(d)}</span></div>`).join('')}</div>
      </div>` : ''}

      ${f.analogy ? `<div class="analogy">${icon('i-bulb')}<p><b>生活类比 · </b>${esc(f.analogy)}</p></div>` : ''}

      ${f.code ? `<div class="code-wrap">
        <div class="code-head"><span>PyTorch</span>
          <button class="icon-btn copy" data-act="copy" data-copy="${attr(f.code)}" data-copy-msg="代码已复制" aria-label="复制代码" style="width:22px;height:22px">${icon('i-copy')}</button>
        </div>
        <pre class="code">${highlight(f.code, 'python')}</pre>
      </div>` : ''}

      ${f.pitfalls.length ? `<div>
        <div class="eyebrow" style="margin-bottom:var(--sp-2)">面试易错点</div>
        <ul class="kcard-points">${f.pitfalls.map((p) => `<li><span>${esc(p)}</span></li>`).join('')}</ul>
      </div>` : ''}

      ${f.sources.length ? `<div class="row" style="flex-wrap:wrap;gap:6px">
        ${f.sources.map((s) => `<a class="btn btn-sm btn-ghost" href="${attr(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">
          ${icon('i-external')} ${esc(s.title || hostOf(s.url))}</a>`).join('')}
      </div>` : ''}
    </div>
  </article>`;
}

/* ============================== PROBLEMS =============================== */

/* ======================= INTERVIEW PANEL ================================ */
/**
 * Renders web/data/interview.json (built by scripts/build_interview_index.py).
 *
 * WHY this is its own panel: interview write-ups are the most PERISHABLE content in
 * the workbench - a 2024 面经 is nearly worthless for a 2026 application - and the raw
 * `summary` of a forum post is mostly venting plus a referral code. The reader asked
 * for deeper, better-organised interview material, so this leads with what is still
 * fresh and answers "which company, which round, what did they ask".
 *
 * The extraction is deterministic rules, not an LLM, so it runs every day and every
 * field can be checked against the source title. Degrades to nothing when absent.
 */
function interviewPanel() {
  const d = state.interview;
  if (!d || !d.count) return '';
  const items = Array.isArray(d.items) ? d.items : [];
  const fresh = items.slice(0, 6);
  const chip = (name, n, cat) => `<span class="chip" data-cat="${attr(cat || 'coding')}"
      style="cursor:default">${esc(name)} <span class="tnum" style="opacity:.65">${n}</span></span>`;

  return `
  <div class="panel" style="margin-bottom:var(--sp-5)">
    <div class="panel-head"><div class="panel-title">${icon('i-briefcase')} 面经速览（时效优先）</div>
      <span class="result-line" style="margin-left:auto">${d.count} 条 · 含手撕题 ${d.withCoding} 条</span></div>
    <div class="panel-body">
      <div class="prose" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
        <p>面经是这套工作台里<strong>时效性最强</strong>的内容，所以按发布时间倒序，并抽取了公司、轮次、结果与考察主题。
        抽取规则是确定性的（<code>scripts/build_interview_index.py</code>，不用模型），可以逐条对照原帖核对。</p>
      </div>

      <div class="grid grid-2" style="gap:var(--sp-4)">
        <div>
          <div class="eyebrow">公司分布（你正在准备哪几家）</div>
          <div class="row" style="flex-wrap:wrap;gap:6px">
            ${(d.companies || []).slice(0, 10).map((c) => chip(c.name, c.count, 'job')).join('') || '<span class="text-3">—</span>'}
          </div>
          <div class="eyebrow" style="margin-top:var(--sp-3)">轮次</div>
          <div class="row" style="flex-wrap:wrap;gap:6px">
            ${(d.rounds || []).map((c) => chip(c.name, c.count, 'coding')).join('') || '<span class="text-3">—</span>'}
          </div>
          <div class="eyebrow" style="margin-top:var(--sp-3)">结果</div>
          <div class="row" style="flex-wrap:wrap;gap:6px">
            ${(d.outcomes || []).map((c) => chip(c.name, c.count, 'job')).join('') || '<span class="text-3">—</span>'}
          </div>
        </div>
        <div>
          <div class="eyebrow">考察主题（决定你该练什么）</div>
          <div class="row" style="flex-wrap:wrap;gap:6px">
            ${(d.topics || []).map((c) => chip(c.name, c.count, 'posttraining')).join('') || '<span class="text-3">—</span>'}
          </div>
        </div>
      </div>

      <div class="eyebrow" style="margin-top:var(--sp-4)">最近的面经</div>
      <ul class="kcard-points" data-cat="coding">
        ${fresh.map((r) => {
          // Skip a chip whose text is already visible in the title: many 面经 titles
          // contain the round ("面经60：江波龙 | 嵌入式软件 | 二面") and the company, so
          // printing them again read as "…| 二面 · 二面 / 通过 · …".
          const inTitle = (s) => s && String(r.title).includes(s);
          const bits = [r.company, r.round, r.outcome].filter((x) => x && !inTitle(x));
          return `<li><span>${r.url
            ? `<a href="${attr(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>`
            : esc(r.title)}
            <span class="text-3" style="font-size:var(--fs-3xs)">
              ${bits.length ? ` · ${esc(bits.join(' / '))}` : ''}
              ${r.publishedAt ? ` · ${esc(String(r.publishedAt).slice(0, 10))}` : ''}
              ${r.hasCoding ? ' · <b style="color:var(--accent)">含手撕题</b>' : ''}
            </span></span></li>`;
        }).join('') || '<li><span class="text-3">暂无</span></li>'}
      </ul>
      <div class="text-3" style="font-size:var(--fs-3xs)">
        生成时间 ${esc(String(d.generatedAt || '—'))} · 规则抽取，未命中公司/轮次的条目按标题原样列出
      </div>
    </div>
  </div>`;
}

export const ProblemsView = {
  title: '题库定位',
  render(params) {
    const all = state.problems;
    if (!all.length) {
      return `<div class="section-head"><div><h2 class="section-title">题库定位</h2>
        <p class="section-desc">手撕题与笔试场景题，按主题与出现频率定位薄弱环节。</p></div></div>` +
        emptyState('还没有题库数据', '题库由 scripts/build_problem_bank.py 生成：合并 CodeTop 真实频度、算法知识库题解与人工题库，并挂载深读解析。', 'i-code');
    }
    if (params.id) {
      const p = all.find((x) => x.id === params.id || x.rawId === params.id);
      if (p) return problemDetailHtml(p);
    }

    // 赛道：model（模型与训练手撕，读者点名的最高优先级视图）/ algorithm /
    // exam。旧链接的 ?kind=exam 兼容映射到 track=exam。
    const track = params.track || (params.kind === 'exam' ? 'exam' : 'model');
    // 编号空间过滤：LeetCode 与卡码网是两个独立的编号空间（见 build_problem_bank.py
    // 的 KAMACODER_RE 段）。放在 URL 里而不是 state.filters，是为了让「分享一条
    // 筛选后的链接」也能带上它，而且与已有的 track= 过滤保持一致的做法。
    const ns = params.ns || 'all';
    const byTrack = all.filter((p) => (p.track || 'algorithm') === track);
    const list = ns === 'all' ? byTrack : byTrack.filter((p) => (p.namespace || 'kb') === ns);
    const nsCounts = { all: byTrack.length, leetcode: 0, kamacoder: 0, kb: 0 };
    for (const p of byTrack) nsCounts[p.namespace || 'kb'] = (nsCounts[p.namespace || 'kb'] || 0) + 1;
    const qs = (over) => {
      const q = { track, ns, ...over };
      return '#/problems?' + Object.entries(q)
        .filter(([, v]) => v && v !== 'all')
        .map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
    };
    const topicCounts = new Map();
    for (const p of list) for (const t of p.topics) topicCounts.set(t, (topicCounts.get(t) || 0) + 1);
    const filtered = state.filters.tag.size ? list.filter((p) => p.topics.some((t) => state.filters.tag.has(t))) : list;

    // Coverage: mastered (status done) per topic
    const coverage = new Map();
    for (const t of topicCounts.keys()) {
      const ps = list.filter((p) => p.topics.includes(t));
      const done = ps.filter((p) => statusOf(p.id) === 'done').length;
      coverage.set(t, { total: ps.length, done });
    }

    const meta = state.problemBankMeta;
    const solved = list.filter((p) => p.analysisStatus === 'deep').length;
    const TRACK_DEFS = [
      { id: 'model', label: '模型与训练', tip: 'DPO/GRPO/MHSA/Transformer/RoPE 等与模型、训练策略直接相关的手撕题' },
      { id: 'algorithm', label: '算法与数据结构', tip: 'LeetCode / 卡码网风格的手撕算法题' },
      { id: 'exam', label: '笔试场景', tip: '公司笔试真题风格的应用场景题' },
    ];

    return `
    <div class="section-head">
      <div><h2 class="section-title">题库分类定位</h2>
      <p class="section-desc">每题都带「被考频度、公司分布、深度解析（代码 / 图解 / 复杂度 / 易错点）」。
      标记为「已掌握」的题目会自动从待办中淡出。</p></div>
      <div class="section-actions">
        <div class="segmented" role="group" aria-label="赛道">
          ${TRACK_DEFS.map((t) => `<button data-route="${qs({ track: t.id })}" class="${track === t.id ? 'is-on' : ''}" data-tip="${attr(t.tip)}">${t.label} ${all.filter((p) => (p.track || 'algorithm') === t.id).length}</button>`).join('')}
        </div>
        ${track !== 'exam' ? `<div class="segmented" role="group" aria-label="题号来源" style="margin-left:var(--sp-3)">
          <button data-route="${qs({ ns: 'all' })}" class="${ns === 'all' ? 'is-on' : ''}">全部 ${nsCounts.all}</button>
          <button data-route="${qs({ ns: 'leetcode' })}" class="${ns === 'leetcode' ? 'is-on' : ''}">LeetCode ${nsCounts.leetcode}</button>
          <button data-route="${qs({ ns: 'kamacoder' })}" class="${ns === 'kamacoder' ? 'is-on' : ''}" data-tip="代码随想录配套的笔试练习平台，用独立的题号">卡码网 ${nsCounts.kamacoder}</button>
        </div>` : ''}
      </div>
    </div>

    <div class="panel" style="margin-bottom:var(--sp-5)">
      <div class="panel-head"><div class="panel-title">${icon('i-target')} 题库概览</div>
        <span class="result-line" style="margin-left:auto">已完整解析 <b>${solved}</b> / ${list.length} 题</span></div>
      <div class="panel-body">
        <div class="prose" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
          <p>题库按**赛道**三分：「模型与训练」（DPO/GRPO/MHSA/Transformer/RoPE 等与模型和训练策略直接相关的手撕题，
          默认视图）、「算法与数据结构」（LeetCode/卡码网风格）、「笔试场景」。两类手撕考的东西不同：算法题考编码与复杂度，
          模型手撕考结构理解 + 向量化实现 + **变体横向对比**——模型赛道的深度解析都带「变体实现」和「对比表」两个板块。</p>
          <p>每道题是一个**实体**：题号来自题干/链接，「被考频度 / 公司 / 难度」来自 CodeTop 的真实记录，
          深度解析由每日深读产出（可运行代码 + 图解 + 复杂度 + 易错点）。排序按「解析完整度 → 被考频度」，
          刻意不按发布时间 —— 高频老题与新题对备考等价。题号分**两个编号空间**：<span class="kcard-cat">#102</span> 是
          LeetCode 第 102 题，<span class="kcard-cat">卡码网 102</span> 是代码随想录配套练习平台的第 102 题。</p>
        </div>
        ${meta && meta.companies && meta.companies.length ? `<div class="eyebrow">高频公司（按出现题数）</div>
        <div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-3)">
          ${meta.companies.slice(0, 12).map((c) => `<span class="chip" style="cursor:default">${esc(c.name)} <span class="tnum" style="opacity:.65">${c.count}</span></span>`).join('')}
        </div>` : ''}
        <div class="eyebrow" style="margin-bottom:6px">解析完整度</div>
        <div class="row" style="flex-wrap:wrap;gap:6px">
          <span class="chip" style="cursor:default">可照着刷 <span class="tnum" style="opacity:.65">${list.filter((p) => p.analysisStatus === 'deep').length}</span></span>
          <span class="chip" style="cursor:default">部分解析 <span class="tnum" style="opacity:.65">${list.filter((p) => p.analysisStatus === 'partial').length}</span></span>
          <span class="chip" style="cursor:default">待深读 <span class="tnum" style="opacity:.65">${list.filter((p) => p.analysisStatus === 'none').length}</span></span>
        </div>
      </div>
    </div>

    ${interviewPanel()}

    <div class="panel" style="margin-bottom:var(--sp-5)">
      <div class="panel-head"><div class="panel-title">${icon('i-target')} 主题热力与掌握度</div>
        <span class="result-line" style="margin-left:auto">点击主题即可筛选</span></div>
      <div class="panel-body">
        <div class="row" style="flex-wrap:wrap;gap:6px">
          ${Array.from(topicCounts.entries()).sort((a, b) => b[1] - a[1]).map(([t, n]) => {
            const cov = coverage.get(t) || { done: 0, total: n };
            const pct = cov.total ? (cov.done / cov.total) * 100 : 0;
            const on = state.filters.tag.has(t);
            return `<button class="chip${on ? ' is-on' : ''}" data-act="toggle-tag" data-tag="${attr(t)}" data-tip="掌握 ${cov.done}/${cov.total}">
              ${esc(t)} <span class="tnum" style="opacity:.65">${n}</span>
              <span style="width:22px">${progressBar(pct)}</span></button>`;
          }).join('')}
        </div>
      </div>
    </div>

    <div class="row" style="justify-content:space-between;margin-bottom:var(--sp-3)">
      <div class="result-line">共 <b>${filtered.length}</b> 题${state.filters.tag.size ? ` · 已按 ${state.filters.tag.size} 个主题筛选` : ''}</div>
      <div class="row">
        <select class="select select-sm" id="p-sort" aria-label="排序">
          <option value="freq">高频优先</option><option value="diff">难度递增</option><option value="topic">按主题</option>
        </select>
      </div>
    </div>

    <div class="grid grid-auto">
      ${filtered.map((p, i) => problemCard(p, i)).join('')}
    </div>`;
  },
  after() {
    const sel = $('#p-sort');
    if (sel) sel.addEventListener('change', () => {
      const grid = $('.grid-auto');
      if (!grid) return;
      const cards = Array.from(grid.children);
      const key = (c) => ({ freq: Number(c.dataset.freq), diff: DIFF_ORDER.indexOf(c.dataset.diff), topic: c.dataset.topic }[sel.value]);
      cards.sort((a, b) => (sel.value === 'freq' ? key(b) - key(a) : String(key(a)).localeCompare(String(key(b)))));
      cards.forEach((c) => grid.append(c));
    });
  },
};

/* 解析完整度的可视标记。三档刻意用不同措辞而不是「好/中/差」：
 * 读者需要知道的是「这题现在能不能直接照着刷」。 */
const STATUS_BADGE = {
  deep: ['badge-ok', '可照着刷'],
  partial: ['badge-warn', '部分解析'],
  none: ['badge-mute', '待深读'],
};

/**
 * 题号徽标。LeetCode 题号写 `#102`，卡码网题号写 `卡码网 102`。
 *
 * 为什么必须分开：卡码网（代码随想录配套的笔试练习平台）用的是独立编号，
 * 它的第 102 题是「沉没孤岛」，LeetCode 第 102 题是「二叉树的层序遍历」。
 * 两者曾经共用 `lc-102` 这个键，于是卡码网题目顶掉了 LeetCode 题的标题 ——
 * 这正是「#102 沉没孤岛」出现在二叉树层序遍历位置上的原因。现在键已经分开
 * （`lc-<n>` / `km-<n>`），徽标也必须分开显示，否则读者会以为这是同一道题。
 */
function numBadge(p) {
  if (p.namespace === 'kamacoder' && p.kbNumber) {
    return `<span class="kcard-cat" data-tip="卡码网题号（与 LeetCode 题号是两个独立编号空间）">卡码网 ${p.kbNumber}</span>`;
  }
  if (p.number) {
    return `<span class="kcard-cat" data-tip="LeetCode 题号">#${p.number}</span>`;
  }
  return '';
}

function problemCard(p, i = 0) {
  const st = statusOf(p.id);
  const [badgeCls, badgeText] = STATUS_BADGE[p.analysisStatus] || STATUS_BADGE.none;
  return `
  <article class="card card-pad card-hover" data-cat="coding" style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 18}ms"
    data-freq="${p.frequencyRaw}" data-diff="${attr(p.difficulty)}" data-topic="${attr(p.topics[0] || '')}">
    <div class="row" style="align-items:flex-start;gap:var(--sp-2)">
      <span class="kcard-cat">${esc(p.type)}</span>
      ${numBadge(p)}
      <span class="badge ${p.difficulty === 'hard' ? 'badge-err' : p.difficulty === 'medium' ? 'badge-warn' : 'badge-ok'}">${esc(DIFF_ZH[p.difficulty] || p.difficulty)}</span>
      ${p.track === 'model' ? '<span class="badge badge-info" data-tip="模型与训练手撕题，含变体实现与横向对比">模型手撕</span>' : ''}
      <span class="badge ${badgeCls}" data-tip="解析完整度">${badgeText}</span>
      <div class="kcard-actions" style="margin-left:auto">
        <span class="relevance" data-tip="大厂被考频度 ${p.frequencyRaw ? p.frequencyRaw + ' 次' : '未知'}">${'★'.repeat(p.frequency)}${'☆'.repeat(5 - p.frequency)}</span>
        <button class="icon-btn${st === 'done' ? ' is-done' : ''}" data-act="status" data-id="${attr(p.id)}" data-status="done"
          aria-label="标记已掌握" data-tip="标记已掌握">${icon('i-check')}</button>
      </div>
    </div>
    <h3 class="kcard-title" style="margin-top:var(--sp-3)">${esc(p.title)}</h3>
    ${p.statement && p.statement !== p.title ? `<p class="kcard-summary clamp-3">${esc(p.statement)}</p>` : ''}
    ${p.analysis && p.analysis.tldr ? `<p class="kcard-summary clamp-2" style="color:var(--fg-2)">${esc(p.analysis.tldr)}</p>` : ''}
    ${p.companies.length ? `<div class="row" style="flex-wrap:wrap;gap:4px">
      ${p.companies.slice(0, 4).map((c) => `<span class="tag" data-tip="被考 ${c.count} 次">${esc(c.name)} · ${c.count}</span>`).join('')}</div>` : ''}
    <div class="row" style="flex-wrap:wrap;gap:4px;margin-top:auto">
      ${p.topics.slice(0, 5).map((t) => `<span class="tag">${esc(t)}</span>`).join('')}
    </div>
    <div class="kcard-foot">
      <button class="btn btn-sm btn-ghost" data-route="#/problems?id=${encodeURIComponent(p.id)}">${icon('i-play')} 详解与代码</button>
      ${p.sources && p.sources[0] ? `<a class="kcard-src" href="${attr(safeUrl(p.sources[0].url))}" target="_blank" rel="noopener noreferrer" style="margin-left:auto">
        ${icon('i-external', '', 11)} 题源</a>` : ''}
    </div>
  </article>`;
}

/* ---------------------------------------------------------------------------
 * teachingHtml / conceptsHtml
 *
 * The Layer-2 (agent) enrichment carries two narrative payloads that are useful
 * everywhere an item can be read — the item drawer AND the 题库解析页. They used
 * to be rendered inline inside openItem(), which meant the problem page had no
 * way to show them. Extracting them into pure string builders lets both call
 * sites share one implementation, so a fix here lands in both places.
 *
 * Both return '' when there is nothing to show, so callers can interpolate
 * unconditionally. `variant` picks the outer chrome: 'prose' (a section heading,
 * for the item drawer which is a column of prose) or 'panel' (a bordered card,
 * for the 题库解析页 which is a grid of panels).
 * ------------------------------------------------------------------------- */

function teachingHtml(t, variant) {
  if (!t || typeof t !== 'object') return '';
  const body = teachingBody(t);
  if (!body) return '';
  return wrapSection('讲解 · 教学', 'i-bulb', body, variant);
}

function conceptsHtml(concepts, variant) {
  const cards = conceptsBody(concepts);
  if (!cards) return '';
  return wrapSection('概念易读化解析', 'i-book', cards, variant);
}

/** Section chrome: prose heading (drawer) vs panel card (problem page). */
function wrapSection(title, ic, body, variant) {
  if (variant === 'panel') {
    return '<div class="panel"><div class="panel-head"><div class="panel-title">'
      + icon(ic) + ' ' + title + '</div></div><div class="panel-body">' + body + '</div></div>';
  }
  return '<div class="prose"><h2>' + title + '</h2>' + body + '</div>';
}

function teachingBody(t) {
  const blocks = [];
  const prog = Array.isArray(t.progressive) ? t.progressive.filter((p) => p && p.text) : [];
  if (prog.length) {
    blocks.push('<div class="eyebrow">由浅入深</div><ol class="teach-prog">'
      + prog.map((p) => '<li><span class="teach-level">' + esc(p.level || '') + '</span>'
        + '<span>' + esc(p.text) + '</span></li>').join('') + '</ol>');
  }
  const soc = Array.isArray(t.socratic) ? t.socratic.filter((s) => s && s.q) : [];
  if (soc.length) {
    blocks.push('<div class="eyebrow" style="margin-top:var(--sp-3)">追问式理解</div>'
      + soc.map((s) => '<div class="teach-qa"><p class="teach-q">' + esc(s.q) + '</p>'
        + (s.a ? '<p class="teach-a">' + esc(s.a) + '</p>' : '') + '</div>').join(''));
  }
  const row = (label, text) => (text
    ? '<p class="teach-row"><b>' + label + '</b>' + esc(text) + '</p>' : '');
  const core = row('机制 · ', t.mechanism) + row('适用边界 · ', t.boundary)
    + row('类比的失效点 · ', t.analogyBoundary) + row('我的分析 · ', t.ownAnalysis)
    + row('面试怎么答 · ', t.interviewAnswer);
  if (core) blocks.push('<div style="margin-top:var(--sp-3)">' + core + '</div>');
  if (Array.isArray(t.misconceptions) && t.misconceptions.length) {
    blocks.push('<div class="eyebrow" style="margin-top:var(--sp-3)">常见误解</div>'
      + '<ul class="teach-mis">' + t.misconceptions.map((m) => '<li>' + esc(m) + '</li>').join('') + '</ul>');
  }
  if (Array.isArray(t.officialNotes) && t.officialNotes.length) {
    blocks.push('<div class="eyebrow" style="margin-top:var(--sp-3)">官方 / 权威口径</div>'
      + t.officialNotes.map((o) => '<div class="teach-official">' + esc(o.position || '')
        + (o.source ? ' <span class="text-3">— ' + esc(o.source) + '</span>' : '') + '</div>').join(''));
  }
  const sp = t.studyPath || {};
  const pre = Array.isArray(sp.prerequisites) ? sp.prerequisites : [];
  const nxt = Array.isArray(sp.nextSteps) ? sp.nextSteps : [];
  if (pre.length || nxt.length) {
    blocks.push('<div class="teach-path">'
      + (pre.length ? '<div><span class="text-3">读之前先会：</span>' + esc(pre.join('、')) + '</div>' : '')
      + (nxt.length ? '<div style="margin-top:4px"><span class="text-3">读完该练：</span>' + esc(nxt.join('、')) + '</div>' : '')
      + '</div>');
  }
  if (!blocks.length) return '';
  return '<div class="teach">' + blocks.join('') + '</div>';
}

function conceptsBody(concepts) {
  const list = Array.isArray(concepts) ? concepts.filter((c) => c && (c.name || c.readable)) : [];
  if (!list.length) return '';
  const cards = list.map((c) => {
    const rows = [];
    if (c.readable) rows.push('<p style="font-size:var(--fs-xs);color:var(--fg-1);margin-bottom:var(--sp-2)">' + esc(c.readable) + '</p>');
    if (c.analogy) {
      rows.push('<div class="analogy" style="margin-bottom:var(--sp-2)">' + icon('i-bulb')
        + '<p><b>生活类比 · </b>' + esc(c.analogy)
        + (c.analogyBreaksDown ? '<br><b>类比的失效边界 · </b>' + esc(c.analogyBreaksDown) : '')
        + '</p></div>');
    }
    if (c.mechanism) rows.push('<p style="font-size:var(--fs-2xs);color:var(--fg-2);margin-bottom:var(--sp-2)"><b style="color:var(--fg-1)">机制 · </b>' + esc(c.mechanism) + '</p>');
    if (c.visual) {
      rows.push('<div style="padding:var(--sp-2) var(--sp-3);border-radius:var(--r-sm);background:var(--bg-3);font-size:var(--fs-2xs);color:var(--fg-1);margin-bottom:var(--sp-2)">'
        + icon('i-chart', '', 12) + ' <b>可视化方案 · </b>' + esc(c.visual) + '</div>');
    }
    if (c.prerequisites) rows.push('<div class="text-3" style="font-size:var(--fs-3xs);margin-bottom:4px">前置知识：' + esc(Array.isArray(c.prerequisites) ? c.prerequisites.join('、') : c.prerequisites) + '</div>');
    if (Array.isArray(c.selfTest) && c.selfTest.length) {
      rows.push('<div class="eyebrow" style="margin-top:var(--sp-2)">自测题</div><ol style="list-style:decimal;padding-left:var(--sp-5);font-size:var(--fs-2xs);color:var(--fg-1)">'
        + c.selfTest.map((q) => '<li style="margin-bottom:3px">' + esc(q) + '</li>').join('') + '</ol>');
    }
    return '<div class="formula" style="margin-bottom:var(--sp-3)"><div class="formula-head" style="cursor:default">'
      + '<span class="formula-glyph">' + esc((c.name || '?').slice(0, 1)) + '</span>'
      + '<div class="grow"><div class="formula-title">' + esc(c.name || '概念') + '</div></div></div>'
      + '<div class="formula-body">' + rows.join('') + '</div></div>';
  }).join('');
  return cards;
}

function problemDetailHtml(p) {
  const [badgeCls, badgeText] = STATUS_BADGE[p.analysisStatus] || STATUS_BADGE.none;
  const a = p.analysis || null;
  const cx = p.complexity || {};
  const ap = p.approach || null;
  return `
  <div class="section-head">
    <div style="min-width:0">
      <div class="row" style="gap:6px;margin-bottom:6px"><span class="kcard-cat" data-cat="coding">${esc(p.type)}</span>
        ${numBadge(p)}
        <span class="badge ${p.difficulty === 'hard' ? 'badge-err' : p.difficulty === 'medium' ? 'badge-warn' : 'badge-ok'}">${esc(DIFF_ZH[p.difficulty] || p.difficulty)}</span>
        ${p.track === 'model' ? '<span class="badge badge-info">模型手撕</span>' : ''}
        <span class="badge ${badgeCls}">${badgeText}</span>
        <span class="relevance" data-tip="累计出现 ${p.frequencyRaw} 次">频率 ${'★'.repeat(p.frequency)}</span></div>
      <h2 class="section-title">${esc(p.title)}</h2>
      ${p.companies.length ? `<div class="row" style="flex-wrap:wrap;gap:6px;margin-top:6px">
        ${p.companies.slice(0, 8).map((c) => `<span class="chip" style="cursor:default">${esc(c.name)} <span class="tnum" style="opacity:.65">${c.count} 次</span></span>`).join('')}
        ${p.analysisStatus !== 'deep' ? `<span class="text-3" style="font-size:var(--fs-3xs)">该题尚未产出完整解析，已排入下一轮深读队列</span>` : ''}
      </div>` : ''}
    </div>
    <div class="section-actions">
      <button class="btn btn-sm" data-route="#/problems?track=${p.track || 'algorithm'}${p.namespace === 'kamacoder' ? '&ns=kamacoder' : ''}">${icon('i-x')} 返回列表</button>
      <button class="btn btn-sm btn-primary" data-act="status" data-id="${attr(p.id)}" data-status="done">
        ${icon('i-check')} ${statusOf(p.id) === 'done' ? '已掌握' : '标记已掌握'}</button>
    </div>
  </div>

  <div class="grid grid-dash">
    <div class="col" style="gap:var(--sp-4)">
      ${p.statement ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-list')} 题目描述</div></div>
        <div class="panel-body"><div class="prose">${md(p.statement)}</div></div></div>` : ''}

      ${ap ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-bulb')} 解题思路</div></div>
        <div class="panel-body"><div class="prose">
          <p>${md(String(ap.idea || ''))}</p>
          ${ap.steps && ap.steps.length ? `<ol style="list-style:decimal;padding-left:var(--sp-5)">
            ${ap.steps.map((s) => `<li style="margin-bottom:6px">${esc(s)}</li>`).join('')}</ol>` : ''}
          ${ap.whyItWorks ? `<p><b>为什么对：</b>${md(String(ap.whyItWorks))}</p>` : ''}
        </div>
        ${ap.alternatives && ap.alternatives.length ? `<div class="eyebrow" style="margin-top:var(--sp-3)">其它解法</div>
          <ul class="kcard-points">${ap.alternatives.map((x) => `<li><span><b>${esc(x.name || '')}</b>
            ${x.complexity ? `<span class="text-3"> · ${esc(x.complexity)}</span>` : ''}<br><span class="text-3">${esc(x.when || '')}</span></span></li>`).join('')}</ul>` : ''}
        </div></div>` : ''}

      ${p.solution ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-terminal')} 参考实现（Python）</div>
        <button class="icon-btn copy" style="margin-left:auto" data-act="copy" data-copy="${attr(p.solution)}" data-copy-msg="代码已复制"
          aria-label="复制代码">${icon('i-copy')}</button></div>
        <div class="panel-body flush"><pre class="code" style="padding:var(--sp-4)">${highlight(p.solution, 'python')}</pre></div></div>` : ''}

      ${p.variants && p.variants.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-code')} 变体实现（同机制 · 不同写法）</div></div>
        <div class="panel-body"><div class="col" style="gap:var(--sp-4)">
          ${p.variants.map((v) => `<div>
            <div class="eyebrow" style="margin-bottom:4px">${esc(v.name)}${v.cost ? ` <span class="text-3">· ${esc(v.cost)}</span>` : ''}</div>
            ${v.idea ? `<p class="text-3" style="margin:0 0 6px">${md(v.idea)}</p>` : ''}
            ${v.when ? `<p class="text-3" style="margin:0 0 6px"><b>适用：</b>${esc(v.when)}</p>` : ''}
            ${v.code ? `<div style="position:relative"><button class="icon-btn copy" style="position:absolute;top:8px;right:8px" data-act="copy" data-copy="${attr(v.code)}" data-copy-msg="代码已复制" aria-label="复制代码">${icon('i-copy')}</button>
              <pre class="code" style="max-height:320px;overflow:auto">${highlight(v.code, 'python')}</pre></div>` : ''}
          </div>`).join('')}
        </div></div></div>` : ''}

      ${p.comparison && p.comparison.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-grid')} 横向对比</div></div>
        <div class="panel-body" style="overflow-x:auto">
          <table style="width:100%;border-collapse:collapse;font-size:var(--fs-2xs)">
            ${p.comparison.map((row, ri) => `<tr>${row.map((cell, ci) => ri === 0
              ? `<th style="text-align:left;padding:6px 10px;border-bottom:1px solid var(--line-1);white-space:nowrap">${esc(cell)}</th>`
              : `<td style="padding:6px 10px;border-bottom:1px solid var(--line-1)${ci === 0 ? ';font-weight:600' : ''}">${esc(cell)}</td>`).join('')}</tr>`).join('')}
          </table>
        </div></div>` : ''}

      ${p.answerOutline.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-bulb')} 答题框架</div></div>
        <div class="panel-body"><ol class="prose" style="list-style:decimal;padding-left:var(--sp-5)">
          ${p.answerOutline.map((x) => `<li style="margin-bottom:6px">${esc(x)}</li>`).join('')}</ol></div></div>` : ''}

      ${a && a.teaching ? teachingHtml(a.teaching, 'panel') : ''}
      ${a && a.diagram ? diagramHtml(a.diagram) : ''}
      ${a && a.concepts && a.concepts.length ? conceptsHtml(a.concepts, 'panel') : ''}
    </div>

    <div class="col" style="gap:var(--sp-4)">
      ${(cx.time || cx.space) ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-clock')} 复杂度</div></div>
        <div class="panel-body"><div class="row" style="gap:var(--sp-4)">
          <div><div class="eyebrow">时间</div><div style="font-family:var(--font-mono)">${esc(cx.time || '—')}</div></div>
          <div><div class="eyebrow">空间</div><div style="font-family:var(--font-mono)">${esc(cx.space || '—')}</div></div>
        </div>${cx.why ? `<p class="text-3" style="margin-top:var(--sp-2)">${esc(cx.why)}</p>` : ''}</div></div>` : ''}
      ${p.keyPoints.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-target')} 得分要点</div></div>
        <div class="panel-body"><ul class="kcard-points">${p.keyPoints.map((k) => `<li><span>${esc(k)}</span></li>`).join('')}</ul></div></div>` : ''}
      ${p.pitfalls.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-alert')} 常见踩坑</div></div>
        <div class="panel-body"><ul class="kcard-points" data-cat="coding">${p.pitfalls.map((k) => `<li><span>${esc(k)}</span></li>`).join('')}</ul></div></div>` : ''}
      ${p.edgeCases.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-filter')} 边界用例</div></div>
        <div class="panel-body"><ul class="kcard-points">${p.edgeCases.map((k) => `<li><span>${esc(k)}</span></li>`).join('')}</ul></div></div>` : ''}
      ${p.interviewTips ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-briefcase')} 面试怎么说</div></div>
        <div class="panel-body"><div class="prose">${md(p.interviewTips)}</div></div></div>` : ''}
      ${p.origins.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-link')} 来源渠道</div></div>
        <div class="panel-body"><div class="row" style="flex-wrap:wrap;gap:4px">
          ${p.origins.map((o) => `<span class="tag">${esc(o)}</span>`).join('')}</div></div></div>` : ''}
      ${p.sources.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-link')} 题源与题解</div></div>
        <div class="panel-body"><div class="col" style="gap:6px">
          ${p.sources.slice(0, 8).map((s) => `<a class="btn btn-sm btn-ghost" style="justify-content:flex-start" href="${attr(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">
            ${icon('i-external')} <span class="truncate">${esc(s.title || hostOf(s.url))}</span></a>`).join('')}</div></div></div>` : ''}
    </div>
  </div>`;
}

/* ============================ REPOS & COURSES ========================== */

export const ReposView = {
  title: '仓库与课程',
  render(params) {
    const repos = state.repos;
    const courses = state.courses;
    const papers = state.papers || [];
    const tab = params.tab || 'repos';
    if (!repos.length && !courses.length && !papers.length) {
      return `<div class="section-head"><div><h2 class="section-title">仓库与课程</h2>
        <p class="section-desc">固定跟进的仓库、系统课程与必读论文。</p></div></div>` +
        emptyState('还没有学习资源数据', '等待 learning.json 生成，或在其中登记你要跟进的仓库与课程。', 'i-repo');
    }
    const tabs = [['repos', `开源仓库 ${repos.length}`], ['courses', `课程 ${courses.length}`], ['papers', `论文 ${papers.length}`]];
    return `
    <div class="section-head">
      <div><h2 class="section-title">仓库与课程</h2>
      <p class="section-desc">固定资源 + 学习计划 + 检查点。把「收藏」变成「跑通」。</p></div>
    </div>
    <div class="tabs">
      ${tabs.map(([k, label]) => `<button class="tab${tab === k ? ' is-on' : ''}" data-route="#/repos?tab=${k}">${esc(label)}</button>`).join('')}
    </div>
    ${tab === 'repos' ? reposHtml(repos) : tab === 'courses' ? coursesHtml(courses) : papersHtml(papers)}`;
  },
  after() {},
};

function reposHtml(repos) {
  if (!repos.length) return emptyState('暂无仓库数据', '在 learning.json 的 repos 字段登记仓库。', 'i-repo');
  const areas = Array.from(new Set(repos.map((r) => r.area).filter(Boolean)));
  return `
  <div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-4)">
    ${areas.map((a) => `<span class="tag">${esc(a)} · ${repos.filter((r) => r.area === a).length}</span>`).join('')}
  </div>
  <div class="grid grid-auto">
    ${repos.map((r, i) => `
      <article class="card card-pad card-hover" data-cat="course" style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 16}ms">
        <div class="row" style="align-items:flex-start">
          <span class="kcard-cat">${esc(r.language || 'repo')}</span>
          ${r.stars ? `<span class="tag" style="margin-left:auto">★ ${r.stars >= 1000 ? (r.stars / 1000).toFixed(1) + 'k' : r.stars}</span>` : ''}
        </div>
        <h3 class="kcard-title" style="margin-top:var(--sp-3);font-family:var(--font-mono);font-size:var(--fs-sm)">
          <span class="text-3">${esc(r.owner)}/</span>${esc(r.name)}</h3>
        ${r.why ? `<p class="kcard-summary clamp-3">${esc(r.why)}</p>` : ''}
        ${r.studyPlan.length ? `<div>
          <div class="eyebrow" style="margin-bottom:4px">学习计划</div>
          <ul class="kcard-points">${r.studyPlan.slice(0, 4).map((s) => `<li><span>${esc(s)}</span></li>`).join('')}</ul>
        </div>` : ''}
        ${r.checkpoints.length ? `<div class="row" style="flex-wrap:wrap;gap:4px">
          ${r.checkpoints.slice(0, 3).map((c) => `<span class="tag">${esc(c)}</span>`).join('')}</div>` : ''}
        <div class="kcard-foot">
          <span class="badge ${r.status === 'active' ? 'badge-ok' : 'badge-mute'}">${r.status === 'active' ? '活跃' : '待复核'}</span>
          ${r.lastVerified ? `<span class="text-3" data-tip="最近核验">${esc(fmtDate(r.lastVerified))}</span>` : ''}
          <a class="kcard-src" style="margin-left:auto" href="${attr(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">
            ${icon('i-external', '', 11)} GitHub</a>
        </div>
      </article>`).join('')}
  </div>`;
}

function coursesHtml(courses) {
  if (!courses.length) return emptyState('暂无课程数据', '在 learning.json 的 courses 字段登记课程。', 'i-book');
  return `<div class="grid grid-auto">
    ${courses.map((c, i) => `
      <article class="card card-pad card-hover" data-cat="system" style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 16}ms">
        <div class="row"><span class="kcard-cat">${esc(c.provider || '课程')}</span>
          ${c.year ? `<span class="tag" style="margin-left:auto">${esc(String(c.year))}</span>` : ''}</div>
        <h3 class="kcard-title" style="margin-top:var(--sp-3)">${esc(c.title)}</h3>
        ${c.why ? `<p class="kcard-summary clamp-3">${esc(c.why)}</p>` : ''}
        <dl class="kv" style="margin-top:var(--sp-2)">
          <dt>时长</dt><dd>${c.hours ? c.hours + ' 小时' : '—'}</dd>
          <dt>难度</dt><dd>${esc({ beginner: '入门', intermediate: '进阶', advanced: '高阶' }[c.level] || c.level)}</dd>
          <dt>语言</dt><dd>${c.language === 'zh' ? '中文' : '英文'}</dd>
          <dt>作业</dt><dd>${c.hasAssignments ? '有' : '无'}</dd>
        </dl>
        <div class="kcard-foot">
          ${c.area ? `<span class="tag">${esc(c.area)}</span>` : ''}
          <a class="kcard-src" style="margin-left:auto" href="${attr(safeUrl(c.url))}" target="_blank" rel="noopener noreferrer">
            ${icon('i-external', '', 11)} 课程主页</a>
        </div>
      </article>`).join('')}</div>`;
}

function papersHtml(papers) {
  if (!papers.length) return emptyState('暂无论文数据', '等待每日采集把 arXiv 结果写入工作台。', 'i-flask');
  const must = papers.filter((p) => p.mustRead);
  const rest = papers.filter((p) => !p.mustRead);
  const row = (p, i) => `
    <div class="card card-pad card-hover" data-cat="paper" style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 14}ms">
      <div class="row" style="align-items:flex-start">
        <span class="kcard-cat">${esc(p.venue || p.area || '论文')}${p.year ? ' ' + p.year : ''}</span>
        ${p.ccf ? `<span class="tag tag-accent" style="margin-left:auto">CCF-${esc(p.ccf)}</span>` : ''}
      </div>
      <h3 class="kcard-title" style="margin-top:var(--sp-3);font-size:var(--fs-sm)">${esc(p.title)}</h3>
      ${p.why ? `<div class="kcard-why"><b>为什么读 · </b>${esc(p.why)}</div>` : ''}
      ${p.keyIdeas.length ? `<ul class="kcard-points">${p.keyIdeas.slice(0, 3).map((k) => `<li><span>${esc(k)}</span></li>`).join('')}</ul>` : ''}
      <div class="kcard-foot">
        ${p.readTime ? `<span class="badge badge-mute">${esc(p.readTime)}</span>` : ''}
        ${p.readingOrder ? `<span class="text-3">阅读顺序 #${p.readingOrder}</span>` : ''}
        <span class="text-3" style="margin-left:auto">${esc(DIFF_ZH[p.difficulty] || '')}</span>
        <a class="kcard-src" href="${attr(safeUrl(p.url))}" target="_blank" rel="noopener noreferrer">${icon('i-external', '', 11)} 原文</a>
      </div>
    </div>`;
  return `
  ${must.length ? `<div class="section-head"><div><h3 class="section-title" style="font-size:var(--fs-lg)">必读奠基</h3>
    <p class="section-desc">按阅读顺序编号，先建立主干再补分支。</p></div></div>
    <div class="grid grid-auto" style="margin-bottom:var(--sp-6)">${must.map(row).join('')}</div>` : ''}
  <div class="section-head"><div><h3 class="section-title" style="font-size:var(--fs-lg)">延伸与前沿</h3></div></div>
  <div class="grid grid-auto">${rest.map(row).join('')}</div>`;
}

/* ================================ JOBS ================================= */

export const JobsView = {
  title: '岗位看板',
  render(params) {
    const jobs = state.jobs;
    if (!jobs.length) {
      return `<div class="section-head"><div><h2 class="section-title">岗位看板</h2>
        <p class="section-desc">实时招聘信息、JD 要求与投递节奏。</p></div></div>` +
        emptyState('还没有岗位数据', '运行采集器读取各厂招聘官网，或把 jobs.json 中的 companies 补充完整。', 'i-briefcase',
          `<button class="btn btn-sm" data-route="#/pipeline">查看采集配置</button>`);
    }
    if (params.focus) {
      const j = jobs.find((x) => x.id === params.focus);
      if (j) return jobDetailHtml(j);
    }

    const dirs = new Set();
    for (const j of jobs) for (const d of j.directions) dirs.add(d);
    const cities = new Set();
    for (const j of jobs) for (const c of j.cities) cities.add(c);

    const stages = jobStageCounts();
    const filtered = jobs.filter((j) => {
      if (state.filters.cat.size && !j.directions.some((d) => state.filters.cat.has(d))) return false;
      if (state.filters.q) {
        const hay = [j.company, j.title, j.notes, ...j.directions, ...j.cities, ...j.highlights].join(' ').toLowerCase();
        if (!hay.includes(state.filters.q.toLowerCase())) return false;
      }
      return true;
    }).sort((a, b) => (TIER_ORDER.indexOf(a.tier) - TIER_ORDER.indexOf(b.tier)) || b.relevance - a.relevance);

    return `
    <div class="section-head">
      <div><h2 class="section-title">岗位看板</h2>
      <p class="section-desc">共 ${jobs.length} 个机会 · ${jobs.filter((j) => j.open).length} 个开放中 · 按公司梯队与方向匹配排序。</p></div>
      <div class="section-actions">
        <button class="btn btn-sm btn-ghost" data-act="export">${icon('i-download')} 导出进度</button>
      </div>
    </div>

    <div class="grid grid-4" style="margin-bottom:var(--sp-5)">
      ${Object.entries(STAGES).map(([k, v]) => `
        <div class="card card-pad" style="border-left:3px solid ${v.color}">
          <div class="eyebrow">${esc(v.label)}</div>
          <div class="stat-val" style="font-size:var(--fs-xl);margin-top:4px">${stages[k] || 0}<small>个</small></div>
        </div>`).join('')}
    </div>

    <div class="panel" style="margin-bottom:var(--sp-5)">
      <div class="panel-head"><div class="panel-title">${icon('i-route')} 投递漏斗</div>
        <span class="result-line" style="margin-left:auto">点击卡片可拖拽/切换阶段（使用下方按钮）</span></div>
      <div class="panel-body">
        <div class="kanban" id="kanban">
          ${Object.entries(STAGES).map(([k, v]) => {
            const list = jobs.filter((j) => (state.user.jobStage[j.id] || 'todo') === k);
            return `<div class="kan-col" data-stage="${k}">
              <div class="kan-head"><span style="width:8px;height:8px;border-radius:2px;background:${v.color}"></span>
                <span class="kan-title">${esc(v.label)}</span><span class="kan-count">${list.length}</span></div>
              ${list.map((j) => `
                <div class="card kan-card" data-cat="job" draggable="true" data-job="${attr(j.id)}">
                  <div class="row" style="gap:6px"><span class="tier" data-tier="${attr(j.tier)}">${esc(j.tier)}</span>
                    <span style="font-weight:640;color:var(--fg-0)">${esc(j.company)}</span></div>
                  <div class="text-2" style="margin-top:4px">${esc(j.directions.slice(0, 3).join(' · ') || j.title)}</div>
                  <div class="row" style="margin-top:6px;gap:4px">
                    <button class="btn btn-sm btn-ghost" data-act="open-job" data-id="${attr(j.id)}">详情</button>
                  </div>
                </div>`).join('') || `<div class="text-3" style="font-size:var(--fs-3xs);padding:var(--sp-2)">拖拽卡片到此</div>`}
            </div>`;
          }).join('')}
        </div>
      </div>
    </div>

    <div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-4)">
      <span class="eyebrow" style="margin-right:4px">方向</span>
      ${Array.from(dirs).map((d) => `<button class="chip${state.filters.cat.has(d) ? ' is-on' : ''}" data-act="toggle-cat" data-cat="${attr(d)}">${esc(dirZh(d))}</button>`).join('')}
      <span class="eyebrow" style="margin:0 4px 0 var(--sp-3)">城市</span>
      ${Array.from(cities).map((c) => `<span class="tag">${esc(c)}</span>`).join('')}
    </div>

    <div class="panel">
      <div class="panel-head"><div class="panel-title">${icon('i-list')} 机会清单</div>
        <span class="result-line" style="margin-left:auto">${filtered.length} / ${jobs.length}</span></div>
      <div class="panel-body flush">
        ${filtered.map((j) => `
          <div class="job-row" data-cat="job">
            <div class="job-co">
              <span class="tier" data-tier="${attr(j.tier)}" data-tip="${esc(tierZh(j.tier))}">${esc(j.tier)}</span>
              <div style="min-width:0">
                <div class="job-co-name truncate">${esc(j.company)}</div>
                <div class="job-co-meta">${esc(j.cities.slice(0, 2).join(' · ') || '城市待定')}</div>
              </div>
            </div>
            <div class="job-role">
              <div class="truncate" style="color:var(--fg-0);font-weight:580">${esc(j.title)}</div>
              <div class="dir truncate" style="font-size:var(--fs-3xs)">${esc(j.directions.slice(0, 4).join(' / ') || j.notes.slice(0, 60))}</div>
            </div>
            <div class="job-pay">${esc(j.pay || '面议')}</div>
            <div class="job-city text-3" style="font-size:var(--fs-3xs)">${j.open ? '开放中' : '已关闭'}${j.deadline ? ` · 截止 ${esc(fmtDate(j.deadline))}` : ''}</div>
            <div class="row" style="gap:4px">
              ${j.applyUrl ? `<a class="icon-btn" href="${attr(j.applyUrl)}" target="_blank" rel="noopener noreferrer" data-tip="投递页">${icon('i-external')}</a>` : ''}
              <button class="icon-btn" data-act="open-job" data-id="${attr(j.id)}" data-tip="详情">${icon('i-chevron')}</button>
            </div>
          </div>`).join('')}
      </div>
    </div>`;
  },
  after() { wireKanban(); },
};

const TIER_ORDER = ['S', 'A', 'B', 'C'];
const tierZh = (t) => ({ S: '一线大厂核心组', A: '一线大厂/明星创业', B: '成长型公司', C: '其他' }[t] || '其他');
const dirZh = (d) => ({
  multimodal: '多模态', 'post-training': '后训练', worldmodel: '世界模型', 'world-model': '世界模型',
  generative: '生成式', rl: '强化学习', agent: 'Agent', infra: '工程/推理', embodied: '具身智能', vision: '视觉', nlp: 'NLP',
}[d] || d);

function wireKanban() {
  const board = $('#kanban');
  if (!board) return;
  let dragging = null;
  board.addEventListener('dragstart', (e) => {
    const card = e.target.closest('[data-job]');
    if (!card) return;
    dragging = card.dataset.job;
    card.classList.add('dragging');
    e.dataTransfer.setData('text/plain', dragging);
    e.dataTransfer.effectAllowed = 'move';
  });
  board.addEventListener('dragend', (e) => {
    const card = e.target.closest('[data-job]');
    if (card) card.classList.remove('dragging');
    $$('.kan-col').forEach((c) => c.classList.remove('drop-target'));
    dragging = null;
  });
  board.addEventListener('dragover', (e) => {
    const col = e.target.closest('.kan-col');
    if (!col) return;
    e.preventDefault();
    $$('.kan-col').forEach((c) => c.classList.toggle('drop-target', c === col));
  });
  board.addEventListener('drop', (e) => {
    const col = e.target.closest('.kan-col');
    if (!col) return;
    e.preventDefault();
    const id = e.dataTransfer.getData('text/plain') || dragging;
    if (!id) return;
    state.user.jobStage[id] = col.dataset.stage;
    saveUser();
    toast(`已移动到「${STAGES[col.dataset.stage].label}」`, 'ok', 1500);
    render();
  });
  board.addEventListener('click', (e) => {
    const card = e.target.closest('[data-job]');
    if (!card || e.target.closest('button')) return;
    openJob(card.dataset.job);
  });
}

function jobDetailHtml(j) {
  const st = state.user.jobStage[j.id] || 'todo';
  return `
  <div class="section-head">
    <div style="min-width:0">
      <div class="row" style="gap:6px;margin-bottom:6px">
        <span class="tier" data-tier="${attr(j.tier)}">${esc(j.tier)}</span>
        <span class="badge ${j.open ? 'badge-ok' : 'badge-mute'}">${j.open ? '开放中' : '已关闭'}</span>
        ${j.confidence ? `<span class="badge badge-mute">可信度 ${esc(j.confidence)}</span>` : ''}
      </div>
      <h2 class="section-title">${esc(j.company)} · ${esc(j.title)}</h2>
      <p class="section-desc">${esc(j.cities.join(' / ') || '城市待定')} · ${esc(j.pay || '薪资面议')}${j.duration ? ' · ' + esc(j.duration) : ''}</p>
    </div>
    <div class="section-actions">
      <button class="btn btn-sm" data-route="#/jobs">${icon('i-x')} 返回</button>
      ${j.applyUrl ? `<a class="btn btn-sm btn-primary" href="${attr(j.applyUrl)}" target="_blank" rel="noopener noreferrer">
        ${icon('i-external')} 打开投递页</a>` : ''}
    </div>
  </div>

  <div class="grid grid-dash">
    <div class="col" style="gap:var(--sp-4)">
      ${j.highlights.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-spark')} 团队与亮点</div></div>
        <div class="panel-body"><ul class="kcard-points">${j.highlights.map((h) => `<li><span>${esc(h)}</span></li>`).join('')}</ul></div></div>` : ''}
      ${j.process.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-route')} 面试流程</div></div>
        <div class="panel-body"><div class="timeline">
          ${j.process.map((s, i) => `<div class="tl-item" data-cat="job">
            <span class="tl-dot"></span>
            <div class="tl-head"><span class="tl-title">${esc(s)}</span><span class="tl-week">第 ${i + 1} 步</span></div>
          </div>`).join('')}
        </div></div></div>` : ''}
      ${j.notes ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-info')} 备注与判断</div></div>
        <div class="panel-body"><div class="prose">${md(j.notes)}</div></div></div>` : ''}
      ${j.sources.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-link')} 信息来源</div></div>
        <div class="panel-body"><div class="col" style="gap:6px">
          ${j.sources.map((s) => `<a class="btn btn-sm btn-ghost" style="justify-content:flex-start" href="${attr(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">
            ${icon('i-external')} <span class="truncate">${esc(s.title || hostOf(s.url))}</span></a>`).join('')}</div></div></div>` : ''}
    </div>
    <div class="col" style="gap:var(--sp-4)">
      <div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-flag')} 投递阶段</div></div>
        <div class="panel-body"><div class="col" style="gap:6px">
          ${Object.entries(STAGES).map(([k, v]) => `
            <button class="btn btn-sm${st === k ? ' btn-primary' : ''}" style="justify-content:flex-start"
              data-act="job-stage" data-id="${attr(j.id)}" data-stage="${k}">
              <span style="width:8px;height:8px;border-radius:2px;background:${st === k ? 'currentColor' : v.color};display:inline-block"></span>
              ${esc(v.label)}</button>`).join('')}
        </div></div></div>
      <div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-target')} 匹配方向</div></div>
        <div class="panel-body">
          <div class="row" style="flex-wrap:wrap;gap:4px">${j.directions.map((d) => `<span class="tag">${esc(dirZh(d))}</span>`).join('') || '<span class="text-3">—</span>'}</div>
          ${j.seasonality ? `<div class="kcard-why" style="margin-top:var(--sp-3)"><b>招聘节奏 · </b>${esc(j.seasonality)}</div>` : ''}
          ${j.conversion ? `<div class="kcard-why" style="margin-top:var(--sp-2)"><b>转正 · </b>${esc(j.conversion)}</div>` : ''}
        </div></div>
    </div>
  </div>`;
}

/* ============================== SKILLS ================================= */

export const SkillsView = {
  title: '技能矩阵',
  render() {
    const skills = state.skills;
    if (!skills.length) {
      return `<div class="section-head"><div><h2 class="section-title">技能矩阵</h2>
        <p class="section-desc">岗位要求的技能、重要度与你当前掌握度的差距。</p></div></div>` +
        emptyState('还没有技能数据', '等待 jobs.json 的 skillMatrix 字段。', 'i-target');
    }
    const cats = new Map();
    for (const s of skills) cats.set(s.category, (cats.get(s.category) || 0) + 1);
    const sorted = skills.slice().sort((a, b) => b.importance - a.importance);
    const gapScore = (s) => s.importance * 20 - (state.user.mastery[s.id] || 0) * 20;

    return `
    <div class="section-head">
      <div><h2 class="section-title">技能矩阵</h2>
      <p class="section-desc">按「岗位重要度 × 我的掌握度」排序，先补高重要度、低掌握的缺口。</p></div>
      <div class="section-actions">
        <select class="select select-sm" id="skill-cat" aria-label="技能分类">
          <option value="">全部分类</option>
          ${Array.from(cats.entries()).map(([c, n]) => `<option value="${attr(c)}">${esc(c)} (${n})</option>`).join('')}
        </select>
      </div>
    </div>

    <div class="grid grid-2">
      ${sorted.map((s, i) => {
        const m = state.user.mastery[s.id] || 0;
        const gap = gapScore(s);
        return `
        <article class="card card-pad" data-cat="${gap > 40 ? 'posttraining' : gap > 20 ? 'rl' : 'agent'}"
          style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${Math.min(i * 14, 300)}ms">
          <div class="row" style="align-items:flex-start">
            <div class="grow">
              <h3 class="kcard-title" style="font-size:var(--fs-sm)">${esc(s.skill)}</h3>
              <div class="row" style="gap:6px;margin-top:4px">
                <span class="tag">${esc(s.category)}</span>
                ${s.learnCost ? `<span class="tag">约 ${esc(s.learnCost)}</span>` : ''}
              </div>
            </div>
            <div class="col" style="align-items:flex-end;gap:4px">
              <span class="relevance" data-tip="岗位重要度">${'★'.repeat(s.importance)}${'☆'.repeat(5 - s.importance)}</span>
              <span class="text-3" style="font-size:var(--fs-3xs)">重要度 ${s.importance}/5</span>
            </div>
          </div>

          ${s.evidence ? `<p class="kcard-summary" style="margin-top:var(--sp-3)">${esc(s.evidence)}</p>` : ''}
          ${s.howToProve ? `<div class="kcard-why" style="margin-top:var(--sp-2)"><b>如何证明 · </b>${esc(s.howToProve)}</div>` : ''}

          <div style="margin-top:var(--sp-3)">
            <div class="row" style="justify-content:space-between;margin-bottom:6px">
              <span class="eyebrow">我的掌握度</span>
              <span class="text-3" style="font-size:var(--fs-3xs)">差距 ${Math.max(0, gap)} 分</span>
            </div>
            <div class="row" style="gap:4px">
              ${[1, 2, 3, 4, 5].map((v) => `
                <button class="icon-btn" data-act="mastery" data-id="${attr(s.id)}" data-v="${v}"
                  style="width:28px;height:22px;border-radius:var(--r-xs);background:${v <= m ? 'var(--accent)' : 'var(--bg-4)'};color:${v <= m ? 'var(--accent-fg)' : 'var(--fg-3)'}"
                  aria-label="掌握度 ${v}" data-tip="掌握度 ${v}/5">${v}</button>`).join('')}
            </div>
          </div>

          ${s.demand.length ? `<div class="row" style="flex-wrap:wrap;gap:4px;margin-top:var(--sp-3)">
            <span class="eyebrow">需求公司</span>
            ${s.demand.map((d) => `<span class="tag">${esc(d)}</span>`).join('')}</div>` : ''}
        </article>`;
      }).join('')}
    </div>`;
  },
  after() {
    const sel = $('#skill-cat');
    if (sel) sel.addEventListener('change', () => {
      const cat = sel.value;
      $$('.grid-2 > article').forEach((n) => {
        const tag = n.querySelector('.tag');
        n.classList.toggle('hide', Boolean(cat) && (!tag || tag.textContent.trim() !== cat));
      });
    });
  },
};

/* ============================== ROADMAP ================================ */

export const RoadmapView = {
  title: '学习路线',
  render(params) {
    const tracks = state.tracks;
    if (!tracks.length) {
      return `<div class="section-head"><div><h2 class="section-title">系统学习路线</h2>
        <p class="section-desc">按方向拆分的模块化路线，含任务、交付物与验收标准。</p></div></div>` +
        emptyState('还没有路线数据', '等待 learning.json 的 tracks 字段。', 'i-route');
    }
    const tasks = collectTasks();
    const doneCount = tasks.filter((t) => state.user.tasks[t.key]).length;
    const active = params.track ? tracks.find((t) => t.id === params.track) : tracks[0];
    const sys = state.studySystem;
    const prof = (state.learningKb && state.learningKb.profile) || null;

    return `
    <div class="section-head">
      <div><h2 class="section-title">系统学习路线</h2>
      <p class="section-desc">${tracks.length} 条路线 · ${tasks.length} 个任务 · 已完成 <b style="color:var(--accent)">${doneCount}</b>
      个（<span data-task-progress>${doneCount}/${tasks.length}</span>）</p>
      <div style="margin-top:var(--sp-3);max-width:520px">
        <div class="bar bar-lg"><i data-task-bar style="width:${tasks.length ? (doneCount / tasks.length) * 100 : 0}%"></i></div>
      </div>
      </div>
    </div>

    ${prof ? `
    <div class="grid grid-2" style="margin-bottom:var(--sp-5)">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">${icon('i-target')} 你的起点与优先级</div>
          <span class="badge badge-info" style="margin-left:auto">已按你的情况重排</span></div>
        <div class="panel-body">
          <div class="grid grid-2" style="gap:var(--sp-3)">
            ${Object.entries(prof.startingPoint || {}).map(([k, v]) => `
              <div class="card card-pad" data-cat="${k === 'coding' ? 'posttraining' : k === 'research' ? 'agent' : 'system'}" style="padding:var(--sp-3)">
                <div class="eyebrow">${esc({ pytorch: 'PyTorch', research: '科研产出', coding: '刷题', rl: '强化学习' }[k] || k)}</div>
                <div style="font-size:var(--fs-sm);font-weight:640;color:var(--fg-0);margin:4px 0">${esc(v.level)}</div>
                <div class="text-2" style="font-size:var(--fs-3xs)">${esc(v.note)}</div>
              </div>`).join('')}
          </div>
          ${prof.priorityOrder ? `<div class="eyebrow" style="margin:var(--sp-4) 0 6px">为什么这样排序</div>
            <ol style="list-style:decimal;padding-left:var(--sp-5);font-size:var(--fs-2xs);color:var(--fg-1)">
              ${prof.priorityOrder.map((p) => `<li style="margin-bottom:3px">${esc(p)}</li>`).join('')}</ol>` : ''}
        </div>
      </div>

      <div class="panel">
        <div class="panel-head"><div class="panel-title">${icon('i-flask')} ICLR 论文 · 抗追问清单</div>
          <span class="result-line" style="margin-left:auto">${(prof.paperQuestions || []).length} 类</span></div>
        <div class="panel-body">
          ${(prof.paperQuestions || []).length ? `
            <div class="text-2" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
              你已有一篇 ICLR 多模态分割论文 —— 这是你相对同届最硬的资产，面试里会占掉 30%–50% 的时间。
              所以「把它讲清楚」的优先级高于再读十篇新论文。逐条准备下面的追问：</div>
            <ul class="kcard-points" data-cat="paper">
              ${prof.paperQuestions.map((q) => `<li><span>${esc(q)}</span></li>`).join('')}
            </ul>
            <div class="row" style="margin-top:var(--sp-3);gap:var(--sp-2)">
              <button class="btn btn-sm" data-route="#/roadmap?track=paper">${icon('i-route')} 论文讲述路线</button>
              <button class="btn btn-sm btn-ghost" data-route="#/roadmap?track=coding">${icon('i-code')} 手撕题路线</button>
            </div>
          ` : '<div class="status-line"><span class="warn">尚未生成追问清单</span></div>'}
        </div>
      </div>
    </div>` : ''}

    <div class="tabs">
      ${tracks.map((t) => `<button class="tab${active && t.id === active.id ? ' is-on' : ''}" data-route="#/roadmap?track=${encodeURIComponent(t.id)}">
        ${esc(t.name)}<span class="cnt">${t.modules.length}</span></button>`).join('')}
    </div>

    ${active ? `
    <div class="grid grid-dash">
      <div class="col" style="gap:var(--sp-4)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-route')} ${esc(active.name)}</div>
            <span class="badge badge-info" style="margin-left:auto">${active.weeks} 周 · ${esc({ core: '核心', support: '支撑', advanced: '进阶' }[active.level] || active.level)}</span></div>
          <div class="panel-body">
            ${active.goal ? `<div class="kcard-why" style="margin-bottom:var(--sp-4)"><b>目标 · </b>${esc(active.goal)}</div>` : ''}
            ${active.prerequisites.length ? `<div class="row" style="flex-wrap:wrap;gap:4px;margin-bottom:var(--sp-4)">
              <span class="eyebrow">前置</span>${active.prerequisites.map((p) => `<span class="tag">${esc(p)}</span>`).join('')}</div>` : ''}
            <div class="timeline">
              ${active.modules.map((m) => {
                const mTasks = m.tasks.map((k) => `${active.id}:${k.id}`);
                const mDone = mTasks.filter((k) => state.user.tasks[k]).length;
                const pct = m.tasks.length ? (mDone / m.tasks.length) * 100 : 0;
                const bodyId = `mod-${m.id}`;
                return `
                <div class="tl-item" data-cat="system">
                  <span class="tl-dot${pct === 100 ? ' done' : ''}"></span>
                  <div class="tl-head">
                    <span class="tl-title">${esc(m.title)}</span>
                    ${m.week ? `<span class="tl-week">W${m.week}</span>` : ''}
                    ${m.hours ? `<span class="tl-week">${m.hours}h</span>` : ''}
                    <span class="result-line" style="margin-left:auto">${mDone}/${m.tasks.length}</span>
                  </div>
                  <div style="margin:6px 0 var(--sp-3);max-width:420px">${progressBar(pct)}</div>

                  <div class="module">
                    <div class="module-head" data-act="toggle-expand" data-target="${bodyId}" role="button" tabindex="0" aria-controls="${bodyId}">
                      ${icon('i-chevrondown')}
                      <span class="module-name">任务与交付物</span>
                      <span class="module-meta">${m.tasks.length} 个任务 · ${m.tasks.reduce((a, b) => a + b.estimateHours, 0)}h</span>
                    </div>
                    <div class="module-body" id="${bodyId}">
                      ${m.objectives.length ? `<div class="eyebrow" style="margin-bottom:6px">学习目标</div>
                        <ul class="kcard-points" style="margin-bottom:var(--sp-3)">${m.objectives.map((o) => `<li><span>${esc(o)}</span></li>`).join('')}</ul>` : ''}
                      ${m.concepts.length ? `<div class="row" style="flex-wrap:wrap;gap:4px;margin-bottom:var(--sp-3)">
                        ${m.concepts.map((c) => `<span class="tag">${esc(c)}</span>`).join('')}</div>` : ''}
                      ${m.tasks.map((k) => {
                        const key = `${active.id}:${k.id}`;
                        const on = Boolean(state.user.tasks[key]);
                        return `<div class="task${on ? ' on' : ''}">
                          <button class="task-check${on ? ' on' : ''}" data-act="toggle-task" data-key="${attr(key)}"
                            aria-label="标记完成" aria-pressed="${on}"></button>
                          <div class="task-main">
                            <div class="task-title">${esc(k.title)}</div>
                            ${k.done ? `<div class="task-done">验收：${esc(k.done)}</div>` : ''}
                            ${k.deliverable ? `<div class="task-done">交付：${esc(k.deliverable)}</div>` : ''}
                          </div>
                          <div class="task-badges">
                            ${k.estimateHours ? `<span class="tag">${k.estimateHours}h</span>` : ''}
                            <span class="tag">${esc(TASK_TYPE[k.type] || k.type)}</span>
                          </div>
                        </div>`;
                      }).join('')}
                    </div>
                  </div>
                </div>`;
              }).join('')}
            </div>
          </div>
        </div>
      </div>

      <div class="col" style="gap:var(--sp-4)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-layers')} 全部路线</div></div>
          <div class="panel-body" style="padding:0">
            <div class="mini-list">
              ${tracks.map((t) => {
                const ts = collectTasks().filter((x) => x.track.id === t.id);
                const d = ts.filter((x) => state.user.tasks[x.key]).length;
                return `<button class="mini-item" style="width:100%;text-align:left" data-route="#/roadmap?track=${encodeURIComponent(t.id)}">
                  <span class="dot" data-cat="${d === ts.length && ts.length ? 'agent' : 'system'}"></span>
                  <span class="t">${esc(t.name)}<div class="text-3" style="font-size:var(--fs-3xs)">${t.weeks} 周 · ${ts.length} 任务</div></span>
                  <span class="n">${d}/${ts.length}</span>
                </button>`;
              }).join('')}
            </div>
          </div>
        </div>

        ${sys ? `<div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-clock')} 学习系统</div></div>
          <div class="panel-body">
            ${sys.weeklyRhythm ? `<div class="eyebrow" style="margin-bottom:6px">每周节奏</div>
              <ul class="kcard-points" style="margin-bottom:var(--sp-4)">${sys.weeklyRhythm.map((r) => `<li><span>${esc(r)}</span></li>`).join('')}</ul>` : ''}
            ${sys.spacedRepetition ? `<div class="eyebrow" style="margin-bottom:6px">间隔重复</div>
              <div class="text-2" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
                间隔 ${(sys.spacedRepetition.intervals || []).join(' / ')} 天${sys.spacedRepetition.rule ? ' · ' + esc(sys.spacedRepetition.rule) : ''}</div>` : ''}
            ${sys.noteTemplate ? `<div class="eyebrow" style="margin-bottom:6px">笔记模板</div>
              <ol style="list-style:decimal;padding-left:var(--sp-5);font-size:var(--fs-2xs);color:var(--fg-1)">
                ${sys.noteTemplate.map((n) => `<li style="margin-bottom:3px">${esc(n)}</li>`).join('')}</ol>` : ''}
            ${sys.antiPatterns ? `<div class="eyebrow" style="margin:var(--sp-4) 0 6px">反模式</div>
              <div class="row" style="flex-wrap:wrap;gap:4px">${sys.antiPatterns.map((a) => `<span class="tag" style="border-color:color-mix(in oklab,var(--err) 40%,transparent);color:var(--err)">${esc(a)}</span>`).join('')}</div>` : ''}
          </div>
        </div>` : ''}

        ${state.milestones && state.milestones.length ? `<div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-flag')} 里程碑</div></div>
          <div class="panel-body" style="padding:0">
            <div class="mini-list">
              ${state.milestones.map((m) => `<div class="mini-item">
                <span class="dot" data-cat="agent"></span>
                <span class="t">${esc(m.title)}<div class="text-3" style="font-size:var(--fs-3xs)">${esc((m.acceptance || []).slice(0, 2).join(' · '))}</div></span>
                <span class="n">${m.week ? 'W' + m.week : ''}</span></div>`).join('')}
            </div>
          </div>
        </div>` : ''}
      </div>
    </div>` : ''}`;
  },
  after() { updateTaskProgress(); },
};

const TASK_TYPE = { paper: '论文', code: '代码', course: '课程', project: '项目', drill: '刷题', study: '学习' };

/* ============================== PROGRESS =============================== */

export const ProgressView = {
  title: '进度与统计',
  render() {
    const s = completionStats();
    const byCat = CATEGORIES.map((c) => {
      const list = state.items.filter((i) => i.category === c.id);
      const done = list.filter((i) => statusOf(i.id) === 'done').length;
      const reading = list.filter((i) => statusOf(i.id) === 'reading').length;
      return { c, total: list.length, done, reading, pct: list.length ? (done / list.length) * 100 : 0 };
    }).filter((x) => x.total);
    const bySrc = allChannels().slice(0, 12);
    const days = groupByDay(state.items);
    const tasks = collectTasks();
    const taskDone = tasks.filter((t) => state.user.tasks[t.key]).length;
    const skills = state.skills;
    const skillAvg = skills.length ? skills.reduce((a, b) => a + (state.user.mastery[b.id] || 0), 0) / skills.length : 0;
    const problems = state.problems;
    const probDone = problems.filter((p) => statusOf(p.id) === 'done').length;

    return `
    <div class="section-head"><div><h2 class="section-title">进度与统计</h2>
      <p class="section-desc">所有状态保存在浏览器 localStorage。收藏与掌握度可以写成学习信号，让每日采集向你实际在学的方向倾斜。</p></div>
      <div class="section-actions">
        <button class="btn btn-sm btn-ghost" data-act="export">${icon('i-download')} 导出进度</button>
        <button class="btn btn-sm" data-act="export-feedback" data-tip="写出 web/data/feedback.json：采集器会据此调整类目权重与深读配额">${icon('i-refresh')} 写出学习信号</button>
      </div></div>

    <div class="grid grid-4" style="margin-bottom:var(--sp-6)">
      ${[
        ['知识卡片', s.total, `${s.done} 已掌握`],
        ['刷题进度', problems.length, `${probDone} 已完成`],
        ['学习任务', tasks.length, `${taskDone} 已完成`],
        ['平均掌握度', skills.length ? skillAvg.toFixed(1) : '—', skills.length ? `覆盖 ${skills.length} 项技能` : '暂无技能数据'],
      ].map(([k, v, sub]) => `
        <div class="card card-pad">
          <div class="eyebrow">${esc(k)}</div>
          <div class="stat-val" style="font-size:var(--fs-2xl);margin-top:6px">${esc(String(v))}</div>
          <div class="text-3" style="font-size:var(--fs-3xs)">${esc(sub)}</div>
        </div>`).join('')}
    </div>

    <div class="grid grid-dash">
      <div class="col" style="gap:var(--sp-5)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-grid')} 分类掌握度</div></div>
          <div class="panel-body">
            <div class="col" style="gap:var(--sp-4)">
              ${byCat.map(({ c, total, done, reading, pct }) => `
                <div data-cat="${c.id}">
                  <div class="row" style="justify-content:space-between;margin-bottom:6px">
                    <span style="font-size:var(--fs-xs);font-weight:600;color:var(--fg-0)">${esc(c.zh)}</span>
                    <span class="text-3" style="font-size:var(--fs-3xs)">${done} 掌握 · ${reading} 学习中 · ${total} 总计 · ${Math.round(pct)}%</span>
                  </div>
                  ${progressBar(pct, c.id)}
                </div>`).join('') || emptyState('暂无分类数据', '等待首次采集。', 'i-grid')}
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-chart')} 每日采集量</div>
            <span class="result-line" style="margin-left:auto">最近 ${Math.min(days.length, 30)} 天</span></div>
          <div class="panel-body">
            ${sparkline(days.slice(0, 30).reverse().map((d) => d.items.length), { w: 560, h: 90 })}
            <div class="tbl-wrap" style="margin-top:var(--sp-4)">
              <table class="tbl">
                <thead><tr><th>日期</th><th class="num">条数</th><th class="num">已掌握</th><th>热门分类</th></tr></thead>
                <tbody>
                  ${days.slice(0, 12).map((d) => {
                    const cc = new Map();
                    for (const it of d.items) cc.set(it.category, (cc.get(it.category) || 0) + 1);
                    const top = Array.from(cc.entries()).sort((a, b) => b[1] - a[1]).slice(0, 3);
                    return `<tr><td>${esc(d.day)} <span class="text-3">${esc(weekdayZh(d.day))}</span></td>
                      <td class="num">${d.items.length}</td>
                      <td class="num">${d.items.filter((i) => statusOf(i.id) === 'done').length}</td>
                      <td>${top.map(([c, n]) => `<span class="tag" data-cat="${c}">${esc((CAT_BY_ID[c] || {}).zh || c)} ${n}</span>`).join(' ')}</td></tr>`;
                  }).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <div class="col" style="gap:var(--sp-5)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-star')} 收藏夹概览</div>
            <button class="btn btn-sm btn-ghost" style="margin-left:auto" data-route="#/starred">查看</button></div>
          <div class="panel-body">
            <div class="donut-wrap">
              ${ring(s.total ? (s.starred / s.total) * 100 : 0, 76, 8, 'job', String(s.starred))}
              <div class="legend">
                <div class="legend-item"><span class="legend-swatch" style="background:var(--c-job)"></span>已收藏<span class="lv">${s.starred}</span></div>
                <div class="legend-item"><span class="legend-swatch" style="background:var(--ok)"></span>已掌握<span class="lv">${s.done}</span></div>
                <div class="legend-item"><span class="legend-swatch" style="background:var(--accent)"></span>学习中<span class="lv">${s.reading}</span></div>
                <div class="legend-item"><span class="legend-swatch" style="background:var(--bg-4)"></span>未读<span class="lv">${s.total - s.done - s.reading}</span></div>
              </div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-database')} 来源分布</div></div>
          <div class="panel-body flush">
            <div class="mini-list">
              ${bySrc.map(([ch, n]) => `<div class="mini-item">
                <span class="dot"></span><span class="t">${esc(channelMeta(ch).zh)}</span>
                <span class="n">${n} · ${Math.round((n / Math.max(1, state.items.length)) * 100)}%</span></div>`).join('')}
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-activity')} 热度日历</div></div>
          <div class="panel-body">
            <div class="heat">
              ${Array.from({ length: 91 }).map((_, i) => {
                const d = new Date(Date.now() - (90 - i) * 86400000);
                const k = dateKey(d);
                const n = (days.find((x) => x.day === k) || { items: [] }).items.length;
                const lv = n === 0 ? 0 : n < 5 ? 1 : n < 12 ? 2 : n < 25 ? 3 : 4;
                return `<span class="heat-cell" data-lv="${lv}" data-tip="${attr(k)} · ${n} 条"></span>`;
              }).join('')}
            </div>
            <div class="row" style="margin-top:var(--sp-3);justify-content:space-between;font-size:var(--fs-3xs);color:var(--fg-3)">
              <span>90 天前</span><span class="row" style="gap:3px">少
                <span class="heat-cell" data-lv="0"></span><span class="heat-cell" data-lv="1"></span>
                <span class="heat-cell" data-lv="2"></span><span class="heat-cell" data-lv="3"></span>
                <span class="heat-cell" data-lv="4"></span> 多</span><span>今天</span>
            </div>
          </div>
        </div>
      </div>
    </div>`;
  },
  after() {},
};

/* ============================== STARRED ================================ */

export const StarredView = {
  title: '收藏夹',
  render() {
    state.filters.starredOnly = true;
    const list = filteredItems();
    const notes = Object.entries(state.user.notes || {}).filter(([, v]) => v && v.trim());
    return `
    <div class="section-head"><div><h2 class="section-title">收藏夹</h2>
      <p class="section-desc">${list.length} 条已收藏内容 · 适合面试前集中复习。</p></div>
      <div class="section-actions">
        <button class="btn btn-sm btn-ghost" data-act="print">${icon('i-download')} 打印复习清单</button>
      </div></div>
    ${renderCards(list, { all: true })}
    ${notes.length ? `<div class="rule"></div>
      <div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-list')} 我的笔记</div></div>
      <div class="panel-body flush"><div class="mini-list">
        ${notes.map(([id, v]) => {
          const it = state.byId.get(id);
          return `<div class="mini-item" style="align-items:flex-start">
            <span class="dot"></span>
            <span class="t">${it ? `<b style="color:var(--fg-0)">${esc(it.title)}</b><br>` : ''}<span class="text-2">${esc(v)}</span></span>
            ${it ? `<button class="icon-btn" data-act="open-item" data-id="${attr(id)}">${icon('i-chevron')}</button>` : ''}
          </div>`;
        }).join('')}
      </div></div></div>` : ''}`;
  },
  after() { wireItemKeyboard(); },
};

/* ============================== PIPELINE =============================== */

/* ======================= REDUNDANCY PANEL =============================== */
/**
 * Renders the optional redundancy audit (web/data/redundancy-report.json, written
 * by scripts/analyze_redundancy.py on every daily run).
 *
 * WHY it is surfaced in the UI: redundancy is a slow, silent failure. Nothing errors
 * when the corpus fills with the same thing reported repeatedly or with items that
 * matched no tracked direction - the workbench just gets less useful. Showing the
 * numbers next to channel health makes that drift visible instead of something you
 * discover months later.
 *
 * Degrades to nothing when the report is absent (fresh clone, or a run that predates
 * this feature) rather than showing an empty shell.
 */
function redundancyPanel() {
  const r = state.redundancy;
  if (!r || !r.l0) return '';

  const l0 = r.l0 || {};
  const l3 = r.l3_lowInformation || {};
  const work = Array.isArray(r.worklist) ? r.worklist : [];
  const high = work.filter((a) => a.severity === 'high').length;
  const ent = (r.l1_repeatedEntities || []).slice(0, 5);
  const sat = (r.l2_saturation || []).filter((s) => s.share >= 0.25).slice(0, 4);
  const unclShare = Number(l3.unclassifiedShare || 0);

  const stat = (label, value, tone) => `
    <div class="stat-mini">
      <div class="stat-mini-v ${tone || ''}">${esc(String(value))}</div>
      <div class="stat-mini-l">${esc(label)}</div>
    </div>`;

  return `
  <div class="panel">
    <div class="panel-head"><div class="panel-title">${icon('i-chart')} 知识卡片去冗余体检</div>
      <span class="badge ${high ? 'badge-warn' : 'badge-ok'}" style="margin-left:auto">
        ${high ? `${high} 项待处理` : '指标正常'}</span></div>
    <div class="panel-body">
      <div class="prose" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
        <p>采集器的四层去重只处理「同一条内容」，处理不了「同一件事被反复收录」和「命中不了任何方向的条目」。
        这一栏是每日运行时的去冗余体检：先看硬重复，再看实体重复、话题饱和、未分类占比。</p>
      </div>

      <div class="grid grid-4" style="gap:var(--sp-3);margin-bottom:var(--sp-4)">
        ${stat('重复 id / 共用 URL', `${l0.duplicateIds || 0} / ${l0.duplicateUrls || 0}`,
               (l0.duplicateIds || l0.duplicateUrls) ? 'is-warn' : '')}
        ${stat('未分类占比', `${(unclShare * 100).toFixed(1)}%`,
               unclShare >= 0.15 ? 'is-warn' : '')}
        ${stat('低于相关度门槛', l3.belowGate || 0)}
        ${stat('摘要 <60 字', l3.shortSummary || 0)}
      </div>

      ${ent.length ? `
      <div class="eyebrow">同一实体反复收录（top ${ent.length}）</div>
      <ul class="kcard-points" data-cat="agent" style="margin-bottom:var(--sp-3)">
        ${ent.map((e) => `<li><span><b>${esc(e.token)}</b> × ${e.items}
          <span class="text-3">${esc(Object.keys(e.categories || {}).join(' / '))}</span></span></li>`).join('')}
      </ul>` : ''}

      ${sat.length ? `
      <div class="eyebrow">话题饱和（分类内某一实词占比 ≥25%）</div>
      <ul class="kcard-points" data-cat="generative" style="margin-bottom:var(--sp-3)">
        ${sat.map((s) => `<li><span>${esc(s.category)} 的 <b>${esc(s.topToken)}</b>
          占 ${(s.share * 100).toFixed(0)}%（${s.count}/${s.items}）</span></li>`).join('')}
      </ul>` : ''}

      <div class="eyebrow">工单</div>
      <ul class="kcard-points" data-cat="posttraining" style="margin-bottom:var(--sp-3)">
        ${work.slice(0, 6).map((a) => `<li><span><b>[${esc(a.kind)}]</b> ${esc(a.text)}</span></li>`).join('')}
      </ul>

      <div class="text-3" style="font-size:var(--fs-3xs)">
        体检时间 ${esc(String(r.generatedAt || '—'))} · 语料 ${esc(String(r.corpus || '—'))} 条 ·
        命令 <code>python scripts/analyze_redundancy.py</code>（只报告；下架需显式
        <code>python scripts/prune_items.py --apply</code>）
      </div>
    </div>
  </div>`;
}

export const PipelineView = {
  title: '采集与运行',
  render() {
    const runs = state.runs || [];
    const m = state.manifest || {};
    const reg = state.sourceRegistry;
    const channels = (reg && reg.channels) || [];
    const okCh = channels.filter((c) => c.status === 'ok' || c.reachable).length;
    return `
    <div class="section-head">
      <div><h2 class="section-title">采集与运行</h2>
      <p class="section-desc">每日 18:00 (Asia/Shanghai)触发的联网调研流水线：渠道 → 去重 → 打分 → 归纳 → 自检 → 原子写入。</p></div>
      <div class="section-actions">
        <button class="btn btn-sm btn-ghost" data-act="reload">${icon('i-refresh')} 重新读取</button>
      </div>
    </div>

    <div class="grid grid-4" style="margin-bottom:var(--sp-6)">
      <div class="card card-pad"><div class="eyebrow">最近运行</div>
        <div class="stat-val" style="font-size:var(--fs-lg);margin-top:6px">${esc(m.lastRunAt ? relTime(m.lastRunAt) : '尚未运行')}</div>
        <div class="text-3" style="font-size:var(--fs-3xs)">${esc(m.lastRunAt ? fmtDate(m.lastRunAt, 'datetime') : '等待第一次采集')}</div></div>
      <div class="card card-pad"><div class="eyebrow">渠道成功率</div>
        <div class="stat-val" style="font-size:var(--fs-lg);margin-top:6px">${m.channelsOk != null ? `${m.channelsOk}/${m.channelsTotal}` : channels.length ? `${okCh}/${channels.length}` : '—'}</div>
        <div class="text-3" style="font-size:var(--fs-3xs)">失败渠道自动降级到备用源</div></div>
      <div class="card card-pad"><div class="eyebrow">累计入库</div>
        <div class="stat-val" style="font-size:var(--fs-lg);margin-top:6px">${state.items.length}</div>
        <div class="text-3" style="font-size:var(--fs-3xs)">去重后知识卡片</div></div>
      <div class="card card-pad"><div class="eyebrow">运行次数</div>
        <div class="stat-val" style="font-size:var(--fs-lg);margin-top:6px">${runs.length}</div>
        <div class="text-3" style="font-size:var(--fs-3xs)">保留最近 90 次记录</div></div>
    </div>

    <div class="grid grid-dash">
      <div class="col" style="gap:var(--sp-5)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-activity')} 运行历史</div>
            <span class="result-line" style="margin-left:auto">
              定时任务每天 18:00 一次；标记为「手动」的是调试运行
            </span></div>
          <div class="panel-body flush">
            ${(() => {
              // Tell the reader WHICH runs came from the 18:00 schedule. Without
              // this the history looks alarming: a debugging afternoon shows a
              // dozen runs and reads like the schedule is firing repeatedly.
              const scheduled = runs.filter((r) => r.trigger === 'scheduled').length;
              return runs.length ? `
              <div style="padding:var(--sp-3) var(--sp-4);border-bottom:1px solid var(--line-0)">
                <div class="quality-legend">
                  <span><i class="q-dot" style="background:var(--ok)"></i>定时触发 ${scheduled} 次</span>
                  <span><i class="q-dot" style="background:var(--fg-3)"></i>手动 / 调试 ${runs.length - scheduled} 次</span>
                  <span class="text-3">共记录 ${runs.length} 次（保留最近 120 条）</span>
                </div>
              </div>` : '';
            })()}
            ${runs.length ? `<div class="tbl-wrap" style="border:none"><table class="tbl">
              <thead><tr><th>时间</th><th>触发</th><th>状态</th><th class="num">新增</th><th class="num">渠道</th><th class="num">耗时</th><th>备注</th></tr></thead>
              <tbody>
                ${runs.slice(0, 25).map((r) => {
                  const trig = r.trigger || 'manual';
                  const trigCls = trig === 'scheduled' ? 'badge-ok' : trig === 'debug' ? 'badge-mute' : 'badge-info';
                  const trigZh = { scheduled: '定时', manual: '手动', debug: '调试' }[trig] || trig;
                  const scope = r.narrowRun ? ' · 部分渠道' : '';
                  return `<tr>
                  <td>${esc(fmtDate(r.startedAt || r.at, 'datetime'))}</td>
                  <td><span class="badge ${trigCls}" data-tip="${trig === 'scheduled' ? '由任务计划程序在 18:00 触发' : '人为执行（调试或补跑）'}">${esc(trigZh)}</span>${scope ? `<div class="text-3" style="font-size:var(--fs-3xs)">${esc(scope.trim())}</div>` : ''}</td>
                  <td><span class="badge ${r.status === 'ok' ? 'badge-ok' : r.status === 'partial' ? 'badge-warn' : 'badge-err'}">${esc(r.status || '—')}</span></td>
                  <td class="num">${r.newItems != null ? r.newItems : '—'}</td>
                  <td class="num">${r.channelsOk != null ? `${r.channelsOk}/${r.channelsTotal}` : '—'}</td>
                  <td class="num">${r.durationSec != null ? r.durationSec + 's' : '—'}</td>
                  <td class="text-2">${esc((r.notes || '').slice(0, 90))}</td>
                </tr>`;
                }).join('')}
              </tbody></table></div>`
              : emptyState('还没有运行记录', '每次采集都会向 data/logs/runs.json 追加一条运行日志。', 'i-activity')}
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-database')} 渠道清单与策略</div>
            <span class="result-line" style="margin-left:auto">
              ${channels.length} 个已登记${reg && reg.channelsRanCount != null ? ` · 本轮跑 ${reg.channelsRanCount} 个` : ''}
            </span></div>
          <div class="panel-body flush">
            ${channels.length ? `<div class="tbl-wrap" style="border:none"><table class="tbl">
              <thead><tr><th>渠道</th><th>模式</th><th>认证</th><th>频率限制</th><th>本轮</th></tr></thead>
              <tbody>
                ${channels.map((c) => {
                  const st = String(c.status || 'unknown');
                  const cls = st === 'ok' ? 'badge-ok'
                    : st === 'blocked' ? 'badge-err'
                    : st === 'unknown' ? 'badge-mute' : 'badge-warn';
                  const backupNote = c.backupUsed
                    ? `<div class="text-3" style="font-size:var(--fs-3xs)">备用源 ${esc(c.backupUsed)} 生效</div>`
                    : (Array.isArray(c.backupAttempts) && c.backupAttempts.some((a) => a.result !== 'ok')
                      ? `<div class="text-3" style="font-size:var(--fs-3xs)">备用源未取得数据</div>` : '');
                  const staleNote = c.notRunThisPass
                    ? `<div class="text-3" style="font-size:var(--fs-3xs)">本轮未运行${c.staleSince ? ' · ' + esc(String(c.staleSince).slice(0, 10)) : ''}</div>`
                    : '';
                  return `<tr>
                  <td><span style="font-weight:600;color:var(--fg-0)">${esc(c.nameZh || c.name || c.id)}</span>
                    <div class="text-3" style="font-size:var(--fs-3xs)">${esc(c.id || '')}${c.tier ? ' · ' + esc(c.tier) : ''}</div>
                    ${backupNote}${staleNote}</td>
                  <td><span class="tag">${esc(c.recommendedMode || c.mode || '—')}</span></td>
                  <td>${c.authRequired ? '<span class="badge badge-warn">需登录</span>' : '<span class="badge badge-mute">公开</span>'}</td>
                  <td class="text-2">${esc(String(c.rateLimit || '—').slice(0, 40))}</td>
                  <td><span class="badge ${cls}">${esc(st)}</span>
                    ${c.count != null ? `<div class="text-3" style="font-size:var(--fs-3xs)">${esc(String(c.count))} 条</div>` : ''}</td>
                </tr>`;
                }).join('')}
              </tbody></table></div>`
              : emptyState('渠道注册表尚未生成', '运行采集器或把 source_registry.json 复制到 web/data/sources.json。', 'i-database')}
          </div>
        </div>

        ${(() => {
          const proposals = state.proposals || null;
          const q = proposals && Array.isArray(proposals.humanReviewQueue) ? proposals.humanReviewQueue : [];
          const health = proposals && Array.isArray(proposals.channelHealth) ? proposals.channelHealth : [];
          const esc_ = health.filter((h) => h.escalate);
          return `<div class="panel">
            <div class="panel-head"><div class="panel-title">${icon('i-flask')} 自我迭代提案</div>
              <span class="result-line" style="margin-left:auto">${proposals ? esc(String(proposals.date || '')) : '尚未生成'}</span></div>
            <div class="panel-body">
              ${proposals ? `
                <div class="text-2" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
                  由采集器确定性生成（不依赖模型），只做<strong>建议</strong>；分类增删、渠道升降级、评分权重、去重阈值一律需要人工确认后才生效。</div>
                ${esc_.length ? `<div class="eyebrow" style="margin-bottom:6px">需升级处理的渠道</div>
                  <ul class="kcard-points" style="margin-bottom:var(--sp-3)">
                    ${esc_.slice(0, 6).map((h) => `<li><span>${esc(h.id)} · ${esc(h.status)} × ${esc(String(h.streak))} — ${esc(h.suggestedAction || '')}</span></li>`).join('')}
                  </ul>` : ''}
                ${q.length ? `<div class="eyebrow" style="margin-bottom:6px">人工复核队列（${q.length}）</div>
                  <ul class="kcard-points" data-cat="posttraining">
                    ${q.map((line) => `<li><span>${esc(line)}</span></li>`).join('')}
                  </ul>` : '<div class="status-line"><span class="ok">本轮无需人工介入</span></div>'}
              ` : emptyState('还没有提案文件', '采集器每轮都会写 web/data/proposals/YYYY-MM-DD.json。', 'i-flask')}
            </div>
          </div>`;
        })()}
      </div>

      <div class="col" style="gap:var(--sp-5)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-clock')} 定时任务</div></div>
          <div class="panel-body">
            <dl class="kv">
              <dt>计划时间</dt><dd>每日 18:00</dd>
              <dt>时区</dt><dd>Asia/Shanghai (UTC+8)</dd>
              <dt>触发方式</dt><dd>Windows 任务计划程序</dd>
              <dt>入口脚本</dt><dd class="mono" style="font-size:var(--fs-3xs)">scripts/run-daily.ps1</dd>
              <dt>日志目录</dt><dd class="mono" style="font-size:var(--fs-3xs)">data/logs/</dd>
            </dl>
            <div class="kcard-why" style="margin-top:var(--sp-4)">
              <b>手动运行 · </b>在项目根目录执行
              <code style="display:block;margin-top:6px;font-size:var(--fs-3xs)">powershell -ExecutionPolicy Bypass -File scripts/run-daily.ps1</code>
              <button class="btn btn-sm" style="margin-top:var(--sp-3)" data-act="copy" data-copy="powershell -ExecutionPolicy Bypass -File scripts/run-daily.ps1" data-copy-msg="命令已复制">
                ${icon('i-copy')} 复制命令</button>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-shield')} 真实性与准确性自查</div></div>
          <div class="panel-body">
            <div class="prose" style="font-size:var(--fs-2xs)">
              <ul>
                <li>每条卡片必须带<strong>可访问的来源链接</strong>，无链接的内容直接丢弃。</li>
                <li>摘要只允许来自原文（标题/摘要/README），<strong>禁止推断未出现的事实</strong>。</li>
                <li>数字类信息（薪资、star 数、录用率）标记 <code>confidence</code>，低可信度在界面上显式标注。</li>
                <li>自动生成内容与人工内容分区展示，来源渠道逐一列出。</li>
                <li>每日自检：链接可达性抽检、重复率、空摘要率、分类覆盖率、<strong>去冗余体检</strong>，异常写入运行日志。</li>
              </ul>
            </div>
          </div>
        </div>

        ${redundancyPanel()}

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-flask')} 自我迭代机制</div>
            ${state.proposals ? `<span class="badge ${((state.proposals.humanReviewQueue || []).length) ? 'badge-warn' : 'badge-ok'}" style="margin-left:auto">
              待复核 ${((state.proposals.humanReviewQueue || []).length)}</span>` : ''}</div>
          <div class="panel-body">
            <div class="prose" style="font-size:var(--fs-2xs)">
              <ul>
                <li><strong>observe</strong>：每轮记录渠道状态、命中关键词、分类覆盖率与重复率。</li>
                <li><strong>propose</strong>：采集器<strong>确定性地</strong>写 <code>proposals/YYYY-MM-DD.json</code>
                  （不依赖模型，所以即使 Agent 层没凭据也会产出）。</li>
                <li><strong>review</strong>：提案进入「自我迭代提案」面板的人工复核队列。</li>
                <li><strong>apply</strong>：只有「单关键词权重 ≤10% 的微调」可自动生效；分类增删、渠道升降级、
                  评分权重、去重阈值、blocklist 一律需人工确认。</li>
                <li><strong>measure</strong>：下一轮对比相关度分布、分类覆盖率与失败渠道数。</li>
              </ul>
            </div>
            ${state.proposals && Array.isArray(state.proposals.keywordProposals) && state.proposals.keywordProposals.length
              ? `<div class="eyebrow" style="margin-top:var(--sp-3);margin-bottom:4px">关键词精简建议</div>
                 <div class="row" style="flex-wrap:wrap;gap:4px">
                   ${state.proposals.keywordProposals.slice(0, 6).map((k) => `<span class="tag" data-cat="${esc(k.category)}">${esc((CAT_BY_ID[k.category] || {}).zh || k.category)} · 待精简 ${esc(String((k.remove || []).length))}</span>`).join('')}
                 </div>` : ''}
            ${state.proposals
              ? `<div class="row" style="margin-top:var(--sp-3)">
                   <button class="btn btn-sm" data-act="reload">${icon('i-refresh')} 重新读取提案</button>
                   <a class="btn btn-sm btn-ghost" href="data/proposals/latest.json" target="_blank" rel="noopener">${icon('i-external')} 查看原始提案</a>
                 </div>`
              : `<button class="btn btn-sm" style="width:100%;margin-top:var(--sp-3)" data-act="reload">提案文件尚未生成，重新读取</button>`}
          </div>
        </div>
      </div>
    </div>`;
  },
  after() {},
};

/* ============================ DETAIL DRAWER ============================ */

export function openItem(id) {
  const it = state.byId.get(id);
  if (!it) return;
  const st = statusOf(it.id);
  const starred = Boolean(state.user.starred[it.id]);
  const dt = it.publishedAt || it.fetchedAt;

  /* Heavy HTML is built from pre-flattened string fragments. Keeping every
     template literal single-level makes this function trivially verifiable and
     avoids the deep nesting that caused a parser-level mistake here before. */
  const parts = [];

  /* Layer-2 (agent) enrichment, when it exists for this item. This is the
     "抽象概念易读化" payload: a one-line conclusion, then each abstract concept
     explained plainly with an analogy, a visualisation recipe and its failure
     boundary. Shown first because it is the most useful thing on the page. */
  if (it.enriched) {
    if (it.tldr) {
      parts.push('<div class="kcard-why" style="margin-bottom:var(--sp-4)"><b>一句话结论 · </b>'
        + esc(it.tldr) + '</div>');
    }
    if (it.diagram) {
      const dg = diagramHtml(it.diagram);
      if (dg) parts.push(dg);
    }
    /* Teaching + concept payloads render through the shared builders defined
       above, so the item drawer and the 题库解析页 cannot drift apart. */
    const teach = teachingHtml(it.teaching);
    if (teach) parts.push(teach);
    const concepts = conceptsHtml(it.concepts);
    if (concepts) parts.push(concepts);
    if (it.selfCheck && ((it.selfCheck.uncertain || []).length || (it.selfCheck.claims || []).length)) {
      const sc = [];
      if ((it.selfCheck.claims || []).length) {
        sc.push('<div class="eyebrow">可核实的断言</div><ul class="kcard-points" data-cat="agent">'
          + it.selfCheck.claims.map((c) => '<li><span>' + esc(c) + '</span></li>').join('') + '</ul>');
      }
      if ((it.selfCheck.uncertain || []).length) {
        sc.push('<div class="eyebrow" style="margin-top:var(--sp-3)">待人工核实</div><ul class="kcard-points" data-cat="posttraining">'
          + it.selfCheck.uncertain.map((c) => '<li><span>' + esc(c) + '</span></li>').join('') + '</ul>');
      }
      parts.push('<div class="prose"><h2>深度层的自检</h2>' + sc.join('') + '</div>');
    }
  } else {
    /* Not yet deep-read. Say so honestly instead of pretending the summary is an
       analysis, and tell the reader where the analysis will come from. */
    const queued = state.deepReadPlan && Array.isArray(state.deepReadPlan.queue)
      && state.deepReadPlan.queue.some((q) => q.id === it.id);
    parts.push('<div class="kcard-why" style="margin-bottom:var(--sp-4);border-left-color:var(--warn)">'
      + '<b>这张卡片还没有深度解析 · </b>'
      + (queued
        ? '它已在深度解析队列里（配额按分类分配，每个方向每天 2–10 条），下一轮运行时会补上：一句话结论、概念易读化、生活类比、图解与自测题。'
        : '当前显示的是采集层的原文摘要与来源链接。你可以在「采集与运行」页看到深度解析的进度与配额。')
      + '</div>');
  }

  if (it.why) {
    parts.push('<div class="kcard-why" style="margin-bottom:var(--sp-4)"><b>为什么重要 · </b>'
      + esc(it.why) + '</div>');
  }

  if (it.summary) {
    parts.push('<div class="prose"><h2>摘要</h2><p>' + esc(it.summary) + '</p></div>');
  }

  if (it.keyPoints.length) {
    const lis = it.keyPoints.map((k) => '<li>' + esc(k) + '</li>').join('');
    parts.push('<div class="prose"><h2>关键要点</h2><ul>' + lis + '</ul></div>');
  }

  if (it.details) {
    parts.push('<div class="prose"><h2>深入解析</h2>' + md(it.details) + '</div>');
  }

  if (it.formulas && it.formulas.length) {
    const cards = it.formulas
      .map((f) => formulaDetailHtml(normalizeFormula(f, 0)))
      .join('');
    parts.push('<div class="prose"><h2>相关公式</h2></div><div class="col" style="gap:var(--sp-3)">'
      + cards + '</div>');
  }

  if (it.examples && it.examples.length) {
    const blocks = it.examples.map((ex) => {
      if (typeof ex === 'string') return '<p>' + esc(ex) + '</p>';
      const head = '<h3>' + esc(ex.title || '示例') + '</h3>';
      const body = ex.body ? '<p>' + esc(ex.body) + '</p>' : '';
      const code = ex.code
        ? '<div class="code-wrap"><div class="code-head"><span>'
          + esc(ex.lang || 'code') + '</span></div><pre class="code">'
          + highlight(ex.code, ex.lang || 'python') + '</pre></div>'
        : '';
      return head + body + code;
    }).join('');
    parts.push('<div class="prose"><h2>实例讲解</h2>' + blocks + '</div>');
  }

  if (it.tags.length || it.entities.length) {
    const tagChips = it.tags
      .map((t) => '<button class="chip" data-act="toggle-tag" data-tag="' + attr(t) + '">' + esc(t) + '</button>')
      .join('');
    const entityTags = it.entities.map((t) => '<span class="tag">' + esc(t) + '</span>').join('');
    parts.push('<div class="prose"><h2>标签与实体</h2><div class="row" style="flex-wrap:wrap;gap:6px">'
      + tagChips + entityTags + '</div></div>');
  }

  const noteValue = (state.user.notes || {})[it.id] || '';
  parts.push(
    '<div class="prose"><h2>我的笔记</h2>'
    + '<textarea data-note-for="' + attr(it.id) + '" rows="4" '
    + 'placeholder="写下你的理解、疑问、可复用片段…" '
    + 'style="width:100%;padding:var(--sp-3);border:1px solid var(--line-1);'
    + 'border-radius:var(--r-md);background:var(--bg-2);color:var(--fg-0);'
    + 'font-size:var(--fs-xs);resize:vertical">' + esc(noteValue) + '</textarea>'
    + '<div class="text-3" style="font-size:var(--fs-3xs);margin-top:4px">'
    + '自动保存到本地（localStorage）。</div></div>'
  );

  if (it.sources.length) {
    const lis = it.sources.map((s) => {
      const url = safeUrl(s.url || s);
      const label = s.title || hostOf(s.url || s) || String(s);
      const origin = s.name ? '<span class="text-3"> · ' + esc(s.name) + '</span>' : '';
      return '<li><a href="' + attr(url) + '" target="_blank" rel="noopener noreferrer">'
        + esc(label) + '</a>' + origin + '</li>';
    }).join('');
    parts.push('<div class="prose"><h2>来源与溯源</h2><ul>' + lis + '</ul></div>');
  }

  const metaJson = JSON.stringify({
    id: it.id, channel: it.channel, category: it.category, lang: it.lang,
    publishedAt: it.publishedAt, fetchedAt: it.fetchedAt,
    relevanceScore: it.relevance, relevanceBreakdown: it.relevanceBreakdown,
    qualitySignals: it.quality, difficulty: it.difficulty,
    venue: it.venue, ccf: it.ccf, contentHash: it.contentHash,
  }, null, 2);
  parts.push('<details style="margin-top:var(--sp-4)">'
    + '<summary style="cursor:pointer;font-size:var(--fs-2xs);color:var(--fg-2)">'
    + '采集元数据（用于准确性与溯源自查）</summary>'
    + '<pre class="code" style="margin-top:var(--sp-3);border:1px solid var(--line-0);'
    + 'border-radius:var(--r-md)">' + esc(metaJson) + '</pre></details>');

  const eyebrow = (CAT_BY_ID[it.category] || {}).zh || '知识';
  const metaChips = [
    catPill(it.category),
    it.difficulty ? '<span class="badge badge-mute">' + esc(DIFF_ZH[it.difficulty] || it.difficulty) + '</span>' : '',
    it.ccf ? '<span class="badge badge-info">CCF-' + esc(it.ccf) + '</span>' : '',
    dt ? '<span class="text-3" style="font-size:var(--fs-3xs)">'
      + esc(fmtDate(dt, 'datetime')) + ' · ' + esc(relTime(dt)) + '</span>' : '',
    it.authors.length ? '<span class="text-3" style="font-size:var(--fs-3xs)">'
      + esc(it.authors.slice(0, 4).join(', ')) + (it.authors.length > 4 ? ' 等' : '') + '</span>' : '',
  ].filter(Boolean).join('');

  const titleHtml = esc(it.title)
    + (it.titleZh
      ? '<div class="text-2" style="font-size:var(--fs-sm);font-weight:500;margin-top:4px">'
        + esc(it.titleZh) + '</div>'
      : '');

  const footParts = [
    it.url
      ? '<a class="btn btn-sm btn-primary" href="' + attr(it.url) + '" target="_blank" '
        + 'rel="noopener noreferrer">' + icon('i-external') + ' 打开原文</a>'
      : '',
    '<button class="btn btn-sm' + (starred ? ' is-on' : '') + '" data-act="star" data-id="'
      + attr(it.id) + '">' + icon('i-star') + (starred ? ' 已收藏' : ' 收藏') + '</button>',
    '<button class="btn btn-sm' + (st === 'reading' ? ' is-on' : '') + '" data-act="status" data-id="'
      + attr(it.id) + '" data-status="reading">' + icon('i-clock') + ' 学习中</button>',
    '<button class="btn btn-sm' + (st === 'done' ? ' is-on' : '') + '" data-act="status" data-id="'
      + attr(it.id) + '" data-status="done">' + icon('i-check') + ' 已掌握</button>',
    '<button class="btn btn-sm btn-ghost" data-act="copy" data-copy="'
      + attr(it.canonicalUrl || it.url || it.title) + '" data-copy-msg="链接已复制">'
      + icon('i-link') + ' 复制链接</button>',
  ].filter(Boolean).join('');

  openDrawer({
    eyebrow: eyebrow + ' · ' + channelMeta(it.channel).zh,
    title: titleHtml,
    cat: it.category,
    meta: metaChips,
    body: parts.join(''),
    foot: footParts,
  });
  $('#drawer').dataset.itemId = it.id;
}

export function openJob(id) {
  const j = state.jobs.find((x) => x.id === id);
  if (!j) return;
  openDrawer({
    eyebrow: '岗位详情',
    title: `${esc(j.company)} · ${esc(j.title)}`,
    cat: 'job',
    meta: `<span class="tier" data-tier="${attr(j.tier)}">${esc(j.tier)}</span>
      <span class="badge ${j.open ? 'badge-ok' : 'badge-mute'}">${j.open ? '开放中' : '已关闭'}</span>
      <span class="text-3" style="font-size:var(--fs-3xs)">${esc(j.cities.join(' / ') || '城市待定')} · ${esc(j.pay || '面议')}</span>`,
    body: `<div class="prose">${jobDetailHtml(j).replace(/^[\s\S]*?<div class="grid grid-dash">/, '<div class="grid grid-dash">')}</div>`,
    foot: `${j.applyUrl ? `<a class="btn btn-sm btn-primary" href="${attr(j.applyUrl)}" target="_blank" rel="noopener noreferrer">${icon('i-external')} 投递</a>` : ''}
      <button class="btn btn-sm btn-ghost" data-act="nav" data-hash="#/jobs?focus=${encodeURIComponent(j.id)}">${icon('i-chevron')} 在看板中打开</button>`,
  });
}

/* ================================= BOOT ================================ */

export function boot() {
  loadUser();
  applyPrefs();

  VIEWS.dashboard = DashboardView;
  VIEWS.digest = DigestView;
  VIEWS.categories = CategoriesView;
  VIEWS.knowledge = KnowledgeView;
  VIEWS.formulas = FormulasView;
  VIEWS.problems = ProblemsView;
  VIEWS.repos = ReposView;
  VIEWS.jobs = JobsView;
  VIEWS.skills = SkillsView;
  VIEWS.roadmap = RoadmapView;
  VIEWS.progress = ProgressView;
  VIEWS.starred = StarredView;
  VIEWS.pipeline = PipelineView;

  installShell();
  installKeyboard();

  Store.boot().then(() => {
    if (!location.hash) history.replaceState(null, '', '#/dashboard');
    render();
    if (state.loadErrors.length) {
      toast(`${state.loadErrors.length} 个数据文件未找到，界面使用降级数据`, 'warn', 5200);
    } else {
      toast(`数据层已就绪：${state.items.length} 条知识 · ${state.jobs.length} 个岗位`, 'ok', 2600);
    }
    // 非阻塞：核对浏览器里跑的是不是最新发布的脚本（见 ui.part.js 的说明）。
    // 放在 render() 之后并且不 await —— 一次自检失败绝不能拖慢或挡住首屏。
    checkForNewBuild();
  }).catch((err) => {
    $('#view').innerHTML = emptyState('数据层加载失败', String(err && err.message || err), 'i-alert',
      `<button class="btn btn-sm" data-act="reload">重试</button>`);
  });
}
