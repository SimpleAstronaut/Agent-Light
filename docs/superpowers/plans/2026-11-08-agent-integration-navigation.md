# Agent 接入二级导航实施计划

> 使用 executing-plans 内联实施，遵照用户既有要求省去独立审查代理和重复测试流程。

**Goal:** DSH 成为 Agent 接入下的二级配置页，其他 Agent 为明确的待适配页面。
**Architecture:** Agent 登记表 → 导航树/页面工厂 → 持久面板实例；带 Agent 身份的动作分发与异步结果归属。
**Tech Stack:** 现有 Python / PySide6 Widgets / QSettings / 受管后台任务。
**Spec:** `docs/superpowers/specs/2026-11-08-agent-integration-navigation-design.md`。

## 约束

- 不改固件、USB、事件 schema 和后台聚合。
- 保留 DSH 所有配置键、正式 overlay 和安装记录位置。
- 导航选择不改变实际接入；未实现 Agent 不执行 DSH 操作。
- 每项异步操作只更新所属 Agent 面板，导航保持可用。
- 仅运行必要的导航/分发回归、现有 PC 回归及冻结包验证。

## 任务

- [x] 1. 新增 Agent 登记表、独立 DSH 面板、通用待适配面板；将 PluginsPage 改为登记驱动的页面容器。
- [x] 2. 主窗口采用导航树并提供 navigate(section, agent_id=None)；控制器按 Agent 分发，保留旧 DSH 偏好并记忆浏览选择。
- [x] 3. 覆盖 DSH 输入保留、所有子页可达、待适配动作禁用、跨页面异步结果隔离和只读选择；更新旧导航测试。
- [x] 4. 更新手册、版本 0.2.1、渲染检查；运行 PC 回归及构建/烟雾验证，产出安装器、zip、wheel 和校验文件。

## 验证关注点

切换页面时检测返回；DSH 未保存输入；未知/过期 Agent 偏好；多个 Agent 动作同时在途；冻结包遗漏面板工厂引用模块。

## 执行记录

复用 `codex/desktop-runtime` 功能分支，不创建额外 worktree，不修改真实 DSH 或用户配置。无共享后台接口变更；唯一接口变化是 UI action 增加 Agent 身份、导航从行号改为稳定 section ID。

任务 1–3：完成。DSH 面板沿用既有路径偏好与后台事务；导航与动作由 Agent 登记表生成/校验，异步任务按 Agent 单独收拢。现有输入在页面切换中保留，迟到检测结果不会覆盖期间新输入，也不会更新当前其他 Agent 的页面。
验证：PC 35/35，通过且无 Qt skip；新增 3 项覆盖页面/能力、并发结果归属和未实现动作拒绝。既有 Qt 生命周期测试同时验证旧 DSH 偏好恢复、记忆浏览 Agent 和服务继续运行。四个 Agent 面板已渲染检查。未运行独立审查代理。

任务 4：完成。版本 0.2.1，手册按 Agent 接入 → DSH 更新，分发包包含完整使用手册及其引用的初始验收记录。GUI/console onedir 已构建；冻结 GUI 实际遍历全部 Agent 子页，确认 DSH 输入保留；独立中文空格目录中的插件/Worker、CLI、schema/元数据和外部 Node 检测通过，Inno Setup 编译通过。

未修改后台 schema/来源白名单、USB、固件或实际用户配置；Codex/ZCode/WorkBuddy 事件适配继续明确为待实现。本次没有新增真实宿主写入或实板操作，不重复既有后端性能验收。后端性能与硬件手工验收边界沿用初始桌面记录。
