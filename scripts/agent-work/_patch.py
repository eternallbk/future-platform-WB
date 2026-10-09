# -*- coding: utf-8 -*-
import json, os
OUT = r"D:/pythonProject/WB-daily/DS-daily/scripts/agent-work/parts/queue-06"

def load(k): return json.load(open(os.path.join(OUT,k+".json"),encoding="utf-8"))
def save(k,d):
    s=json.dumps(d,ensure_ascii=False,separators=(",",":"))
    open(os.path.join(OUT,k+".json"),"w",encoding="utf-8").write(s)
    return len(s.encode("utf-8"))

# ---- 02 ICDP ----
d=load("02"); t=d["teaching"]
t["progressive"][1]["text"]="离线 RL 只能用已有数据学，策略会挑数据没充分支持的动作。自驾里一条自车轨迹单独看数据里有，却可能和当时周围车的行为凑成从没出现过的组合，叫交互分布偏移。"
t["progressive"][3]["text"]="相比只在策略动作空间约束，ICDP 把约束提到交互级，能压掉高价值但交互上不被支持的轨迹，并用密度比估计省掉联合密度建模与在线 rollout。摘要称在 nuPlan、InterPlan 与真实卡车实验的交互关键场景更好。"
t["mechanism"]="分布偏移的本质是策略倾向数据不支持的动作，但自驾的动作与环境耦合：自车轨迹的合法性取决于周围车的同时行为。只约束边缘自车分布会漏掉联合不支持的组合，故必须显式建模交互层支持；用密度比估计而非联合密度，以免需在线 rollout。"
t["ownAnalysis"]="把支持度从动作空间提升到交互级，与多智能体后训练、世界模型 rollout 同构（推断）：价值估计不可靠常源于耦合而非单个行为罕见。可疑处：摘要说分解「精确」，但连续动作空间下如何保持未给细节，需核对原文。"
t["interviewAnswer"]="离线 RL 从固定数据学，核心难题是分布偏移。以往方法只在策略自己的动作空间约束，但自驾这种交互环境里不够：一条自车轨迹可能边缘支持很好，却和当时周围车的行为联合不被支持，我称之为交互分布偏移。做法是从联合分布出发把支持退化拆成自车支持项与残差交互支持项，后者用对比密度比估计隔离，不需要显式联合密度或反应式 rollout。"
d["concepts"][0]["mechanism"]="从自车与周围车未来的联合分布出发，把联合支持退化精确拆成自车边缘支持与残差交互支持；用对比密度比估计后者，无需显式联合密度、周围车预测或反应式 rollout。"
d["concepts"][0]["visual"]="二维热力图：横轴自车轨迹簇、纵轴周围车行为簇；两轴都有值但联合格为空的格子标红，表示交互不支持。"
d["selfCheck"]["claims"]=d["selfCheck"]["claims"][:5]
d["formulas"][0]["derivation"]=d["formulas"][0]["derivation"][:3]
d["formulas"][0]["pitfalls"]=d["formulas"][0]["pitfalls"][:2]
print("02",save("02",d))

