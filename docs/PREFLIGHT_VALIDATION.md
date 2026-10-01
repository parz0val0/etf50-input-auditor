# rc5 preflight validation / 预检验证

21 focused synthetic regressions; candidate199 passed, working project235 passed. 中文/BOM、未知列、重复列/别名歧义、行宽、日期、无时区/混合偏移、非有限值、数量整数、单位标注、未知价格语义、缺列、确认哈希、重复映射、Excel二进制拒绝及两次复用映射均覆盖。Main-checker agreement is asserted; no relaxed second qualification implementation.

公开合成复跑：`python3 scripts/reproduce_preflight_case.py --output audit-output/preflight-demo`，新目录；预检0、转换0、源不变、同一主检查结果、源与映射哈希留痕。No values or evidence are fabricated.

macOS/Python3.9 official PyPI isolated install passed after normal approved-network retry (initial sandbox DNS failed). Version CLI and package metadata0.4.0rc5, pip check passed. 实跑正常0、故障1、最小日数据1、中文原表直接检查2、预检0、修正演示0、中文BOM确认0、数值辅助0。Initial network failure is not evidence of package incompatibility.

双语README命令一致；回归不证明真人提效或市场研究完成；HTML转义/结构有测试，浏览器视觉未核验。The original first simulated-study scores remain unchanged. No real supplier validation or efficacy claim.

最终清单绑定公开文件，不认证供应商事实或许可。Await independent review before publishing.

## rc6审查修复

rc5首轮测试计数保留为历史。rc6新增9项回归：null/数组/标量映射拒绝、坏policy无最终目录、确定性读间修改映射（只读一次且应用快照与SHA一致）、输出复制故障清理且既有哨兵不动、真实CLI拒绝路径。公开候选208通过；工作项目含独立Heston253通过。

所有输入校验及准入在私有临时目录完成，成功后才创建最终目录；普通写入失败清理仅本次新建目录，既有目录从不删除。不声称进程被强制杀死时的多文件原子发布保证。映射同一raw快照用于解析与SHA；policy已有single-read parse+SHA；源CSV单次读取用于预览及源SHA，转换后主检查读取本次生成的私有规范副本。
