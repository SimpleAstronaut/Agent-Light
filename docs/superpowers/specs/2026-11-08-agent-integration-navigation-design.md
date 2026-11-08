# Agent 接入二级导航设计

用户已确认：将 DSH 配置放入可选择的二级页面，为 Codex、ZCode、WorkBuddy 留出扩展入口。选择仅切换配置界面，多个来源可同时接入并聚合。

采用现有 PySide6 Widgets：一级导航保留状态、设备、设置，将插件改为 Agent 接入；其下展示 DSH、Codex、ZCode、WorkBuddy。界面通过登记表生成子项和面板，使用 QStackedWidget 切换，复用面板实例以保留未保存输入及检测结果。

DSH 保留既有检测/草稿/安装/卸载/配置目录及 `dsh/entry`、`dsh/node`、`dsh/launcher` 偏好，后台事务和安装记录不迁移。Codex 保留只读环境检测，清楚标记事件适配待实现；ZCode、WorkBuddy 只显示待适配说明，检测/安装等未实现动作禁用。

动作必须带 agent_id，按能力分发；异步结果绑定发起操作时的具体面板，切换页面不会串写状态或触发安装/停用/断开。DSH 与 Codex 检测任务独立管理。记忆上次浏览 Agent 仅使用桌面 QSettings，不修改后台配置。

此次不扩展事件 schema、后台来源白名单、USB 或固件，不声称新增实际 Agent 适配。已登记各 Agent 的后续适配由独立适配器提供。

方案取舍：采用一级导航树内的二级项目，直接对应已确认层级；不采用全局互斥的 Agent 运行模式，也不使用仅能看到一个入口的下拉框。

版本升级为 0.2.1，以区分此前 0.2.0 分发。更新手册并构建 GUI/console onedir、安装器、便携 zip 和 Python wheel；保留历史版本。