# ---- 03 MiMo ----
d=load("03"); t=d["teaching"]
t["progressive"][3]["text"]="它把 RL 扩算力拆成批量吞吐、环境多样性、grader 计算三条正交轴，并配套混合任务 agentic RL 基建（统一轨迹表示、高并发多框架 rollout、控制面数据面解耦、训推一致）。相比只堆采样量，它强调环境与评分器也要同比例扩展。边界是基建门槛极高，小团队难复现；组内相对信号在组内同质时会退化。"
t["mechanism"]="RL 扩算力的瓶颈不只是采样数量：长程任务上奖励信号本身不准，弱 grader 会把模型推向刷分与冗长回答；环境单一则探索空间受限。报告把环境与 grader 计算与批量同比例扩展，使更多算力转化为更可靠奖励；同时冻结路由、加多层防御，避免规模化下 reward hacking 把收益吃掉。"
t["ownAnalysis"]="「批量 × 环境 × grader」三轴扩展与 GRPO 类组内相对优化一脉相承（推断）：核心是把算力投向更可靠的奖励与更多样探索，而非单纯增加采样。可疑处：报告只强调开源与规模，未给与同类模型的精度对比，需核对原文。"
t["interviewAnswer"]="这份报告的核心观点是 RL 是大模型自我改进的主路径。MiMo-V2.6 先多模态中训练铺探索空间，再从三向扩 RL 算力：更大批量与异步训练，每步一千多样本、上十亿 token；更多样更复杂的环境，覆盖代码、通用、视觉、网络并混合多种 agent harness；更多 grader 计算，用 groupwise 智能体评分给长程任务更准奖励并把模型引向更短省 token 的解。"
d["concepts"][0]["mechanism"]="对同一 prompt 采一组 rollout 交给智能体 grader 相对评分，得到组内相对优势而非绝对奖励；相对打分降低奖励尺度漂移，并配合长度信号把模型推向更短、更省 token 的解。"
d["concepts"][0]["analogyBreaksDown"]="批卷标准固定，而这里 grader 本身可能是模型，会偏爱某类风格；成组比较减少绝对尺度漂移，却可能放大组内同质偏好。"
d["concepts"][0]["visual"]="横轴同一 prompt 的多个 rollout、纵轴相对偏好分；同组内两两比较后归一化成组内优势。"
d["selfCheck"]["claims"]=d["selfCheck"]["claims"][:5]
d["formulas"][0]["pitfalls"]=d["formulas"][0]["pitfalls"][:2]
print("03",save("03",d))

# ---- 04 DAEDALUS ----
d=load("04"); t=d["teaching"]
t["progressive"][1]["text"]="LLM 智能体到新环境常不知工具怎么用，做了也不记事，于是反复犯同样的错。已有做法要么靠人写指南，要么靠训练任务加标准答案验证器。DAEDALUS 不要这些，让 explorer 自己造越来越难的题，solver 去做。"
t["progressive"][3]["text"]="它与人工指南和 oracle 监督路线的差别是完全自举、无需环境先验，代价是记忆质量取决于自生成任务的覆盖与 solver 的判断。摘要称在 AppWorld、tau^2-bench、AutomationBench 上平均成功率升至 15.9 点、pass^5 高 2.2x。边界是探索预算与任务覆盖，分布外环境仍可能缺规则。"
t["mechanism"]="新环境里既没有现成任务也没有标准答案验证器，人写指南又依赖先验。DAEDALUS 把造题与做题解耦到两个智能体：explorer 保证任务可解且难度可调，solver 的失败提供经验来源；再用反复成功这条稳定性判据把经验筛成规则，于是记忆获得不依赖任何外部监督，也把探索成本集中在最需要的难度区间。"
t["ownAnalysis"]="「自生成任务 + 稳定性验收」把课程学习与程序性记忆自举结合得很干净（推断），与 RL 环境自动出题、多模态 agent 经验复用都可对接。可疑处：提升数字都是相对的，缺少与人工指南方法的成本对照；explorer 与 solver 同源时可能形成共同盲点，需核对原文消融。"
t["interviewAnswer"]="LLM 智能体到新环境常缺操作知识，没记忆就反复犯错。以往要么靠人写指南，要么靠训练任务加 oracle 验证器，都需要环境先验。DAEDALUS 不要这些：一个 explorer 自己造有挑战却可解的任务，一个 solver 去解；每次失败抽一条启发式，只有带着它反复成功才被接受进记忆库，这样过滤掉偶然生效的假规律，结果再回去调难度。"
d["concepts"][0]["mechanism"]="explorer 按难度生成可解任务，solver 尝试；每次失败抽一条启发式，只有带着它在上下文里反复成功才被接受，从而过滤掉过拟合单次的假规律；接受结果回馈 explorer 调难度，接受的启发式合并成记忆库。"
d["concepts"][0]["visual"]="横轴任务难度、纵轴 solver 成功率；画 explorer 难度爬升曲线，标注失败点抽启发式、接受点入库，成功率阶梯上升。"
d["selfCheck"]["claims"]=d["selfCheck"]["claims"][:5]
d["formulas"][0]["derivation"]=d["formulas"][0]["derivation"][:3]
d["formulas"][0]["pitfalls"]=d["formulas"][0]["pitfalls"][:2]
print("04",save("04",d))

