// Copyright 2026 Agent Light Authors
// 文件/模块：应用调度与 USB 收发队列。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：先 BoardInit()，再调用一次 AppStart()；USB 回调仅调用 AppUsbReceive/Event。
// 约束：应用任务独占 Protocol/TX；USB ISR 写 RX 和事件，任务用临界区同步。
#include "app_main.h"
#include <string.h>
#include "FreeRTOS.h"
#include "task.h"
#include "board.h"
#include "protocol.h"
#include "usb_device.h"

// 静态 TCB/任务栈在整个运行期有效；384/96 均为字数，Cortex-M0 每字 4 字节。
static StaticTask_t app_tcb, idle_tcb;
static StackType_t app_stack[384], idle_stack[configMINIMAL_STACK_SIZE];
// 协议与显示对象仅由 AppTask 持有；ISR 不得解析或改动它。
static Protocol protocol;
// 单 USB ISR 生产、单任务消费的环形队列，空出一格区分满/空。
// ISR 写入字节并经 DMB 后发布 rx_write；任务读索引时使用临界区。
// rx_lost 通知任务丢弃协议半帧，rx_discard 让 ISR 丢弃到下一个分隔符。
static uint8_t rx_queue[256];
static volatile uint16_t rx_read, rx_write;
static volatile bool rx_lost, rx_discard;
// USB 总线事件代次；任务用 seen_epoch 拒绝旧代次数据和旧 LED 结果。
static volatile uint32_t usb_epoch;
static volatile DisplayMode usb_mode = kModeWaitSync;
// 单槽异步 TX：tx_size==0 表示空，tx_submitted 表示已交给 CDC。
// 等待 TxState 清零前不重用缓冲；总线事件使本代响应作废。
static uint8_t tx_buffer[40];
static uint8_t tx_size;
static bool tx_submitted;
volatile uint32_t g_app_stack_free_words;
volatile uint32_t g_rx_overflows;

// 通过递增代次使任务检测总线变化；清队列只在 ISR 与任务临界区之间串行发生。
void AppUsbEvent(DisplayMode mode) {
  usb_mode = mode;
  ++usb_epoch;
  rx_read = rx_write = 0;
  rx_lost = rx_discard = false;
}
// 将 USB 分包拼成字节流；不把每个 USB 包误当作一帧。
// 队列溢出后丢弃当前残帧，并保留后续首个 0，让任务的协议解析器同步恢复。
void AppUsbReceive(const uint8_t *data, size_t size) {
  for (size_t i = 0; i < size; ++i) {
    uint8_t byte = data[i];
    if (rx_discard && byte != 0) continue;
    uint16_t next = (uint16_t)((rx_write + 1) & 255u);
    if (next == rx_read) {
      // 队列溢出时清掉不完整数据；保留下一个分隔符供协议层恢复。
      ++g_rx_overflows;
      rx_read = rx_write = 0;
      rx_lost = rx_discard = true;
      if (byte != 0) continue;
      next = 1;
    }
    rx_discard = false;
    rx_queue[rx_write] = byte;
    __DMB();
    rx_write = next;
  }
}

// 应用任务在背压解除前停止取下一帧，因此只需一个静态 TX 槽。
// 复制完整响应到唯一静态 TX 槽，作为 ProtocolSend 回调使用。
// 参数：data 非 NULL，size 为 1..40 字节且含帧尾 0；context 未使用，可为 NULL。
// 返回 true；调用者必须保证槽为空，违反槽/容量约束触发 configASSERT 停机。
// 仅 AppTask 同步调用；复制后不保留 data，实际 USB 提交在后续轮询中进行。
static bool QueueReply(const uint8_t *data, size_t size, void *context) {
  (void)context;
  configASSERT(tx_size == 0 && size <= sizeof(tx_buffer));
  memcpy(tx_buffer, data, size);
  tx_size = (uint8_t)size;
  tx_submitted = false;
  return true;
}

