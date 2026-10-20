#!/usr/bin/env python3
"""Render and check the hierarchical ticket index under docs/tickets.

Facts come from .tickets/*.md frontmatter. The module registry comes from
docs/tickets/modules.toml; per-ticket module ownership and one-line summaries
come from docs/tickets/meta/<id>.toml. INDEX.md and modules/*.md are local
artifacts: they are generated, never committed, and therefore cannot conflict
when two branches merge.

Commands:
    facts   compact fact sheet for review
    check   validate config and generated files (exit 1 on problems)
    diff    show what render would change, without writing (review only the hunks)
    render  write INDEX.md and modules/*.md
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    print("需要 Python 3.11+（tomllib）。", file=sys.stderr)
    raise SystemExit(2)

ID_RE = re.compile(r"ai4-[0-9a-z]{4}")
MODULE_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
ACTIVE_STATUSES = {"open", "in_progress"}
STATUS_ORDER = {"in_progress": 0, "open": 1, "closed": 2}
PLACEHOLDER_ASSIGNEES = {"", "-", "sciweave", "team", "tbd", "todo"}
GENERATED_MARK = "由 `ticket-index` 技能生成"


# --------------------------------------------------------------------------
# Parsing


@dataclass(frozen=True)
class Ticket:
    id: str
    title: str
    status: str
    type: str
    priority: int
    assignee: str
    parent: str | None
    deps: tuple[str, ...]
    links: tuple[str, ...]
    tags: tuple[str, ...]
    created: str

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def is_map(self) -> bool:
        return "wayfinder:map" in self.tags


@dataclass(frozen=True)
class Module:
    id: str
    title: str
    scope: str


def _strip_comment(value: str) -> str:
    quote = None
    for index, char in enumerate(value):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and index > 0 and value[index - 1] in " \t":
            return value[:index]
    return value


def _scalar(raw: str) -> str:
    value = _strip_comment(raw).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _ids(raw: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in ID_RE.finditer(_strip_comment(raw)))


def cell(text: str) -> str:
    """Keep Markdown table rows intact when a title or scope contains a pipe."""
    return text.replace("|", "\\|").replace("\n", " ")


def parse_ticket(path: Path) -> Ticket:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    meta: dict[str, str] = {}
    body_start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                body_start = index + 1
                break
        for line in lines[1:body_start]:
            if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            meta[key.strip()] = value

    title = ""
    for line in lines[body_start:]:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    try:
        priority = int(_scalar(meta.get("priority", "2")))
    except ValueError:
        priority = 2

    return Ticket(
        id=_scalar(meta.get("id", "")).strip() or path.stem,
        title=title or path.stem,
        status=_scalar(meta.get("status", "open")) or "open",
        type=_scalar(meta.get("type", "task")) or "task",
        priority=priority,
        assignee=_scalar(meta.get("assignee", "")),
        parent=(_ids(meta.get("parent", "")) or (None,))[0],
        deps=_ids(meta.get("deps", "")),
        links=_ids(meta.get("links", "")),
        tags=tuple(
            tag.strip().strip("\"'")
            for tag in _strip_comment(meta.get("tags", "")).strip().strip("[]").split(",")
            if tag.strip()
        ),
        created=_scalar(meta.get("created", "")),
    )


def find_repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / ".tickets").is_dir():
            return parent
    for parent in (Path.cwd().resolve(), *Path.cwd().resolve().parents):
        if (parent / ".tickets").is_dir():
            return parent
    raise SystemExit("找不到仓库根目录：向上查找 .tickets/ 失败")


# --------------------------------------------------------------------------
# Index model


class Index:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.tickets: dict[str, Ticket] = {}
        self.modules: list[Module] = []
        self.entries: dict[str, dict] = {}
        self.entries_seen: set[str] = set()
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self._load()

    # -- loading and validation -------------------------------------------

    def _load(self) -> None:
        tickets_dir = self.root / ".tickets"
        for path in sorted(tickets_dir.glob("*.md")):
            if not ID_RE.fullmatch(path.stem):
                self.warnings.append(f"忽略非工单文件：{path.name}")
                continue
            ticket = parse_ticket(path)
            if ticket.id != path.stem:
                self.errors.append(f"{path.name}：frontmatter id `{ticket.id}` 与文件名不一致")
                continue
            self.tickets[ticket.id] = ticket

        modules_path = self.root / "docs/tickets/modules.toml"
        if not modules_path.is_file():
            self.errors.append("缺少 docs/tickets/modules.toml")
            return
        try:
            config = tomllib.loads(modules_path.read_text(encoding="utf-8-sig"))
        except tomllib.TOMLDecodeError as exc:
            self.errors.append(f"docs/tickets/modules.toml 不是合法 TOML：{exc}")
            return

        for raw in config.get("modules", []):
            module = Module(
                id=str(raw.get("id", "")).strip(),
                title=str(raw.get("title", "")).strip(),
                scope=str(raw.get("scope", "")).strip(),
            )
            if not MODULE_ID_RE.fullmatch(module.id):
                self.errors.append(f"模块 id 非法：`{module.id}`（只允许小写字母、数字、连字符）")
                continue
            if not module.title:
                self.errors.append(f"模块 `{module.id}` 缺少 title")
            self.modules.append(module)

        module_ids = [module.id for module in self.modules]
        for duplicate, count in Counter(module_ids).items():
            if count > 1:
                self.errors.append(f"模块 id 重复：`{duplicate}`")

        meta_dir = self.root / "docs/tickets/meta"
        if not meta_dir.is_dir():
            self.errors.append("缺少 docs/tickets/meta/ 目录")
            return

        for path in sorted(meta_dir.glob("*.toml")):
            if not ID_RE.fullmatch(path.stem):
                self.warnings.append(f"忽略非工单元数据：{path.name}")
                continue
            relative = path.relative_to(self.root).as_posix()
            try:
                raw = tomllib.loads(path.read_text(encoding="utf-8-sig"))
            except tomllib.TOMLDecodeError as exc:
                self.errors.append(f"{relative} 不是合法 TOML：{exc}")
                continue
            if path.stem not in self.tickets:
                self.errors.append(f"{relative}：工单 `{path.stem}` 不存在于 .tickets/")
                continue
            self.entries_seen.add(path.stem)
            raw_modules = raw.get("module", [])
            if isinstance(raw_modules, str):
                modules = [raw_modules]
            elif isinstance(raw_modules, list) and all(isinstance(item, str) for item in raw_modules):
                modules = list(raw_modules)
            else:
                self.errors.append(f"{relative}：module 必须是字符串或字符串数组")
                continue
            if not modules:
                self.errors.append(f"{relative}：未指定 module")
                continue
            if len(set(modules)) != len(modules):
                self.errors.append(f"{relative}：module 有重复项")
            unknown = [module for module in modules if module not in module_ids]
            if unknown:
                self.errors.append(f"{relative}：使用了未知模块 {', '.join(unknown)}")
                continue
            summary = str(raw.get("summary", "")).strip()
            if not summary:
                self.errors.append(f"{relative}：缺少 summary")
            elif not 20 <= len(summary) <= 60:
                self.warnings.append(f"{relative}：summary 为 {len(summary)} 字，建议 20–60 字")
            self.entries[path.stem] = {"modules": tuple(modules), "summary": summary}

        for ticket_id in self.tickets:
            if ticket_id not in self.entries_seen:
                self.errors.append(
                    f"docs/tickets/meta/{ticket_id}.toml：缺少该工单的 module 与 summary"
                )

        for ticket in self.tickets.values():
            if ticket.status not in STATUS_ORDER:
                self.warnings.append(f"{ticket.id}：未知状态 `{ticket.status}`")
            if ticket.parent and ticket.parent not in self.tickets:
                self.errors.append(f"{ticket.id}：parent `{ticket.parent}` 不存在")
            for dep in ticket.deps:
                if dep not in self.tickets:
                    self.errors.append(f"{ticket.id}：依赖 `{dep}` 不存在")
            for link in ticket.links:
                if link not in self.tickets:
                    self.errors.append(f"{ticket.id}：关联 `{link}` 不存在")

    # -- lookups ----------------------------------------------------------

    def entry(self, ticket_id: str) -> dict:
        return self.entries.get(ticket_id, {"modules": (), "summary": ""})

    def primary(self, ticket_id: str) -> str:
        modules = self.entry(ticket_id)["modules"]
        return modules[0] if modules else ""

    def modules_of(self, ticket_id: str) -> tuple[str, ...]:
        return self.entry(ticket_id)["modules"]

    def summary(self, ticket_id: str) -> str:
        return self.entry(ticket_id)["summary"]

    def module_title(self, module_id: str) -> str:
        for module in self.modules:
            if module.id == module_id:
                return module.title
        return module_id

    def sorted_tickets(self) -> list[Ticket]:
        return [self.tickets[key] for key in sorted(self.tickets)]

    def module_tickets(self, module_id: str) -> list[Ticket]:
        return [ticket for ticket in self.sorted_tickets() if self.primary(ticket.id) == module_id]

    def is_blocked(self, ticket: Ticket) -> bool:
        return ticket.active and bool(self.unresolved(ticket))

    def unresolved(self, ticket: Ticket) -> list[str]:
        return [
            dep
            for dep in ticket.deps
            if dep not in self.tickets or self.tickets[dep].status != "closed"
        ]

    def is_placeholder_assignee(self, ticket: Ticket) -> bool:
        return ticket.assignee.strip().lower() in PLACEHOLDER_ASSIGNEES

    # -- derived views ----------------------------------------------------

    def tree(self, module_id: str) -> tuple[dict[str, list[Ticket]], list[Ticket]]:
        children: dict[str, list[Ticket]] = defaultdict(list)
        roots: list[Ticket] = []
        for ticket in self.module_tickets(module_id):
            parent = ticket.parent
            if parent and parent in self.tickets and self.primary(parent) == module_id:
                children[parent].append(ticket)
            else:
                roots.append(ticket)

        def child_key(ticket: Ticket) -> tuple[int, int, str]:
            return (STATUS_ORDER.get(ticket.status, 9), ticket.priority, ticket.id)

        for siblings in children.values():
            siblings.sort(key=child_key)
        roots.sort(key=lambda ticket: (0 if ticket.is_map else 1, *child_key(ticket)))
        return children, roots

    def cross_relations(self) -> list[tuple[str, str, str]]:
        relations: list[tuple[str, str, str]] = []
        seen_links: set[tuple[str, str]] = set()
        for ticket in self.sorted_tickets():
            for dep in ticket.deps:
                if dep in self.tickets and self.primary(dep) != self.primary(ticket.id):
                    relations.append((ticket.id, "依赖", dep))
            for link in ticket.links:
                if link not in self.tickets:
                    continue
                if self.primary(link) == self.primary(ticket.id):
                    continue
                pair = (ticket.id, link) if ticket.id < link else (link, ticket.id)
                if pair in seen_links:
                    continue
                seen_links.add(pair)
                relations.append((pair[0], "关联", pair[1]))
        return sorted(set(relations))

    # -- rendering --------------------------------------------------------

    @staticmethod
    def ticket_link(ticket_id: str, up: str = "../..") -> str:
        return f"[{ticket_id}]({up}/.tickets/{ticket_id}.md)"

    def dep_label(self, ticket_id: str, up: str = "../..") -> str:
        if ticket_id not in self.tickets:
            return f"`{ticket_id}`（缺失）"
        ticket = self.tickets[ticket_id]
        return f"{self.ticket_link(ticket_id, up)}（{ticket.status}）"

    def badge_text(self, ticket: Ticket) -> str:
        badges = [ticket.type or "task"]
        if ticket.is_map:
            badges.append("map")
        badges.append(f"P{ticket.priority}")
        badges.append(ticket.status)
        badges.append(ticket.assignee or "未分配")
        return " ".join(f"`{badge}`" for badge in badges)

    def render_line(
        self, ticket: Ticket, depth: int, module_id: str, up: str = "../..", cycle: bool = False
    ) -> str:
        line = (
            f"{'  ' * depth}- {self.ticket_link(ticket.id, up)} **{ticket.title}**"
            f" — {self.summary(ticket.id)} {self.badge_text(ticket)}"
        )
        extras: list[str] = []
        if ticket.active:
            blocked = self.unresolved(ticket)
            if blocked:
                extras.append("阻塞于 " + "、".join(self.dep_label(dep, up) for dep in blocked))
        if ticket.parent:
            if ticket.parent not in self.tickets:
                extras.append(f"上级 `{ticket.parent}`（缺失）")
            elif self.primary(ticket.parent) != module_id:
                extras.append(
                    f"上级 {self.ticket_link(ticket.parent, up)}"
                    f"（{self.module_title(self.primary(ticket.parent))}）"
                )
        if cycle:
            extras.append("层级循环")
        if extras:
            line += " · " + " · ".join(extras)
        return line

    def render_tree(self, module_id: str, up: str = "../../..") -> list[str]:
        children, roots = self.tree(module_id)
        if not roots:
            return ["（本模块暂无工单）"]

        lines: list[str] = []

        def walk(ticket: Ticket, depth: int, stack: frozenset[str]) -> None:
            cycle = ticket.id in stack
            lines.append(self.render_line(ticket, depth, module_id, up=up, cycle=cycle))
            if cycle:
                return
            next_stack = stack | {ticket.id}
            for child in children.get(ticket.id, []):
                walk(child, depth + 1, next_stack)

        for root in roots:
            walk(root, 0, frozenset())
        return lines

    def module_stats(self, module_id: str) -> dict[str, int]:
        tickets = self.module_tickets(module_id)
        counts = Counter(ticket.status for ticket in tickets)
        return {
            "total": len(tickets),
            "open": counts.get("open", 0),
            "in_progress": counts.get("in_progress", 0),
            "closed": counts.get("closed", 0),
            "active": counts.get("open", 0) + counts.get("in_progress", 0),
            "maps": sum(1 for ticket in tickets if ticket.is_map),
        }

    def render_module(self, module: Module) -> str:
        stats = self.module_stats(module.id)
        lines = [
            f"# 工单模块：{module.title}",
            "",
            f"> {GENERATED_MARK}，请勿手工编辑。"
            f"总览：[索引](../INDEX.md) · 模块注册：[modules.toml](../modules.toml)"
            f" · 工单元数据：[meta/](../meta/)",
            "",
            f"**范围**：{module.scope or '（未填写）'}",
            "",
            f"**统计**：共 {stats['total']} 张 · 活跃 {stats['active']}"
            f"（open {stats['open']} / in_progress {stats['in_progress']}）"
            f" · 已关闭 {stats['closed']} · 地图 {stats['maps']}",
            "",
            "## 工单层级",
            "",
            *self.render_tree(module.id, up="../../.."),
        ]

        referenced = [
            ticket
            for ticket in self.sorted_tickets()
            if module.id in self.modules_of(ticket.id) and self.primary(ticket.id) != module.id
        ]
        if referenced:
            lines += ["", "## 跨模块归属", "", "以下工单主模块在其他领域，同时归属本模块：", ""]
            for ticket in referenced:
                primary = self.primary(ticket.id)
                lines.append(
                    f"- {self.ticket_link(ticket.id, '../../..')} **{ticket.title}**"
                    f" — {self.summary(ticket.id)}"
                    f"（主模块：[{self.module_title(primary)}]({primary}.md)）"
                )
        lines.append("")
        return "\n".join(lines)

    def render_index(self) -> str:
        tickets = self.sorted_tickets()
        status_counts = Counter(ticket.status for ticket in tickets)
        type_counts = Counter(ticket.type or "task" for ticket in tickets)
        active = [ticket for ticket in tickets if ticket.active]
        frontier = [ticket for ticket in active if not self.unresolved(ticket)]
        blocked = [ticket for ticket in active if self.unresolved(ticket)]
        ownerless = [ticket for ticket in active if self.is_placeholder_assignee(ticket)]
        relations = self.cross_relations()
        multi_module = [ticket for ticket in tickets if len(self.modules_of(ticket.id)) > 1]

        lines = [
            "# SciWeave 工单索引",
            "",
            f"> {GENERATED_MARK}：事实来自 `.tickets/`，归属与简介来自 [`meta/<id>.toml`](meta/)，模块来自 [`modules.toml`](modules.toml)；本文件是本地生成物，不入库，请勿手工编辑。",
            "> 工单变更后运行 `python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py render`。",
            "",
            "## 读法",
            "",
            "- 找工单：先看模块导航，再打开模块文件；定位到候选后再读 `.tickets/<id>.md` 全文。",
            "- `open` 待开始，`in_progress` 进行中，`closed` 已验收关闭；**活跃**指前两者。",
            "- 带 `map` 标记的是 Wayfinder 地图；层级只来自 `parent`，`links` 表达关联。",
            "- 跨模块工单只在主模块展开；其他模块的归属、依赖和关联见“跨模块关系”。",
            "",
            "## 总览",
            "",
            f"- 工单总数 **{len(tickets)}**：open {status_counts.get('open', 0)}"
            f" · in_progress {status_counts.get('in_progress', 0)}"
            f" · closed {status_counts.get('closed', 0)}",
            "- 类型：" + " · ".join(f"{name} {count}" for name, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))),
            f"- 地图 {sum(1 for ticket in tickets if ticket.is_map)} 张"
            f" · 活跃 {len(active)} 张"
            f" · 跨模块关系 {len(relations)} 条",
            "",
            "## 负责人（活跃工单）",
            "",
            "| 负责人 | open | in_progress | 活跃合计 |",
            "| --- | ---: | ---: | ---: |",
        ]

        by_assignee: dict[str, list[Ticket]] = defaultdict(list)
        for ticket in active:
            by_assignee[ticket.assignee.strip() or "未分配"].append(ticket)
        for assignee, owned in sorted(by_assignee.items(), key=lambda item: (-len(item[1]), item[0])):
            open_count = sum(1 for ticket in owned if ticket.status == "open")
            progress_count = sum(1 for ticket in owned if ticket.status == "in_progress")
            shown = f"{assignee}（占位）" if assignee.strip().lower() in PLACEHOLDER_ASSIGNEES else assignee
            lines.append(f"| {cell(shown)} | {open_count} | {progress_count} | {len(owned)} |")
        if not by_assignee:
            lines.append("| （无活跃工单） | 0 | 0 | 0 |")

        lines += [
            "",
            "## 模块导航",
            "",
            "| 模块 | 范围 | 工单 | 活跃 | 地图 |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
        for module in self.modules:
            stats = self.module_stats(module.id)
            lines.append(
                f"| [{module.title}](modules/{module.id}.md) | {cell(module.scope) or '—'}"
                f" | {stats['total']} | {stats['active']} | {stats['maps']} |"
            )
        if not self.modules:
            lines.append("| （未配置模块） | — | 0 | 0 | 0 |")

        lines += [
            "",
            "## 当前前沿",
            "",
            "依赖已满足的活跃工单，可直接认领或继续。",
            "",
            "| 工单 | 模块 | 负责人 |",
            "| --- | --- | --- |",
        ]
        for ticket in sorted(frontier, key=lambda item: (item.priority, item.id)):
            lines.append(
                f"| {self.ticket_link(ticket.id)} {cell(ticket.title)}"
                f" | {self.module_title(self.primary(ticket.id))}"
                f" | {cell(ticket.assignee) or '未分配'} |"
            )
        if not frontier:
            lines.append("| （无） | — | — |")

        lines += [
            "",
            "## 阻塞中的活跃工单",
            "",
            "| 工单 | 模块 | 阻塞于 |",
            "| --- | --- | --- |",
        ]
        for ticket in sorted(blocked, key=lambda item: (item.priority, item.id)):
            deps = "、".join(self.dep_label(dep) for dep in self.unresolved(ticket))
            lines.append(
                f"| {self.ticket_link(ticket.id)} {cell(ticket.title)}"
                f" | {self.module_title(self.primary(ticket.id))}"
                f" | {deps} |"
            )
        if not blocked:
            lines.append("| （无） | — | — |")

        lines += [
            "",
            "## 待补负责人",
            "",
            "活跃但 `assignee` 为空或仍是团队占位名的工单，需要指定具体个人。",
            "",
            "| 工单 | 状态 | 当前 assignee |",
            "| --- | --- | --- |",
        ]
        for ticket in sorted(ownerless, key=lambda item: (item.priority, item.id)):
            lines.append(f"| {self.ticket_link(ticket.id)} {cell(ticket.title)} | {ticket.status} | `{cell(ticket.assignee) or '空'}` |")
        if not ownerless:
            lines.append("| （无） | — | — |")

        lines += [
            "",
            "## 跨模块关系",
            "",
            "### 多模块归属",
            "",
            "| 工单 | 主模块 | 同时归属 |",
            "| --- | --- | --- |",
        ]
        for ticket in multi_module:
            modules = self.modules_of(ticket.id)
            others = "、".join(self.module_title(module_id) for module_id in modules[1:])
            lines.append(
                f"| {self.ticket_link(ticket.id)} {cell(ticket.title)}"
                f" | {self.module_title(modules[0])} | {others} |"
            )
        if not multi_module:
            lines.append("| （无） | — | — |")

        lines += [
            "",
            "### 依赖与关联",
            "",
            "只列跨模块的边；同一对工单的对称关联只出现一次。",
            "",
            "| 工单 | 关系 | 对方工单 | 涉及模块 |",
            "| --- | --- | --- | --- |",
        ]
        for source, kind, target in relations:
            modules = sorted({self.module_title(self.primary(source)), self.module_title(self.primary(target))})
            lines.append(
                f"| {self.ticket_link(source)} | {kind} | {self.ticket_link(target)} | {'、'.join(modules)} |"
            )
        if not relations:
            lines.append("| （无） | — | — |")

        lines += [
            "",
            "## 维护约定",
            "",
            "- 事实来源：`.tickets/ai4-*.md` 的 frontmatter，通过 `fer` 修改；索引不缓存可推导事实。",
            "- 归属与简介：`docs/tickets/meta/<id>.toml`，由人维护；脚本不推断一句话简介。",
            "- 模块注册：`docs/tickets/modules.toml`，只在模块增减时修改。",
            "- 生成物：`INDEX.md` 与 `modules/*.md` 不入库，合并分支后运行 `render` 即可重建。",
            "- 生成：`python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py render`。",
            "- 校验：`python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py check`，退出码 0 才算一致。",
            "- 模块 = 工单结论落地的领域；一张票只在一个模块展开，跨模块关系单独汇总。",
            "- 本文件与 `modules/*.md` 都是生成物；手改会在下一次 `check` 中报过期。",
            "",
        ]
        return "\n".join(lines)

    def expected_files(self) -> dict[Path, str]:
        output = self.root / "docs/tickets"
        files = {output / "INDEX.md": self.render_index()}
        for module in self.modules:
            files[output / "modules" / f"{module.id}.md"] = self.render_module(module)
        return files


# --------------------------------------------------------------------------
# Commands


def print_problems(problems: list[str], warnings: list[str]) -> None:
    for warning in warnings:
        print(f"警告：{warning}", file=sys.stderr)
    if problems:
        print(f"发现 {len(problems)} 个问题：", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)


def cmd_check(index: Index) -> int:
    problems = list(index.errors)
    for path, expected in index.expected_files().items():
        relative = path.relative_to(index.root)
        if not path.is_file():
            problems.append(f"缺少生成文件：{relative}（运行 render）")
        elif path.read_text(encoding="utf-8") != expected:
            problems.append(f"生成文件过期：{relative}（运行 render）")

    modules_dir = index.root / "docs/tickets/modules"
    managed = {path.resolve() for path in index.expected_files()}
    if modules_dir.is_dir():
        for path in sorted(modules_dir.glob("*.md")):
            if path.resolve() in managed:
                continue
            if GENERATED_MARK in path.read_text(encoding="utf-8")[:600]:
                problems.append(f"多余生成文件：{path.relative_to(index.root)}（运行 render 清理）")

    print_problems(problems, index.warnings)
    if problems:
        return 1
    print(f"OK：{len(index.tickets)} 张工单，{len(index.modules)} 个模块，生成文件一致。")
    return 0


def cmd_diff(index: Index) -> int:
    """Show the unified diff render would produce, so review stays on deltas."""
    changed = 0
    for path, expected in index.expected_files().items():
        relative = path.relative_to(index.root).as_posix()
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current == expected:
            continue
        changed += 1
        print(f"### {relative}")
        print(
            "\n".join(
                difflib.unified_diff(
                    current.splitlines(),
                    expected.splitlines(),
                    fromfile=f"a/{relative}",
                    tofile=f"b/{relative}",
                    lineterm="",
                )
            )
        )
        print()

    print_problems([], index.warnings)
    if changed:
        print(f"{changed} 个生成文件将变化（只审查上面的 hunk；运行 render 写入）。")
    else:
        print("生成文件已是最新，无需审查。")
    return 0


def cmd_render(index: Index) -> int:
    if index.errors:
        print_problems(index.errors, index.warnings)
        print("配置有错误，未写入任何文件。", file=sys.stderr)
        return 1

    written = 0
    unchanged = 0
    expected = index.expected_files()
    for path, content in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.read_text(encoding="utf-8") == content:
            unchanged += 1
            continue
        path.write_text(content, encoding="utf-8", newline="\n")
        written += 1

    removed = 0
    modules_dir = index.root / "docs/tickets/modules"
    managed = {path.resolve() for path in expected}
    if modules_dir.is_dir():
        for path in sorted(modules_dir.glob("*.md")):
            if path.resolve() in managed:
                continue
            if GENERATED_MARK in path.read_text(encoding="utf-8")[:600]:
                path.unlink()
                removed += 1

    print_problems([], index.warnings)
    print(f"已生成 {len(expected)} 个文件：写入 {written}，未变 {unchanged}，清理 {removed}。")
    return 0


def cmd_facts(index: Index) -> int:
    print("id\t状态\t类型\t负责人\t主模块\t上级\t简介\t标题")
    for ticket in index.sorted_tickets():
        entry = index.entries.get(ticket.id)
        summary = entry["summary"] if entry else "[缺少 meta 条目]"
        module = index.primary(ticket.id) or "[未归属]"
        assignee = ticket.assignee or "[未分配]"
        print(
            f"{ticket.id}\t{ticket.status}\t{ticket.type}\t{assignee}\t{module}"
            f"\t{ticket.parent or '-'}\t{summary}\t{ticket.title}"
        )
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="仓库根目录（默认向上查找 .tickets/）")
    parser.add_argument("command", nargs="?", choices=["facts", "check", "diff", "render"], default="check")
    args = parser.parse_args()

    index = Index(find_repo_root(args.repo))
    if args.command == "facts":
        return cmd_facts(index)
    if args.command == "diff":
        return cmd_diff(index)
    if args.command == "render":
        return cmd_render(index)
    return cmd_check(index)


if __name__ == "__main__":
    raise SystemExit(main())