# ---- 05 LEGO ----
d=load("05"); t=d["teaching"]
d["keyPoints"]=["从单段第三人称视频生成第一人称视频是难的新视角合成，两相机几乎不重叠、目标视角多未观测","SOTA 显式重建：估深度、抬升成点云、从第一人称相机重渲以条件化视频扩散模型","确定性映射把每像素投到单一位置，深度误差会变成内容错位","LEGO 用 LVSM 式 transformer 微调直接渲染，无深度、点云、重投影"]
t["progressive"][1]["text"]="要把一段第三人称视频变成第一人称，两视角几乎不重叠、目标画面大多看不到。以往先估深度、抬成点云、再从第一人称相机重渲染去条件化视频扩散模型，问题是这种映射确定，深度一旦估错像素就投到错位置。"
t["progressive"][2]["text"]="LEGO 换掉这套管线，用一个学过的新视角合成器（LVSM 式 transformer 微调）直接渲染。它的映射是概率式的：一个目标区域按学到的对应分布对多个候选源位置加权平均，结构保住、细纹理被平均掉，恰好适合让扩散模型去补。"
t["progressive"][3]["text"]="它的判断是：给扩散模型的条件应优先结构对齐而非锐度，因为去噪训练本就擅长恢复细节。对应分布的集中度顺带给出逐区域置信度，用来掩掉低置信区并在早期布局阶段引导生成。摘要称它持续优于显式管线，且无需重训即可泛化到其它数据集。"
t["mechanism"]="难点在目标视角大部未观测、两相机几乎不重叠，显式深度抬升会把误差不可逆地固化到像素位置。作者把「条件该给什么」重新定义：条件应提供可靠的结构对齐而非锐利纹理，于是用可学习合成器输出概率式区域平均与置信度，把纹理恢复外包给扩散模型，从源头降低对深度精度的依赖。"
t["ownAnalysis"]="「条件给结构、细节交给扩散」的分工与潜变量/多阶段生成里把粗结构与大细节分层的思路同构（推断），可迁移到世界模型的观测条件设计。可疑处：摘要未给具体指标与数据集名称，也未说明置信度阈值如何选，需核对原文。"
t["interviewAnswer"]="任务是从一段第三人称视频生成第一人称视频，两视角几乎不重叠、目标画面大多没看过。以往估深度、抬成点云、再重投影来条件化扩散模型，但这是确定性映射，深度误差会被固化成像素错位。LEGO 不用 lifting，改用一个微调过的 LVSM 式 transformer 直接渲染目标视角，它的对应是概率分布：对多个候选源位置加权平均，保结构、钝化纹理，正好让扩散补细节。"
d["concepts"][0]["mechanism"]="用 LVSM 式 transformer 把源视角特征直接聚合到目标像素，聚合权重是学到的对应分布，因此是概率映射：一个目标区域按权重平均多个候选源位置，保结构、平滑掉细纹理；集中度顺带给出逐区域置信度，用于掩低置信区并在早期去噪引导布局。"
d["concepts"][0]["visual"]="横轴目标视角像素、纵轴对应源位置权重；确定映射是一根尖峰（one-hot），概率映射是覆盖几处源位置的小山包，越矮平置信度越低。"
d["selfCheck"]["claims"]=d["selfCheck"]["claims"][:5]
d["formulas"][0]["derivation"]=d["formulas"][0]["derivation"][:3]
d["formulas"][0]["pitfalls"]=d["formulas"][0]["pitfalls"][:2]
print("05",save("05",d))