// 运行自检、协议消费、异步发送和 LED 更新的唯一业务任务，永不返回。
// 参数：argument 是创建任务时传入的上下文，本项目为 NULL，未使用。
// 启动先完成 3×100 ms 自检再接入 USB；之后按 5 ms 绝对周期轮询。
// 每轮先消费总线代次/丢帧事件，再推进 TX；TX 槽占用时暂停 RX 解析，
// 确保 ProtocolSend 总有槽可写。每轮最多解析 64 字节，避免输入流饿死灯效。
// 临界区保护 ISR 共享索引、发送提交和寄存器更新；完整帧解析在区外运行。
// Reset 与尚未消费字节通过代次隔离；LED 写前再次确认代次与挂起状态。
static void AppTask(void *argument) {
  (void)argument;
  uint32_t seen_epoch = 0;
  uint32_t now = HAL_GetTick();
  ProtocolInit(&protocol, QueueReply, NULL, now);
  // USB 启动前展示三个 100 ms 自检阶段，USB reset 不会截断自检。
  for (unsigned i = 0; i < 3; ++i) {
    BoardSetLeds(DisplayGetLeds(&protocol.display, now + i * 100));
    vTaskDelay(pdMS_TO_TICKS(100));
  }
  ProtocolPoll(&protocol, HAL_GetTick());
  UsbDeviceInit();
  TickType_t wake = xTaskGetTickCount();
  for (;;) {
    now = HAL_GetTick();
    taskENTER_CRITICAL();
    if (seen_epoch != usb_epoch) {
      seen_epoch = usb_epoch;
      tx_size = 0;
      tx_submitted = false;
      ProtocolReset(&protocol, now);
      if (usb_mode == kModeSuspended) ProtocolSuspend(&protocol);
      else BoardPwmResume();
    }
    if (rx_lost) {
      rx_lost = false;
      ProtocolRxLost(&protocol);
    }
    if (tx_size != 0) {
      if (!tx_submitted) tx_submitted = UsbTransmit(tx_buffer, tx_size);
      else if (!UsbTransmitBusy()) tx_size = 0;
    }
    taskEXIT_CRITICAL();
    // 每轮最多 64 字节；时间推进和 LED 更新不会被连续输入饿死。
    for (unsigned count = 0; count < 64 && tx_size == 0; ++count) {
      taskENTER_CRITICAL();
      bool available = rx_read != rx_write && seen_epoch == usb_epoch && !rx_lost;
      uint8_t byte = 0;
      if (available) {
        byte = rx_queue[rx_read];
        rx_read = (uint16_t)((rx_read + 1) & 255u);
      }
      taskEXIT_CRITICAL();
      if (!available) break;
      ProtocolFeed(&protocol, byte, now);
    }
    ProtocolPoll(&protocol, now);
    taskENTER_CRITICAL();
    // ISR 可立即停 PWM；这里再次检查代次，防止旧的计算结果恢复输出。
    if (seen_epoch == usb_epoch && usb_mode != kModeSuspended) {
      BoardSetLeds(DisplayGetLeds(&protocol.display, now));
    }
    taskEXIT_CRITICAL();
    g_app_stack_free_words = uxTaskGetStackHighWaterMark(NULL);
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(5));
  }
}

// 向 FreeRTOS 提供唯一 Idle 任务的静态存储，不分配堆。
// 参数：tcb、stack、size 均为非 NULL 输出指针，分别覆盖为 TCB 地址、
// 栈首地址和栈容量（StackType_t 字数，非字节）。内存具有静态生命周期。
// 由调度器启动过程调用一次；应用代码不要自行调用或复用这些存储。
void vApplicationGetIdleTaskMemory(StaticTask_t **tcb, StackType_t **stack,
                                  uint32_t *size) {
  *tcb = &idle_tcb; *stack = idle_stack; *size = configMINIMAL_STACK_SIZE;
}
// 在 Idle 任务中等待中断以减少空转；无参数，返回后仍由内核调度。
// 不得改为阻塞等待或 HAL_Delay；此处不进入 Stop，也不调整 USB 时钟。
void vApplicationIdleHook(void) { __WFI(); }
// 检测到栈溢出后全灭停机，不返回，不尝试使用已经损坏的任务状态。
// 参数：task 为出错任务句柄，name 为任务名指针；均未使用，不解引用。
// 由 FreeRTOS 的栈检查路径调用，不执行阻塞操作。
void vApplicationStackOverflowHook(TaskHandle_t task, char *name) {
  (void)task; (void)name; BoardFatal();
}
// 使用预留 TCB/栈创建优先级 1 的应用任务；Idle 优先级为 0。
// xTaskCreateStatic 的 384 是栈字数；调度器异常返回也进入故障停机。
void AppStart(void) {
  configASSERT(xTaskCreateStatic(AppTask, "agent-light", 384, NULL, 1,
                                 app_stack, &app_tcb) != NULL);
  vTaskStartScheduler();
  BoardFatal();
}
