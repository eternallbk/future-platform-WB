#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_solutions.py — 题库批次 14 道题的参考实现 + 自测。

这不是流水线的一部分：它是「作者工具」。apply_agent_out.py 只吃 out-*.json，
本文件的作用是让 out-problems-01.json 里的每一段代码都**真的跑过**，
而不是写一段看起来对的伪代码。跑完可以删。

约定
  · 每个条目给出 SOL[iid] = {"code": str, "fn": callable, "cases": [...]}；
  · code 会写进 enrichment 的 problem.solution.python，因此必须是完整可运行函数；
  · 用 exec(code) 把 code 求值成函数再来测，保证「写进库里的那段」就是「测过的那段」。
"""
from __future__ import annotations

import json
import sys
from collections import deque

# ---------------------------------------------------------------- 数据结构
LIST_NODE = '''
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next
'''

TREE_NODE = '''
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right
'''


def mk_list(xs):
    head = None
    for v in reversed(xs):
        head = ListNode(v, head)
    return head


def to_list(node):
    out = []
    while node:
        out.append(node.val)
        node = node.next
    return out


def mk_tree(xs):
    if not xs:
        return None
    it = iter(xs)
    root = TreeNode(next(it))
    q = deque([root])
    while q:
        n = q.popleft()
        try:
            v = next(it)
        except StopIteration:
            break
        if v is not None:
            n.left = TreeNode(v)
            q.append(n.left)
        try:
            v = next(it)
        except StopIteration:
            break
        if v is not None:
            n.right = TreeNode(v)
            q.append(n.right)
    return root


class ListNode:                                   # noqa: F811  (runtime class for tests)
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


class TreeNode:                                   # noqa: F811
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


# =================================================================== 1. 快排
QUICK_SORT = '''
def quick_sort(nums):
    """原地快速排序（双指针挖坑 + 随机基准）。"""
    import random

    def partition(lo, hi):
        # 随机选基准并与左端交换：避免「已有序数组」退化成 O(n^2)
        k = random.randint(lo, hi)
        nums[lo], nums[k] = nums[k], nums[lo]
        pivot = nums[lo]
        i, j = lo, hi
        while i < j:
            # 先从右往左找第一个 < pivot 的，填到左边的坑里
            while i < j and nums[j] >= pivot:
                j -= 1
            nums[i] = nums[j]
            # 再从左往右找第一个 > pivot 的，填到右边的坑里
            while i < j and nums[i] <= pivot:
                i += 1
            nums[j] = nums[i]
        nums[i] = pivot
        return i

    def sort(lo, hi):
        if lo >= hi:
            return
        p = partition(lo, hi)
        sort(lo, p - 1)
        sort(p + 1, hi)

    sort(0, len(nums) - 1)
    return nums
'''

QUICK_SORT_ALT = '''
def quick_sort_hoare(nums):
    """另一种写得出彩的版本：Hoare 划分 + 三数取中。面试里说清楚「为什么比 Lomuto 少交换」。"""
    def median3(lo, hi):
        mid = (lo + hi) // 2
        a, b, c = nums[lo], nums[mid], nums[hi]
        if a > b:
            lo, mid = mid, lo
        if nums[lo] > nums[hi]:
            lo, hi = hi, lo
        if nums[mid] > nums[hi]:
            mid, hi = hi, mid
        return nums[mid]

    def partition(lo, hi):
        pivot = median3(lo, hi)
        i, j = lo - 1, hi + 1
        while True:
            i += 1
            while nums[i] < pivot:
                i += 1
            j -= 1
            while nums[j] > pivot:
                j -= 1
            if i >= j:
                return j
            nums[i], nums[j] = nums[j], nums[i]

    def sort(lo, hi):
        if lo >= hi:
            return
        p = partition(lo, hi)
        sort(lo, p)
        sort(p + 1, hi)

    sort(0, len(nums) - 1)
    return nums
'''

# ============================================================ 2. 最长上升子序列
LIS = '''
def length_of_lis(nums):
    """O(n log n)：tails[k] 记录「长度 k+1 的上升子序列的最小结尾」。"""
    import bisect

    tails = []
    for x in nums:
        i = bisect.bisect_left(tails, x)     # 第一个 >= x 的位置
        if i == len(tails):
            tails.append(x)                  # x 比所有结尾都大 → 子序列变长
        else:
            tails[i] = x                     # 否则把该长度的结尾改小（更优）
    return len(tails)
'''

LIS_ALT = '''
def length_of_lis_dp(nums):
    """O(n^2) 定义解：dp[i] = 以 nums[i] 结尾的 LIS 长度。先说这个再优化，面试节奏更稳。"""
    if not nums:
        return 0
    dp = [1] * len(nums)
    for i in range(1, len(nums)):
        for j in range(i):
            if nums[j] < nums[i]:
                dp[i] = max(dp[i], dp[j] + 1)
    return max(dp)
'''

# ======================================================= 3. 合并两个有序链表
MERGE_LISTS = '''
def merge_two_lists(l1, l2):
    """迭代 + 哑结点：把较小的结点接在尾部，最后接上没走完的那条。"""
    dummy = ListNode(0)
    tail = dummy
    while l1 and l2:
        if l1.val <= l2.val:          # <= 保证「稳定」：相等时先取 l1
            tail.next, l1 = l1, l1.next
        else:
            tail.next, l2 = l2, l2.next
        tail = tail.next
    tail.next = l1 if l1 else l2      # 剩余整段直接挂上，O(1)
    return dummy.next
'''

MERGE_LISTS_ALT = '''
def merge_two_lists_rec(l1, l2):
    """递归版：代码短，但递归深度 = 链表长度，长链表有爆栈风险，面试要主动说出来。"""
    if not l1:
        return l2
    if not l2:
        return l1
    if l1.val <= l2.val:
        l1.next = merge_two_lists_rec(l1.next, l2)
        return l1
    l2.next = merge_two_lists_rec(l1, l2.next)
    return l2
'''

# ==================================================== 4. 二叉树的层序遍历
LEVEL_ORDER = '''
def level_order(root):
    """BFS：每轮先记下当前队列长度，那个长度就是「这一层」的结点数。"""
    from collections import deque

    if not root:
        return []
    out, q = [], deque([root])
    while q:
        level = []
        for _ in range(len(q)):        # 关键：循环边界取的是本轮开始时的长度
            node = q.popleft()
            level.append(node.val)
            if node.left:
                q.append(node.left)
            if node.right:
                q.append(node.right)
        out.append(level)
    return out
'''

LEVEL_ORDER_ALT = '''
def level_order_dfs(root):
    """DFS + 深度下标：把「层」当成一次先序遍历的副作用，面试里作为第二种写法很加分。"""
    out = []

    def dfs(node, d):
        if not node:
            return
        if d == len(out):
            out.append([])
        out[d].append(node.val)
        dfs(node.left, d + 1)
        dfs(node.right, d + 1)

    dfs(root, 0)
    return out
'''

# ========================================================== 5. 有效的括号
VALID_PAREN = '''
def is_valid(s):
    """栈 + 字典映射。闭括号来了必须和栈顶配对，否则直接 False。"""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for ch in s:
        if ch in pairs:
            # 栈空（多了一个闭括号）或栈顶不匹配 → 非法
            if not stack or stack.pop() != pairs[ch]:
                return False
        else:
            stack.append(ch)
    return not stack              # 全部配对完栈必须为空
'''

VALID_PAREN_ALT = '''
def is_valid_replace(s):
    """反复消去配对括号：写法极简，但最坏 O(n^2)，只适合说明「别在面试里用它」。"""
    while "()" in s or "[]" in s or "{}" in s:
        s = s.replace("()", "").replace("[]", "").replace("{}", "")
    return s == ""
'''

# ====================================================== 6. 合并两个有序数组
MERGE_ARRAY = '''
def merge_sorted_array(nums1, m, nums2, n):
    """从后往前填：把大的先放到 nums1 末尾，天然不会覆盖还没比较的元素。"""
    i, j, k = m - 1, n - 1, m + n - 1
    while j >= 0:                      # nums2 处理完就结束（nums1 剩下的本来就在原位）
        if i >= 0 and nums1[i] > nums2[j]:
            nums1[k] = nums1[i]
            i -= 1
        else:
            nums1[k] = nums2[j]
            j -= 1
        k -= 1
    return nums1
'''

MERGE_ARRAY_ALT = '''
def merge_sorted_array_front(nums1, m, nums2, n):
    """从前向后 + 临时副本：需要 O(m) 额外空间，用它反衬「从后往前」为什么更优。"""
    a = nums1[:m]
    i = j = 0
    for k in range(m + n):
        if j >= n or (i < m and a[i] <= nums2[j]):
            nums1[k] = a[i]
            i += 1
        else:
            nums1[k] = nums2[j]
            j += 1
    return nums1
'''

# ========================================================= 7. 反转链表 II
REVERSE_II = '''
def reverse_between(head, left, right):
    """哑结点 + 头插法：先把 pre 走到 left 前一个，然后每次把 cur 后面的结点插到 pre 后面。"""
    dummy = ListNode(0, head)
    pre = dummy
    for _ in range(left - 1):
        pre = pre.next
    cur = pre.next
    for _ in range(right - left):
        nxt = cur.next          # 要被挪到前面的结点
        cur.next = nxt.next     # 从原位置摘掉
        nxt.next = pre.next     # 插到 pre 之后（成为这一段新的头）
        pre.next = nxt
    return dummy.next
'''

REVERSE_II_ALT = '''
def reverse_between_splice(head, left, right):
    """切成三段再拼接：思路最直白（断链 → 整体反转 → 接回去），代价是要小心 4 个接点。"""
    dummy = ListNode(0, head)
    pre = dummy
    for _ in range(left - 1):
        pre = pre.next
    left_node = pre.next
    right_node = left_node
    for _ in range(right - left):
        right_node = right_node.next
    tail = right_node.next
    # 反转 [left_node, right_node]
    prev, cur = None, left_node
    while cur is not tail:
        nxt = cur.next
        cur.next = prev
        prev = cur
        cur = nxt
    pre.next = prev
    left_node.next = tail
    return dummy.next
'''

# =========================================================== 8. 重排链表
REORDER_LIST = '''
def reorder_list(head):
    """三步走：快慢指针找中点 → 反转后半段 → 交替合并。空间 O(1)。"""
    if not head or not head.next:
        return head
    # 1) 找中点：slow 停在「前半段最后一个」
    slow, fast = head, head
    while fast.next and fast.next.next:
        slow = slow.next
        fast = fast.next.next
    # 2) 反转后半段
    prev, cur = None, slow.next
    slow.next = None                 # 断开，否则合并时会成环
    while cur:
        nxt = cur.next
        cur.next = prev
        prev = cur
        cur = nxt
    # 3) 交替合并两条链
    l1, l2 = head, prev
    while l2:
        n1, n2 = l1.next, l2.next
        l1.next = l2
        l2.next = n1
        l1, l2 = n1, n2
    return head
'''

REORDER_LIST_ALT = '''
def reorder_list_array(head):
    """结点全装进数组再按 i / n-1-i 重连：3 行核心逻辑，代价是 O(n) 空间。面试可先说这个再优化。"""
    if not head:
        return head
    nodes = []
    cur = head
    while cur:
        nodes.append(cur)
        cur = cur.next
    i, j = 0, len(nodes) - 1
    while i < j:
        nodes[i].next = nodes[j]
        i += 1
        if i == j:
            break
        nodes[j].next = nodes[i]
        j -= 1
    nodes[i].next = None
    return head
'''

# ========================================================= 9. 字符串相加
ADD_STRINGS = '''
def add_strings(num1, num2):
    """模拟竖式：i、j 从末尾往前，carry 记住进位，最后别忘了处理最高位进位。"""
    i, j = len(num1) - 1, len(num2) - 1
    carry = 0
    out = []
    while i >= 0 or j >= 0 or carry:
        a = int(num1[i]) if i >= 0 else 0
        b = int(num2[j]) if j >= 0 else 0
        s = a + b + carry
        out.append(str(s % 10))
        carry = s // 10
        i -= 1
        j -= 1
    return "".join(reversed(out))
'''

ADD_STRINGS_ALT = '''
def add_strings_int(num1, num2):
    """直接用 int()：Python 大整数没有溢出问题，但**面试官问的就是模拟**，
    所以这个版本只能作为「为什么不能这么写」的对照。"""
    return str(int(num1) + int(num2))
'''

# =========================================================== 10. 环形链表
HAS_CYCLE = '''
def has_cycle(head):
    """Floyd 判圈：slow 走 1 步、fast 走 2 步，有环必相遇，无环 fast 先到 None。"""
    slow = fast = head
    while fast and fast.next:
        slow = slow.next
        fast = fast.next.next
        if slow is fast:        # 比的是「结点身份」不是值
            return True
    return False
'''

HAS_CYCLE_ALT = '''
def has_cycle_hash(head):
    """哈希存访问过的结点：O(n) 额外空间，但能顺带回答「环的入口在哪」。"""
    seen = set()
    cur = head
    while cur:
        if id(cur) in seen:
            return True
        seen.add(id(cur))
        cur = cur.next
    return False
'''

# ============================================ 11. 删除排序链表中的重复元素 II
DELETE_DUP_II = '''
def delete_duplicates(head):
    """哑结点 + 「看下一段是否重复」：只要 next 与 next.next 相等就整段跳过。"""
    dummy = ListNode(0, head)
    cur = dummy
    while cur.next and cur.next.next:
        if cur.next.val == cur.next.next.val:
            dup = cur.next.val
            while cur.next and cur.next.val == dup:
                cur.next = cur.next.next      # 把这一整段重复值全删掉
        else:
            cur = cur.next
    return dummy.next
'''

DELETE_DUP_II_ALT = '''
def delete_duplicates_counter(head):
    """先数一遍每个值出现几次，再保留 count == 1 的：逻辑直白，但要走两遍链表。"""
    from collections import Counter

    cnt = Counter()
    cur = head
    while cur:
        cnt[cur.val] += 1
        cur = cur.next
    dummy = ListNode(0)
    tail = dummy
    cur = head
    while cur:
        if cnt[cur.val] == 1:
            tail.next = ListNode(cur.val)
            tail = tail.next
        cur = cur.next
    return dummy.next
'''

# ======================================== 12. 删除链表的倒数第 N 个节点
REMOVE_NTH = '''
def remove_nth_from_end(head, n):
    """哑结点 + 双指针定距离：fast 先走 n 步，然后一起走到 fast 到末尾，slow 正好在待删结点前一个。"""
    dummy = ListNode(0, head)
    fast = slow = dummy
    for _ in range(n):
        fast = fast.next
    while fast.next:
        fast = fast.next
        slow = slow.next
    slow.next = slow.next.next      # 跳掉待删结点
    return dummy.next
'''

REMOVE_NTH_ALT = '''
def remove_nth_from_end_count(head, n):
    """先求总长 L，再走 L-n 步：两遍扫描，胜在不容易写错。"""
    dummy = ListNode(0, head)
    L = 0
    cur = head
    while cur:
        L += 1
        cur = cur.next
    cur = dummy
    for _ in range(L - n):
        cur = cur.next
    cur.next = cur.next.next
    return dummy.next
'''

# ================================================ 13. 二叉树中的最大路径和
MAX_PATH_SUM = '''
def max_path_sum(root):
    """后序遍历：gain(u) = 以 u 为端点向下的最大贡献；每个结点处顺便更新「以 u 为拐点」的答案。"""
    best = float("-inf")

    def gain(node):
        nonlocal best
        if not node:
            return 0
        # 负贡献直接砍掉：选它不如不选（这条就是 0 vs 负数的取舍）
        left = max(gain(node.left), 0)
        right = max(gain(node.right), 0)
        # 以当前结点为「拐点」的完整路径：左 + 自己 + 右，用它更新全局答案
        best = max(best, node.val + left + right)
        # 向上返回的只能是「一条直链」：自己 + 较大的一侧
        return node.val + max(left, right)

    gain(root)
    return best
'''

MAX_PATH_SUM_ALT = '''
def max_path_sum_naive(root):
    """暴力枚举任意两个结点求真实路径和：O(n^2)。只用来验证 O(n) 后序解，
    面试里作为「反例」说明为什么必须用 DP（每个结点都重算一遍子树）。"""
    if not root:
        return 0

    parent = {root: None}

    def walk(n):
        for ch in (n.left, n.right):
            if ch:
                parent[ch] = n
                walk(ch)

    walk(root)
    nodes = list(parent)

    def path_to_root(u):
        """从 u 往上走到根的结点序列。"""
        p = []
        while u is not None:
            p.append(u)
            u = parent[u]
        return p

    best = float("-inf")
    for a in nodes:
        for b in nodes:
            pa, pb = path_to_root(a), path_to_root(b)
            seen = {n: i for i, n in enumerate(pa)}
            # pa 从 a 往根走，第一个出现在 pb 里的就是 LCA
            lca_i = next(i for i, n in enumerate(pa) if n in set(pb))
            lca = pa[lca_i]
            lca_j = pb.index(lca)
            # a → lca 的和 + b → lca 的和，LCA 自己只能算一次
            s = sum(n.val for n in pa[:lca_i + 1]) + sum(n.val for n in pb[:lca_j + 1]) - lca.val
            best = max(best, s)
    return best
'''

# =========================================================== 14. 复原 IP 地址
RESTORE_IP = '''
def restore_ip_addresses(s):
    """DFS 切 4 段：每段 1~3 位、无前导 0、值 ≤ 255；切满 4 段且用尽整串才收结果。"""
    out = []
    n = len(s)

    def dfs(start, parts):
        if len(parts) == 4:
            if start == n:                 # 必须恰好用完，不能剩字符
                out.append(".".join(parts))
            return
        # 剪枝：剩余字符数必须在「剩下的段」可行范围内
        remain_seg = 4 - len(parts)
        if n - start < remain_seg or n - start > remain_seg * 3:
            return
        for end in range(start + 1, min(start + 3, n) + 1):
            seg = s[start:end]
            if len(seg) > 1 and seg[0] == "0":     # 前导 0 非法
                break
            if int(seg) > 255:
                break
            dfs(end, parts + [seg])

    dfs(0, [])
    return out
'''

RESTORE_IP_ALT = '''
def restore_ip_addresses_iter(s):
    """三重循环暴力定切点：O(1) 段数所以是常数级枚举，胜在没有递归、边界一眼看清。"""
    n = len(s)
    out = []
    for a in range(1, 4):
        for b in range(1, 4):
            for c in range(1, 4):
                d = n - a - b - c
                if d < 1 or d > 3:
                    continue
                parts = [s[:a], s[a:a + b], s[a + b:a + b + c], s[a + b + c:]]
                if any(p[0] == "0" and len(p) > 1 for p in parts):
                    continue
                if all(0 <= int(p) <= 255 for p in parts):
                    out.append(".".join(parts))
    return out
'''

SOLUTIONS = {
    "1ce9f0a6715ffa8f": ("quick_sort", QUICK_SORT, QUICK_SORT_ALT),
    "541b3f61c94a86a7": ("length_of_lis", LIS, LIS_ALT),
    "034602d65c3c3d83": ("merge_two_lists", MERGE_LISTS, MERGE_LISTS_ALT),
    "bd4885b4390f3133": ("level_order", LEVEL_ORDER, LEVEL_ORDER_ALT),
    "68cee1fb263dc177": ("is_valid", VALID_PAREN, VALID_PAREN_ALT),
    "ae9b3bd5f0c0ec14": ("merge_sorted_array", MERGE_ARRAY, MERGE_ARRAY_ALT),
    "cc9024199418b8b6": ("reverse_between", REVERSE_II, REVERSE_II_ALT),
    "ce573ed982fd7269": ("reorder_list", REORDER_LIST, REORDER_LIST_ALT),
    "8cfadace34fdffa0": ("add_strings", ADD_STRINGS, ADD_STRINGS_ALT),
    "fa012b290cb172ce": ("has_cycle", HAS_CYCLE, HAS_CYCLE_ALT),
    "25052c937d781b08": ("delete_duplicates", DELETE_DUP_II, DELETE_DUP_II_ALT),
    "820e5d46ff3a9ca9": ("remove_nth_from_end", REMOVE_NTH, REMOVE_NTH_ALT),
    "89c412c833ced6e2": ("max_path_sum", MAX_PATH_SUM, MAX_PATH_SUM_ALT),
    "d80b9ddcb5f113ce": ("restore_ip_addresses", RESTORE_IP, RESTORE_IP_ALT),
}


def run_selftest() -> int:
    """跑一遍所有参考实现，任何一条不过就非零退出。"""
    print(f"python {sys.version.split()[0]}")
    fails = 0

    # 1 快排
    body = {}
    exec(LIST_NODE, body)
    exec(QUICK_SORT, body)
    for xs, exp in [([], []), ([1], [1]), ([3, 1, 2], [1, 2, 3]),
                    ([5, 5, 1, 1, 3], [1, 1, 3, 5, 5]),
                    (list(range(50)), list(range(50))),
                    (list(range(50, 0, -1)), list(range(1, 51)))]:
        got = body["quick_sort"](list(xs))
        if got != exp:
            fails += 1
            print(f"  E quick_sort({xs[:8]}…) -> {got[:8]} != {exp[:8]}")
    print("  ok quick_sort")

    # 2 LIS
    body = {}
    exec(LIS, body)
    exec(LIS_ALT, body)
    for xs, exp in [([], 0), ([1], 1), ([10, 9, 2, 5, 3, 7, 101, 18], 4),
                    ([7, 7, 7, 7], 1), ([0, 1, 0, 3, 2, 3], 4),
                    ([1, 3, 6, 7, 9, 4, 10, 5, 6], 6)]:
        a, b = body["length_of_lis"](list(xs)), body["length_of_lis_dp"](list(xs))
        if a != exp or b != exp:
            fails += 1
            print(f"  E lis({xs}) -> {a}/{b} != {exp}")
    print("  ok length_of_lis (+dp 交叉验证)")

    # 3 合并两个有序链表
    body = {}
    exec(LIST_NODE, body)
    body["ListNode"] = ListNode
    exec(MERGE_LISTS, body)
    exec(MERGE_LISTS_ALT, body)
    for a, b, exp in [([], [], []), ([], [0], [0]), ([1, 2, 4], [1, 3, 4], [1, 1, 2, 3, 4, 4]),
                      ([1, 1], [1, 1], [1, 1, 1, 1]), ([5], [1, 2, 3], [1, 2, 3, 5])]:
        g1 = to_list(body["merge_two_lists"](mk_list(a), mk_list(b)))
        g2 = to_list(body["merge_two_lists_rec"](mk_list(a), mk_list(b)))
        if g1 != exp or g2 != exp:
            fails += 1
            print(f"  E merge({a},{b}) -> {g1}/{g2} != {exp}")
    print("  ok merge_two_lists (+递归版)")

    # 4 层序遍历
    body = {}
    body["TreeNode"] = TreeNode
    exec(LEVEL_ORDER, body)
    exec(LEVEL_ORDER_ALT, body)
    for xs, exp in [([], []), ([1], [[1]]), ([3, 9, 20, None, None, 15, 7], [[3], [9, 20], [15, 7]]),
                    ([1, 2, 3, 4, None, None, 5], [[1], [2, 3], [4, 5]])]:
        g1 = body["level_order"](mk_tree(xs))
        g2 = body["level_order_dfs"](mk_tree(xs))
        if g1 != exp or g2 != exp:
            fails += 1
            print(f"  E level_order({xs}) -> {g1}/{g2} != {exp}")
    print("  ok level_order (+DFS 版)")

    # 5 有效括号
    body = {}
    exec(VALID_PAREN, body)
    exec(VALID_PAREN_ALT, body)
    for s, exp in [("()", True), ("()[]{}", True), ("(]", False), ("([)]", False),
                   ("{[]}", True), ("(", False), (")", False), ("", True),
                   ("([{}])()", True), ("(((", False)]:
        g1, g2 = body["is_valid"](s), body["is_valid_replace"](s)
        if g1 != exp or g2 != exp:
            fails += 1
            print(f"  E is_valid({s!r}) -> {g1}/{g2} != {exp}")
    print("  ok is_valid (+消去法)")

    # 6 合并两个有序数组
    body = {}
    exec(MERGE_ARRAY, body)
    exec(MERGE_ARRAY_ALT, body)
    for n1, m, n2, n, exp in [
        ([1, 2, 3, 0, 0, 0], 3, [2, 5, 6], 3, [1, 2, 2, 3, 5, 6]),
        ([1], 1, [], 0, [1]),
        ([0], 0, [1], 1, [1]),
        ([4, 0, 0, 0, 0, 0], 1, [1, 2, 3, 5, 6], 5, [1, 2, 3, 4, 5, 6]),
        ([1, 2, 4, 5, 6, 0], 5, [3], 1, [1, 2, 3, 4, 5, 6]),
    ]:
        g1 = body["merge_sorted_array"](list(n1), m, list(n2), n)
        g2 = body["merge_sorted_array_front"](list(n1), m, list(n2), n)
        if g1 != exp or g2 != exp:
            fails += 1
            print(f"  E merge_array({n1},{m},{n2},{n}) -> {g1}/{g2} != {exp}")
    print("  ok merge_sorted_array (+临时副本版)")

    # 7 反转链表 II
    body = {}
    body["ListNode"] = ListNode
    exec(REVERSE_II, body)
    exec(REVERSE_II_ALT, body)
    for xs, l, r, exp in [([1, 2, 3, 4, 5], 2, 4, [1, 4, 3, 2, 5]),
                          ([5], 1, 1, [5]),
                          ([1, 2, 3], 1, 3, [3, 2, 1]),
                          ([1, 2, 3, 4, 5], 1, 1, [1, 2, 3, 4, 5]),
                          ([1, 2, 3, 4, 5], 3, 5, [1, 2, 5, 4, 3]),
                          ([1, 2], 1, 2, [2, 1])]:
        g1 = to_list(body["reverse_between"](mk_list(xs), l, r))
        g2 = to_list(body["reverse_between_splice"](mk_list(xs), l, r))
        if g1 != exp or g2 != exp:
            fails += 1
            print(f"  E reverse_between({xs},{l},{r}) -> {g1}/{g2} != {exp}")
    print("  ok reverse_between (+切段版)")

    # 8 重排链表
    body = {}
    body["ListNode"] = ListNode
    exec(REORDER_LIST, body)
    exec(REORDER_LIST_ALT, body)
    for xs, exp in [([1, 2, 3, 4], [1, 4, 2, 3]),
                    ([1, 2, 3, 4, 5], [1, 5, 2, 4, 3]),
                    ([1], [1]), ([1, 2], [1, 2]),
                    ([1, 2, 3], [1, 3, 2]),
                    ([1, 2, 3, 4, 5, 6], [1, 6, 2, 5, 3, 4])]:
        g1 = to_list(body["reorder_list"](mk_list(xs)))
        g2 = to_list(body["reorder_list_array"](mk_list(xs)))
        if g1 != exp or g2 != exp:
            fails += 1
            print(f"  E reorder_list({xs}) -> {g1}/{g2} != {exp}")
    print("  ok reorder_list (+数组版)")

    # 9 字符串相加
    body = {}
    exec(ADD_STRINGS, body)
    exec(ADD_STRINGS_ALT, body)
    for a, b, exp in [("11", "123", "134"), ("456", "77", "533"), ("0", "0", "0"),
                      ("9", "1", "10"), ("999", "1", "1000"),
                      ("1" * 40, "9" * 40, None), ("999999999999999999", "1", "1000000000000000000")]:
        g1 = body["add_strings"](a, b)
        g2 = body["add_strings_int"](a, b)
        want = exp if exp is not None else str(int(a) + int(b))
        if g1 != want or g2 != want:
            fails += 1
            print(f"  E add_strings({a[:10]}…,{b[:10]}…) -> {g1[:12]}…/{g2[:12]}… != {want[:12]}…")
    print("  ok add_strings (+int 对照版)")

    # 10 环形链表
    body = {}
    body["ListNode"] = ListNode
    exec(HAS_CYCLE, body)
    exec(HAS_CYCLE_ALT, body)
    # pos=1 → 尾结点连到下标 1
    def build_cycle(xs, pos):
        if not xs:
            return None
        head = mk_list(xs)
        if pos < 0:
            return head
        nodes, cur = [], head
        while cur:
            nodes.append(cur)
            cur = cur.next
        nodes[-1].next = nodes[pos]
        return head

    for xs, pos, exp in [([3, 2, 0, -4], 1, True), ([1, 2], 0, True),
                         ([1], -1, False), ([], -1, False), ([1, 2], -1, False)]:
        g1 = body["has_cycle"](build_cycle(xs, pos))
        g2 = body["has_cycle_hash"](build_cycle(xs, pos))
        if g1 != exp or g2 != exp:
            fails += 1
            print(f"  E has_cycle({xs},pos={pos}) -> {g1}/{g2} != {exp}")
    print("  ok has_cycle (+哈希版)")

    # 11 删除排序链表中的重复元素 II
    body = {}
    body["ListNode"] = ListNode
    exec(DELETE_DUP_II, body)
    exec(DELETE_DUP_II_ALT, body)
    for xs, exp in [([1, 2, 3, 3, 4, 4, 5], [1, 2, 5]),
                    ([1, 1, 1, 2, 3], [2, 3]),
                    ([1, 1], []), ([1, 2], [1, 2]), ([], []),
                    ([1, 1, 1], []), ([1, 2, 2, 3, 3], [1])]:
        g1 = to_list(body["delete_duplicates"](mk_list(xs)))
        g2 = to_list(body["delete_duplicates_counter"](mk_list(xs)))
        if g1 != exp or g2 != exp:
            fails += 1
            print(f"  E delete_duplicates({xs}) -> {g1}/{g2} != {exp}")
    print("  ok delete_duplicates (+计数版)")

    # 12 删除倒数第 N 个
    body = {}
    body["ListNode"] = ListNode
    exec(REMOVE_NTH, body)
    exec(REMOVE_NTH_ALT, body)
    for xs, n, exp in [([1, 2, 3, 4, 5], 2, [1, 2, 3, 5]),
                       ([1], 1, []), ([1, 2], 1, [1]), ([1, 2], 2, [2]),
                       ([1, 2, 3, 4, 5], 5, [2, 3, 4, 5])]:
        g1 = to_list(body["remove_nth_from_end"](mk_list(xs), n))
        g2 = to_list(body["remove_nth_from_end_count"](mk_list(xs), n))
        if g1 != exp or g2 != exp:
            fails += 1
            print(f"  E remove_nth({xs},{n}) -> {g1}/{g2} != {exp}")
    print("  ok remove_nth_from_end (+两遍扫描版)")

    # 13 二叉树最大路径和
    body = {}
    body["TreeNode"] = TreeNode
    exec(MAX_PATH_SUM, body)
    exec(MAX_PATH_SUM_ALT, body)
    for xs, exp in [([1, 2, 3], 6), ([-10, 9, 20, None, None, 15, 7], 42),
                    ([-3], -3), ([2, -1], 2), ([1, -2, -3, 1, 3, -2, None, -1], 3),
                    ([-2, -1], -1), ([5, 4, 8, 11, None, 13, 4, 7, 2, None, None, None, 1], 48)]:
        g1 = body["max_path_sum"](mk_tree(xs))
        g2 = body["max_path_sum_naive"](mk_tree(xs))
        if g1 != exp or g2 != exp:
            fails += 1
            print(f"  E max_path_sum({xs}) -> {g1}/{g2} != {exp}")
    print("  ok max_path_sum (+暴力 LCA 交叉验证)")

    # 14 复原 IP
    body = {}
    exec(RESTORE_IP, body)
    exec(RESTORE_IP_ALT, body)
    for s, exp in [("25525511135", ["255.255.11.135", "255.255.111.35"]),
                   ("0000", ["0.0.0.0"]),
                   ("101023", ["1.0.10.23", "1.0.102.3", "10.1.0.23", "10.10.2.3", "101.0.2.3"]),
                   ("1111", ["1.1.1.1"]),
                   ("010010", ["0.10.0.10", "0.100.1.0"]),
                   ("1234567890123", [])]:
        g1 = body["restore_ip_addresses"](s)
        g2 = body["restore_ip_addresses_iter"](s)
        if sorted(g1) != sorted(exp) or sorted(g2) != sorted(exp):
            fails += 1
            print(f"  E restore_ip({s}) -> {g1} / {g2} != {exp}")
    print("  ok restore_ip_addresses (+三重循环版)")

    print()
    if fails:
        print(f"FAILED: {fails} case(s)")
    else:
        print("ALL 14 SOLUTIONS PASS — 参考实现全部可运行且通过边界用例")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run_selftest())
