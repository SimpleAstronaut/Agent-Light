"""Desktop integration catalogue; this does not enable backend event adapters."""
from dataclasses import dataclass
from typing import Callable
from .pages.dsh import DshPage
from .pages.pending_agent import PendingAgentPage


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    implemented: bool
    description: str
    actions: frozenset[str]
    page_factory: Callable

    @property
    def status(self):
        return '已支持' if self.implemented else '待适配'


AGENTS = (
    AgentDefinition('dsh', 'DSH', True, '检测宿主、配置接入并查看安装结果。',
                    frozenset(('detect','generate','install','uninstall','open')), lambda _: DshPage()),
    AgentDefinition('codex', 'Codex', False, '统一事件接口已预留，真实事件适配器尚未实现。',
                    frozenset(('detect',)), PendingAgentPage),
    AgentDefinition('zcode', 'ZCode', False, '已预留独立接入页面，事件采集和配置安装尚未实现。',
                    frozenset(), PendingAgentPage),
    AgentDefinition('workbuddy', 'WorkBuddy', False, '已预留独立接入页面，事件采集和配置安装尚未实现。',
                    frozenset(), PendingAgentPage),
)
AGENTS_BY_ID = {agent.agent_id: agent for agent in AGENTS}
