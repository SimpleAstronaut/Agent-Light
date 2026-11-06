// Copyright 2026 Agent Light Authors
// 文件/模块：Rev A 时钟、USB 引脚映射和三色 PWM 板级驱动。
// 版本：1.0.0（固件基线）；日期：2026-10-28。
// 用法：启动时调用 BoardInit()；任务用 BoardSetLeds() 更新三路百分比占空比。
// 约束：挂起/恢复只控制 TIM2 计数器；异常统一经 BoardFatal() 全灭停机。
#include "board.h"

// TIM2 的唯一 HAL 句柄，初始化后通道保持启动状态，挂起只停计数器。
static TIM_HandleTypeDef pwm;

// 先确认 TIM2 外设时钟已打开再触碰其寄存器，使初始化早期失败也能停机。
void BoardFatal(void) {
  __disable_irq();
  // 清零比较寄存器，即便调度器或 USB 失败也不保持误导灯态。
  if (RCC->APB1ENR & RCC_APB1ENR_TIM2EN) {
    TIM2->CCR1 = 0; TIM2->CCR2 = 0; TIM2->CCR3 = 0;
    TIM2->CCER = 0;
  }
  for (;;) __WFI();
}

// 依次建立 48 MHz 系统/USB 时钟、SOF 校准、TSSOP-20 USB 重映射和 PWM。
// CRS 以 USB 1 kHz SOF 为参考；USB 引脚重映射必须在 USB 外设启动前完成。
// PWM 先将所有通道比较值设为 0 再启动，避免上电误亮；错误统一停机。
void BoardInit(void) {
  HAL_Init();
  RCC_OscInitTypeDef osc = {0};
  osc.OscillatorType = RCC_OSCILLATORTYPE_HSI48;
  osc.HSI48State = RCC_HSI48_ON;
  osc.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&osc) != HAL_OK) BoardFatal();
  RCC_ClkInitTypeDef clock = {0};
  clock.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                    RCC_CLOCKTYPE_PCLK1;
  clock.SYSCLKSource = RCC_SYSCLKSOURCE_HSI48;
  clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clock.APB1CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_1) != HAL_OK) BoardFatal();
  RCC_PeriphCLKInitTypeDef peripheral = {0};
  peripheral.PeriphClockSelection = RCC_PERIPHCLK_USB;
  peripheral.UsbClockSelection = RCC_USBCLKSOURCE_HSI48;
  if (HAL_RCCEx_PeriphCLKConfig(&peripheral) != HAL_OK) BoardFatal();
  __HAL_RCC_CRS_CLK_ENABLE();
  RCC_CRSInitTypeDef crs = {0};
  crs.Prescaler = RCC_CRS_SYNC_DIV1;
  crs.Source = RCC_CRS_SYNC_SOURCE_USB;
  crs.Polarity = RCC_CRS_SYNC_POLARITY_RISING;
  crs.ReloadValue = __HAL_RCC_CRS_RELOADVALUE_CALCULATE(48000000, 1000);
  crs.ErrorLimitValue = RCC_CRS_ERRORLIMIT_DEFAULT;
  crs.HSI48CalibrationValue = RCC_CRS_HSI48CALIBRATION_DEFAULT;
  HAL_RCCEx_CRSConfig(&crs);
  __HAL_RCC_SYSCFG_CLK_ENABLE();
  // TSSOP-20 的物理 17/18 脚必须重映射，不能使用 PA9/10 的 UART 功能。
  SET_BIT(SYSCFG->CFGR1, SYSCFG_CFGR1_PA11_PA12_RMP);
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_TIM2_CLK_ENABLE();
  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  gpio.Alternate = GPIO_AF2_TIM2;
  HAL_GPIO_Init(GPIOA, &gpio);
  pwm.Instance = TIM2;
  pwm.Init.Prescaler = 0;
  pwm.Init.CounterMode = TIM_COUNTERMODE_UP;
  pwm.Init.Period = 4799;  // 48 MHz / (0 + 1) / (4799 + 1) = 10 kHz。
  pwm.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  pwm.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  if (HAL_TIM_PWM_Init(&pwm) != HAL_OK) BoardFatal();
  TIM_OC_InitTypeDef channel = {0};
  channel.OCMode = TIM_OCMODE_PWM1;
  channel.Pulse = 0;
  channel.OCPolarity = TIM_OCPOLARITY_HIGH;
  channel.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&pwm, &channel, TIM_CHANNEL_1) != HAL_OK ||
      HAL_TIM_PWM_ConfigChannel(&pwm, &channel, TIM_CHANNEL_2) != HAL_OK ||
      HAL_TIM_PWM_ConfigChannel(&pwm, &channel, TIM_CHANNEL_3) != HAL_OK) {
    BoardFatal();
  }
  if (HAL_TIM_PWM_Start(&pwm, TIM_CHANNEL_1) != HAL_OK ||
      HAL_TIM_PWM_Start(&pwm, TIM_CHANNEL_2) != HAL_OK ||
      HAL_TIM_PWM_Start(&pwm, TIM_CHANNEL_3) != HAL_OK) BoardFatal();
}

// 百分比乘以 48 得到 CCR；ARR=4799 时 CCR=4800 对应真正的 100% 高电平。
void BoardSetLeds(LedLevels levels) {
  // Rev A 为 GPIO 高电平点亮；100% 比较值 4800，实现真正常亮。
  TIM2->CCR1 = (uint32_t)levels.red * 48;
  TIM2->CCR2 = (uint32_t)levels.yellow * 48;
  TIM2->CCR3 = (uint32_t)levels.green * 48;
}
// 通过 EGR 强制更新零比较值后再停计数器，使预装载不会留下旧的点亮电平。
void BoardPwmSuspend(void) {
  BoardSetLeds((LedLevels){0, 0, 0});
  // 比较寄存器有预装载，先强制更新，避免停计数器时留下高电平。
  TIM2->EGR = TIM_EGR_UG;
  CLEAR_BIT(TIM2->CR1, TIM_CR1_CEN);
}
// 只恢复 CEN；HAL 通道状态仍为 BUSY，重复调用 HAL_TIM_PWM_Start 会失败。
void BoardPwmResume(void) {
  // 通道已经启动，HAL 状态保持 BUSY；重复调用 PWM_Start 会返回错误。
  // 挂起只停计数器，因此恢复只需使能 CEN，并允许重复 reset/resume。
  SET_BIT(TIM2->CR1, TIM_CR1_CEN);
}
