# B01 measurement_locator 重建
> 生成器 `build_measurement_locator/1.0.0` · 2026-11-23T05:21:35Z

## 一、结论
- 测量总数：**2065**
- 获得定位符：**2065**（100.0%）
- 无定位符：**0**
- 来源文件：61 个，成功解析 61 个

## 二、定位符语义
格式：`ThermoML block=<n>|prop=<n>|propname=<...>|phase=<...>|method=<...>|row=<n>`

**定位到什么：** 沉积的 ThermoML 记录中的数据块与性质条目

**不定位什么：** 印刷版论文的页码、表格号、图号. 这些信息 ThermoML 不携带, 需要人工回原文补录, 不得由本程序推断.

## 三、分布
- `THEROML_BLOCK_AND_PROPERTY`：2065

## 四、残余缺口
来源文件不可读或结构中无 PureOrMixtureData 块 (例如 NBS Circular 514 的人工转录行, 其来源不是 ThermoML)

**规则：** 缺失即登记为 UNRESOLVED, 不补造定位符
