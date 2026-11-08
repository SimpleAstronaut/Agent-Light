"""Presentation only: device confirmation and lease decisions belong to the service."""
STATE_NAMES = {'IDLE':'空闲', 'RUNNING':'运行中', 'ATTENTION':'等待处理', 'ERROR':'异常', 'COMPLETED':'已完成'}
ERRORS = {
    'ADAPTER_NOT_IMPLEMENTED':'此 Agent 的相关适配尚未实现，请选择已支持的接入。',
    'SERVICE_UNAVAILABLE':'无法连接本地服务，请检查服务是否启动。',
    'SERVICE_ALREADY_RUNNING':'已有服务正在运行，请先正常退出原服务。',
    'ENDPOINT_IN_USE':'服务地址已被占用，请检查占用程序或更改配置。',
    'CONFIG_INSTANCE_CONFLICT':'已有桌面实例使用另一配置，请先退出再切换。',
    'AUTH_FAILED':'服务鉴权失败，请检查所选配置和 token 文件。',
    'DEVICE_NOT_READY':'灯板尚未确认，请连接设备并等待同步。',
    'DEVICE_NOT_FOUND':'没有找到设备，请检查连接并重新扫描。',
    'DEVICE_NOT_UNIQUE':'发现多个匹配设备，请选择端口或填写序列号。',
    'DEVICE_IDENTITY_MISMATCH':'端口与序列号不匹配，请重新选择。',
    'DISPLAY_TEST_RUNNING':'三色测试正在进行，请稍后再保存。',
    'CONFIG_CHANGED_EXTERNALLY':'配置已被外部修改，请重启服务加载。',
    'CONFIG_SAVE_FAILED':'配置保存失败，请检查磁盘和目录权限。',
    'INVALID_DISPLAY_CONFIG':'亮度必须为 20–100 的整数，保持时间必须为非负整数。',
    'INSTALLER_UNSUPPORTED':'启动脚本结构不受支持，请按手工说明接入。',
    'UNSUPPORTED_VERSION':'DSH 版本或文件指纹不兼容。',
    'HOST_NOT_FOUND':'未找到可检测的 DSH 宿主，请手工选择入口。',
    'NODE_RUNTIME_MISSING':'请选择该 DSH 环境使用的 Node 可执行文件。',
    'SHUTDOWN_TIMEOUT':'退出清理超过预期，仍在等待资源释放。',
    'PRODUCER_STILL_REPORTING':'来源仍在上报，请退出对应 DSH 并等待租约到期。',
    'SOURCE_STATE_CHANGED':'来源状态已变化，请刷新后重新操作。',
    'INSTALLER_CONCURRENT_CHANGE':'文件在预览后发生变化，请重新预览。',
    'INTEGRATION_CONFLICT':'检测到另一个 Agent Light 接入，请先解除旧接入。',
}


def explain(code):
    return ERRORS.get(code, '操作未完成，请检查相关路径、权限和当前状态。') + ' [' + code + ']'


def reporting(producers, agent='dsh'):
    rows = [p for p in producers if p['agent'] == agent]
    active = [p for p in rows if p.get('management_state','enabled') != 'disabled']
    if not rows:
        return '未上报'
    if not active:
        return '来源已停用'
    if any(p.get('lease_expired') or p.get('health') == 'degraded' for p in active):
        return '上报异常'
    if any(p.get('management_state') == 'activation_pending' for p in active):
        return '待重启来源 / 恢复中'
    if all(p.get('health') == 'healthy' and p.get('last_heartbeat_at') for p in active):
        return '上报正常'
    return '等待当前进程心跳'


def overview(snapshot=None, *, fresh=True, failures=0):
    if not fresh or snapshot is None:
        return ['服务离线' if failures >= 3 else '刷新失败 / 等待服务', '未知（快照过期）', '未知（服务不可用）', '未知']
    device = snapshot.get('device', {})
    return ['服务在线', reporting(snapshot.get('producers', [])),
            '灯板已确认' if device.get('confirmed') else '同步中' if device.get('connected') else '未连接',
            STATE_NAMES.get(snapshot.get('desired'), '未知')]
